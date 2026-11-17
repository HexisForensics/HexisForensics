"""
Representação do dispositivo Android alvo: verificação de conexão/
autorização (antigo `1_verificar_conexao.py`) e coleta de especificações
técnicas (antigo `4_caracteristicas_tecnicas.py`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .adb_client import ADBClient


@dataclass
class StatusConexao:
    conectado: bool
    autorizado: bool
    serial: Optional[str]
    mensagem: str
    seriais_detectados: List[str] = field(default_factory=list)

    @property
    def multiplos_dispositivos(self) -> bool:
        """
        Mais de um aparelho plugado ao mesmo tempo.

        E uma condicao que precisa bloquear a extracao, nao apenas avisar:
        sem escolha explicita do examinador, qualquer selecao automatica
        arrisca periciar o aparelho errado — ou, se um segundo aparelho for
        conectado no meio do procedimento, misturar dados de dois
        dispositivos no mesmo caso.
        """
        return len(self.seriais_detectados) > 1


@dataclass
class RelogioDispositivo:
    """
    Relogio do aparelho confrontado com o da estacao forense.

    Os carimbos de tempo dos artefatos extraidos so tem ancora se o desvio
    do relogio do aparelho for conhecido e documentado. Um celular com a
    data adiantada em tres dias produz evidencia que, sem essa medicao,
    seria lida como se estivesse correta.
    """

    epoch_dispositivo: Optional[int]
    epoch_estacao: int
    data_dispositivo_texto: str
    fuso_dispositivo: str

    @property
    def desvio_segundos(self) -> Optional[int]:
        if self.epoch_dispositivo is None:
            return None
        return self.epoch_dispositivo - self.epoch_estacao

    @property
    def data_estacao_iso(self) -> str:
        return datetime.fromtimestamp(self.epoch_estacao, tz=timezone.utc).astimezone().isoformat()

    def resumo(self, idioma: str = None) -> str:
        from core.idioma import traduzir
        if self.desvio_segundos is None:
            return traduzir("rel_resumo_ilegivel", idioma)

        from core.relogio import descrever_desvio

        return traduzir("rel_resumo", idioma, data=self.data_dispositivo_texto,
                        fuso=self.fuso_dispositivo, estacao=self.data_estacao_iso,
                        desvio=descrever_desvio(self.desvio_segundos, idioma))


@dataclass
class EspecificacoesDispositivo:
    fabricante: str = ""
    modelo: str = ""
    marca: str = ""
    numero_serie: str = ""
    arquitetura_cpu: str = ""
    versao_android: str = ""
    versao_sdk: str = ""
    patch_seguranca: str = ""
    info_bateria: str = ""


class AndroidDevice:
    def __init__(self, adb_client: Optional[ADBClient] = None):
        self.adb = adb_client or ADBClient()

    def verificar_conexao(self) -> StatusConexao:
        from core.idioma import traduzir
        binario_ok, motivo = self.adb.verificar_binario()
        if not binario_ok:
            return StatusConexao(False, False, None, motivo)

        dispositivos = self.adb.listar_dispositivos()
        if not dispositivos:
            return StatusConexao(
                False, False, None, traduzir("dev_sem_dispositivo"),
            )

        seriais = [serial for serial, _ in dispositivos]

        # Mais de um aparelho plugado: recusa, em vez de escolher por conta
        # propria. Ver `StatusConexao.multiplos_dispositivos`.
        if len(dispositivos) > 1:
            return StatusConexao(
                True, False, None,
                traduzir("dev_multiplos", seriais=', '.join(seriais)),
                seriais_detectados=seriais,
            )

        serial, status = dispositivos[0]
        if status == "device":
            return StatusConexao(
                True, True, serial,
                traduzir("dev_conectado", serial=serial),
                seriais_detectados=seriais,
            )
        if status == "unauthorized":
            return StatusConexao(
                True, False, serial,
                traduzir("dev_nao_autorizado"),
                seriais_detectados=seriais,
            )
        return StatusConexao(
            True, False, serial,
            traduzir("dev_status_inesperado", status=status),
            seriais_detectados=seriais,
        )

    def obter_relogio(self) -> RelogioDispositivo:
        """
        Le o relogio do aparelho e o confronta com o da estacao forense.

        Executado no inicio do procedimento: o desvio precisa ser o do
        momento da aquisicao, nao o de uma medicao posterior.
        """
        from core.idioma import traduzir
        epoch_estacao = int(time.time())
        epoch_bruto = self.adb.executar(["shell", "date", "+%s"], timeout=20).strip()

        epoch_dispositivo: Optional[int] = None
        if epoch_bruto.isdigit():
            epoch_dispositivo = int(epoch_bruto)

        return RelogioDispositivo(
            epoch_dispositivo=epoch_dispositivo,
            epoch_estacao=epoch_estacao,
            data_dispositivo_texto=self.adb.executar(["shell", "date"], timeout=20).strip()
            or traduzir("rel_ilegivel_data"),
            fuso_dispositivo=self.adb.obter_propriedade("persist.sys.timezone").strip()
            or traduzir("rel_fuso_desconhecido"),
        )

    def obter_id_dispositivo(self) -> str:
        for serial, status in self.adb.listar_dispositivos():
            if status == "device":
                return serial
        from core.aparelho import ID_GENERICO_ANDROID

        return ID_GENERICO_ANDROID

    def obter_especificacoes(self) -> EspecificacoesDispositivo:
        return EspecificacoesDispositivo(
            fabricante=self.adb.obter_propriedade("ro.product.manufacturer"),
            modelo=self.adb.obter_propriedade("ro.product.model"),
            marca=self.adb.obter_propriedade("ro.product.brand"),
            numero_serie=self.adb.obter_propriedade("ro.serialno"),
            arquitetura_cpu=self.adb.obter_propriedade("ro.product.cpu.abi"),
            versao_android=self.adb.obter_propriedade("ro.build.version.release"),
            versao_sdk=self.adb.obter_propriedade("ro.build.version.sdk"),
            patch_seguranca=self.adb.obter_propriedade("ro.build.version.security_patch"),
            info_bateria=self.adb.executar(["shell", "dumpsys", "battery"]),
        )
