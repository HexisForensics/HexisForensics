"""
Serviço de dispositivo.

Fachada única sobre `core.android.device.AndroidDevice`,
`core.ios.device.IOSDevice` e `core.computador.device.ComputadorDevice`: a
UI pede status/identificação "do dispositivo da plataforma X" sem
precisar saber que essas classes existem em módulos diferentes de `core`,
com construtores e formas de "conexão" diferentes. Isso é o que mantém
`ui/` sem nenhum `import core...`.

Computador não se encaixa no modelo de Android/iOS (um único dispositivo
conectado via cabo/pareamento, "conectado ou não"): o examinador escolhe,
entre várias unidades de disco detectadas, qual será periciada. Por isso
os métodos de Computador têm nomes e formatos de retorno próprios
(`listar_unidades_computador`, `UnidadeInfo`) em vez de reaproveitar
`verificar_conexao`/`StatusDispositivo`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.android.adb_client import ADBClient
from core.android.device import AndroidDevice
from core.computador.device import ComputadorDevice
from core.computador.disk_client import UnidadeDisco, descrever_bloqueio
from core.computador.extractors.base import raiz_instalacao_suite
from core.ios.client import IOSClient
from core.ios.device import IOSDevice

ANDROID = "Android"
IOS = "iOS"
COMPUTADOR = "Computador"


@dataclass
class StatusDispositivo:
    conectado: bool
    autorizado: bool
    mensagem: str


@dataclass
class UnidadeInfo:
    """Espelha `core.computador.disk_client.UnidadeDisco`, sem expor o tipo do core à UI."""

    letra: str
    caminho: str
    tipo_descricao: str
    rotulo: str
    sistema_arquivos: str
    bytes_livres: int
    bytes_total: int
    # A unidade onde o próprio HexisForensics está instalado. Nunca é
    # objeto de perícia: é a estação do examinador. Vem marcada daqui, e
    # não calculada na UI, porque `ui/` não pode importar `core.*` — e a
    # raiz da suíte é justamente um dado de `core` (ver
    # `core.computador.extractors.base.raiz_instalacao_suite`, que trata o
    # caso da suíte empacotada em `.exe`).
    e_estacao_do_examinador: bool = False
    # Estado de leitura do volume (ver `core.computador.disk_client`):
    # vazio quando responde normalmente; "bitlocker", "indeterminado" ou
    # "ilegivel" quando o Windows não conseguiu ler o sistema de arquivos.
    # A explicação vem pronta do core — é conhecimento sobre o alvo, e a
    # tela só a exibe.
    bloqueio: str = ""
    explicacao_bloqueio: str = ""


def _letra_da_estacao() -> str:
    """
    Letra da unidade onde a suíte está instalada agora (ex.: 'C'), ou ''
    se não for possível determinar. Descoberta a cada chamada, nunca fixa:
    a suíte pode ter sido movida de disco desde a última execução.
    """
    try:
        return raiz_instalacao_suite().drive.rstrip(":").upper()
    except OSError:
        return ""


@dataclass
class StatusUnidadeInfo:
    disponivel: bool
    unidade: Optional[UnidadeInfo]
    mensagem: str


class DeviceService:
    """Ponto único de acesso a status e identificação de dispositivo, por plataforma."""

    def __init__(self):
        self._android = AndroidDevice(ADBClient())
        self._ios = IOSDevice(IOSClient())
        self._computador = ComputadorDevice()

    def verificar_conexao(self, nome_plataforma: str) -> StatusDispositivo:
        status = (
            self._android.verificar_conexao()
            if nome_plataforma == ANDROID
            else self._ios.verificar_conexao()
        )
        return StatusDispositivo(status.conectado, status.autorizado, status.mensagem)

    def obter_id_dispositivo(self, nome_plataforma: str) -> str:
        if nome_plataforma == ANDROID:
            return self._android.obter_id_dispositivo()
        return self._ios.obter_id_dispositivo()

    def obter_udid_ios(self) -> Optional[str]:
        """UDID do iPhone conectado e que confia nesta estação, ou `None`."""
        status = self._ios.verificar_conexao()
        return status.identificador if status.autorizado else None

    def conferir_iphone_do_caso(self, udid_esperado: str) -> tuple:
        """Mesma conferência de `conferir_aparelho_do_caso`, para o iPhone."""
        try:
            conectados = {udid for udid, _ in self._ios.client.listar_dispositivos()}
        except Exception as erro:  # serviço da Apple parado, biblioteca ausente
            return False, (
                f"NÃO foi possível confirmar o iPhone '{udid_esperado}' ao final da "
                f"aquisição: {erro}"
            )
        if udid_esperado in conectados:
            return True, f"iPhone '{udid_esperado}' confirmado ao final da aquisição."
        if not conectados:
            return False, (
                f"NÃO foi possível confirmar o iPhone '{udid_esperado}' ao final da "
                "aquisição: nenhum iPhone conectado neste momento."
            )
        return False, (
            f"O iPhone conectado ao final ({', '.join(sorted(conectados))}) NÃO é o do caso "
            f"('{udid_esperado}')."
        )

    def obter_serial_android(self) -> Optional[str]:
        """
        Serial do aparelho Android conectado e autorizado, ou `None`.

        É o valor com que os extratores são vinculados ao aparelho do caso
        (`adb -s <serial>`), garantindo que nenhum comando escape para
        outro dispositivo que venha a ser conectado durante o procedimento.
        """
        status = self._android.verificar_conexao()
        return status.serial if status.autorizado else None

    def conferir_aparelho_do_caso(self, serial_esperado: str) -> tuple:
        """
        Confere se o aparelho vinculado ao caso ainda e o que responde ao ADB.

        Chamado no encerramento: um aparelho trocado, desconectado ou
        substituido no meio do procedimento e um evento de cadeia de
        custodia, e o registro do caso precisa afirmar que o dispositivo do
        inicio e o mesmo do fim -- ou dizer que nao foi possivel confirmar.
        """
        status = self._android.verificar_conexao()
        seriais = status.seriais_detectados

        if serial_esperado in seriais and status.autorizado:
            return True, f"Aparelho '{serial_esperado}' confirmado ao final da aquisição."
        if not seriais:
            return False, (
                f"NÃO foi possível confirmar o aparelho '{serial_esperado}' ao final da "
                "aquisição: nenhum dispositivo respondeu ao ADB neste momento."
            )
        return False, (
            f"DIVERGÊNCIA ao final da aquisição: o aparelho do caso é '{serial_esperado}', "
            f"e o que responde ao ADB agora é '{', '.join(seriais)}'."
        )

    def obter_versao_adb(self) -> str:
        """Versão do binário ADB em uso, para o registro do procedimento."""
        return self._android.adb.versao()

    def obter_relogio_android(self) -> Tuple[str, str]:
        """
        `(resumo, alerta)` do relógio do aparelho contra o da estação.

        `alerta` vem vazio quando o desvio está dentro do limite.
        """
        from core.relogio import alerta

        relogio = self._android.obter_relogio()
        return relogio.resumo(), alerta(relogio.desvio_segundos)

    # ------------------------------------------------------------------
    # Computador: não existe "conexão" — existe "unidades disponíveis".
    # ------------------------------------------------------------------
    def listar_unidades_computador(
        self, apenas_removiveis: bool = False
    ) -> List[UnidadeInfo]:
        """Lista as unidades de disco detectadas, para o examinador escolher qual periciar."""
        return [
            self._converter_unidade(unidade)
            for unidade in self._computador.listar_unidades(
                apenas_removiveis=apenas_removiveis
            )
        ]

    def verificar_unidade_computador(self, caminho_unidade: str) -> StatusUnidadeInfo:
        """Confirma que a unidade escolhida ainda está disponível, logo antes de iniciar a extração."""
        status = self._computador.verificar_unidade(caminho_unidade)
        return StatusUnidadeInfo(
            disponivel=status.disponivel,
            unidade=self._converter_unidade(status.unidade) if status.unidade else None,
            mensagem=status.mensagem,
        )

    def obter_id_unidade_computador(self, caminho_unidade: str) -> str:
        """Identificação da mídia (interface, série do volume, rótulo e letra), para a cadeia de custódia."""
        return self._computador.obter_id_unidade(caminho_unidade)

    @staticmethod
    def _converter_unidade(unidade: UnidadeDisco) -> UnidadeInfo:
        return UnidadeInfo(
            letra=unidade.letra,
            caminho=unidade.caminho,
            tipo_descricao=unidade.tipo_descricao,
            rotulo=unidade.rotulo,
            sistema_arquivos=unidade.sistema_arquivos,
            bytes_livres=unidade.bytes_livres,
            bytes_total=unidade.bytes_total,
            e_estacao_do_examinador=(
                bool(unidade.letra) and unidade.letra.upper() == _letra_da_estacao()
            ),
            bloqueio=unidade.bloqueio,
            explicacao_bloqueio=descrever_bloqueio(unidade),
        )
