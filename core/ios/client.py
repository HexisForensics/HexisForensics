"""
Cliente de baixo nível para iPhone — a contraparte de `ADBClient`.

Fala com o aparelho pelo serviço de dispositivos móveis da Apple (no
Windows, o que o aplicativo "Dispositivos Apple" ou o iTunes instalam),
por meio da biblioteca `pymobiledevice3`. Não há jailbreak nem agente: o
que se obtém é o que o próprio iOS entrega a um computador em que o dono
do aparelho CONFIOU — as informações do aparelho e o backup local, o mesmo
que o iTunes faria.

Todas as operações são vinculadas ao UDID do aparelho do caso, pela mesma
razão de `adb -s <serial>`: um segundo aparelho conectado no meio do
procedimento não pode receber comando nenhum.

A biblioteca é assíncrona; aqui cada operação roda até o fim antes de
devolver, porque os extratores são síncronos (rodam numa thread própria).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

DOMINIO_DE_BACKUP = "com.apple.mobile.backup"

FALTA_O_SERVICO_DA_APPLE = (
    "O Windows não encontrou o serviço de dispositivos móveis da Apple. Instale o "
    "aplicativo 'Dispositivos Apple' (Microsoft Store) ou o iTunes, conecte o iPhone e "
    "tente de novo."
)


class ErroIOS(Exception):
    """
    Falha de comunicação com o iPhone — a mensagem diz o que fazer.

    `original` guarda a resposta crua do aparelho quando a mensagem é uma
    tradução: o que o iPhone disse é evidência e vai para o log da aquisição.
    """

    def __init__(self, mensagem: str, original: str = ""):
        super().__init__(mensagem)
        self.original = original


# Recusas do serviço de backup do iOS (MBErrorDomain) que já foram vistas em
# aparelho real. Código desconhecido não é adivinhado: sai a resposta crua.
RECUSAS_DE_BACKUP = {
    212: (
        "O iPhone recusou o backup porque a configuração inicial do aparelho não foi "
        "concluída (código 212). No iPhone, abra Ajustes, toque em 'Concluir configuração "
        "do iPhone' e vá até o fim; depois repita a aquisição."
    ),
}


def _resposta_crua(erro: Exception) -> str:
    """O texto do erro sem o convite da biblioteca a abrir chamado no GitHub."""
    texto = str(erro)
    corte = texto.find("Please report it at")
    if corte != -1:
        texto = texto[:corte]
    return " ".join(texto.split()).rstrip(" .")


def _codigo_da_recusa(erro: Exception) -> Optional[int]:
    import re

    achado = re.search(r"'ErrorCode':\s*(\d+)", str(erro))
    return int(achado.group(1)) if achado else None


def _biblioteca():
    try:
        from pymobiledevice3 import usbmux
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service
    except ImportError as erro:
        raise ErroIOS(
            f"A biblioteca de comunicação com iPhone (pymobiledevice3) não está instalada "
            f"nesta estação ({erro})."
        ) from erro
    return usbmux, create_using_usbmux, Mobilebackup2Service


def _rodar(corotina):
    return asyncio.run(corotina)


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        return valor.hex()
    return str(valor)


class IOSClient:
    def __init__(self, udid: Optional[str] = None):
        self.udid = udid
        # Se a última leitura de `cifragem_ativa` veio do valor informado pelo
        # aparelho (`True`) ou da ausência dele (`False`). `None`: não lida.
        self.cifragem_informada: Optional[bool] = None

    def definir_udid(self, udid: Optional[str]) -> None:
        self.udid = udid

    # ------------------------------------------------------------------
    def listar_dispositivos(self) -> List[Tuple[str, str]]:
        """`(udid, tipo de conexão)` de cada iPhone visível. Levanta `ErroIOS`."""
        usbmux, _, _ = _biblioteca()
        try:
            dispositivos = _rodar(usbmux.list_devices())
        except Exception as erro:  # serviço da Apple ausente ou parado
            raise ErroIOS(f"{FALTA_O_SERVICO_DA_APPLE} ({type(erro).__name__}: {erro})") from erro
        return [(d.serial, str(getattr(d, "connection_type", "USB"))) for d in dispositivos]

    def verificar_disponibilidade(self) -> Tuple[bool, str]:
        try:
            dispositivos = [d for d in self.listar_dispositivos() if "USB" in d[1].upper()]
        except ErroIOS as erro:
            return False, str(erro)
        if not dispositivos:
            return False, (
                "Nenhum iPhone conectado por cabo. Conecte, desbloqueie a tela e, se "
                "aparecer a pergunta 'Confiar neste computador?', toque em Confiar."
            )
        if self.udid and self.udid not in {udid for udid, _ in dispositivos}:
            return False, (
                f"O iPhone '{self.udid}', vinculado a este caso, não está mais conectado."
            )
        if not self.udid and len(dispositivos) > 1:
            return False, "Há mais de um iPhone conectado. Deixe só o do exame."
        return True, ""

    def _udid_alvo(self) -> str:
        if self.udid:
            return self.udid
        dispositivos = [d for d in self.listar_dispositivos() if "USB" in d[1].upper()]
        if len(dispositivos) != 1:
            raise ErroIOS("Conecte exatamente um iPhone por cabo.")
        return dispositivos[0][0]

    async def _lockdown(self, udid: str):
        _, create_using_usbmux, _ = _biblioteca()
        try:
            return await create_using_usbmux(serial=udid, autopair=True)
        except Exception as erro:
            raise ErroIOS(
                "O iPhone não autorizou esta estação. Desbloqueie a tela e toque em "
                f"'Confiar' quando o iPhone perguntar ({type(erro).__name__}: {erro})."
            ) from erro

    def sondar(self) -> Tuple[List[str], Dict[str, str]]:
        """
        Tenta falar com o iPhone SEM pedir pareamento — para documentar um
        aparelho bloqueado sem alterá-lo.

        Devolve `(linhas do registro, valores públicos)`. Sem pareamento o
        iOS ainda informa alguns valores (modelo, versão); a recusa do
        restante fica registrada com o texto do erro.
        """
        linhas: List[str] = []
        try:
            dispositivos = self.listar_dispositivos()
        except ErroIOS as erro:
            return [f"listagem de dispositivos: FALHOU — {erro}"], {}
        linhas.append(f"listagem de dispositivos: {len(dispositivos)} iPhone(s) visível(is)")
        for udid, conexao in dispositivos:
            linhas.append(f"  {udid} ({conexao})")
        usb = [udid for udid, conexao in dispositivos if "USB" in conexao.upper()]
        if len(usb) != 1:
            return linhas, {}
        _, create_using_usbmux, _ = _biblioteca()

        async def ler():
            lockdown = await create_using_usbmux(serial=usb[0], autopair=False)
            try:
                pareado = bool(getattr(lockdown, "paired", False))
                try:
                    valores = await lockdown.get_value()
                except Exception as erro:
                    valores = {"_erro": f"{type(erro).__name__}: {erro}"}
                return pareado, valores
            finally:
                await lockdown.close()

        try:
            pareado, valores = _rodar(ler())
        except Exception as erro:
            linhas.append(f"sessão sem pareamento: RECUSADA — {type(erro).__name__}: {erro}")
            return linhas, {}
        linhas.append(
            "sessão sem pareamento: aberta; o iPhone "
            + ("JÁ confia nesta estação" if pareado else "NÃO confia nesta estação")
        )
        if "_erro" in (valores or {}):
            linhas.append(f"consulta de valores: RECUSADA — {valores['_erro']}")
            return linhas, {}
        publicos = {chave: _texto(valor) for chave, valor in (valores or {}).items()
                    if not isinstance(valor, (dict, list))}
        for chave in sorted(publicos):
            linhas.append(f"  {chave}: {publicos[chave]}")
        return linhas, publicos

    # ------------------------------------------------------------------
    def informacoes(self) -> Dict[str, str]:
        """Valores que o iOS informa de si mesmo (modelo, versão, série, IMEI...)."""
        udid = self._udid_alvo()

        async def ler():
            lockdown = await self._lockdown(udid)
            try:
                valores = await lockdown.get_value()
                try:
                    valores["WillEncrypt"] = await lockdown.get_value(DOMINIO_DE_BACKUP, "WillEncrypt")
                except Exception:
                    pass
                return valores
            finally:
                await lockdown.close()

        valores = _rodar(ler()) or {}
        return {chave: _texto(valor) for chave, valor in valores.items()
                if not isinstance(valor, (dict, list))}

    def cifragem_ativa(self) -> bool:
        """
        `True` se o iPhone está configurado para cifrar o backup (senha definida).

        Aparelho em que nunca se definiu senha de backup não tem o valor
        `WillEncrypt` (medido num iPhone 11 com iOS 18.6.2): a ausência é o
        estado de fábrica, sem senha, e devolve `False`. Fica anotada em
        `cifragem_informada`, para quem chama registrar que a resposta veio da
        ausência do valor — o `Manifest.plist` do backup confirma depois.
        """
        udid = self._udid_alvo()
        from pymobiledevice3.exceptions import MissingValueError

        async def ler():
            lockdown = await self._lockdown(udid)
            try:
                try:
                    valor = await lockdown.get_value(DOMINIO_DE_BACKUP, "WillEncrypt")
                except MissingValueError:
                    self.cifragem_informada = False
                    return False
                self.cifragem_informada = True
                return bool(valor)
            finally:
                await lockdown.close()

        try:
            return _rodar(ler())
        except ErroIOS:
            raise
        except Exception as erro:
            raise ErroIOS(f"O iPhone não informou se cifra o backup ({erro}).") from erro

    def alterar_senha_de_backup(self, antiga: str = "", nova: str = "") -> None:
        """
        Liga (só `nova`), troca ou desliga (só `antiga`) a senha de backup.

        É ALTERAÇÃO DE CONFIGURAÇÃO do aparelho, e o iOS pede o código de
        desbloqueio na tela para aceitá-la.
        """
        udid = self._udid_alvo()
        _, _, Mobilebackup2Service = _biblioteca()

        async def executar():
            lockdown = await self._lockdown(udid)
            try:
                with tempfile.TemporaryDirectory(prefix="forense_ios_senha_") as pasta:
                    async with Mobilebackup2Service(lockdown) as servico:
                        await servico.change_password(backup_directory=Path(pasta),
                                                      old=antiga, new=nova)
            finally:
                await lockdown.close()

        try:
            _rodar(executar())
        except ErroIOS:
            raise
        except Exception as erro:
            raise ErroIOS(
                f"O iPhone não aceitou a alteração da senha de backup ({type(erro).__name__}: "
                f"{erro})."
            ) from erro

    def fazer_backup(
        self,
        destino: Path,
        progresso: Optional[Callable[[float], None]] = None,
    ) -> Path:
        """
        Faz o backup completo do iPhone em `destino/<udid>/` e devolve essa pasta.

        É o backup local do próprio iOS: o aparelho decide o que entra. Se o
        dono ativou a criptografia do backup, o backup sai cifrado, e a suíte
        não o abre sem a senha.
        """
        udid = self._udid_alvo()
        _, _, Mobilebackup2Service = _biblioteca()
        Path(destino).mkdir(parents=True, exist_ok=True)

        async def executar():
            lockdown = await self._lockdown(udid)
            try:
                async with Mobilebackup2Service(lockdown) as servico:
                    await servico.backup(
                        full=True,
                        backup_directory=Path(destino),
                        progress_callback=progresso or (lambda _: None),
                    )
            finally:
                await lockdown.close()

        try:
            _rodar(executar())
        except ErroIOS:
            raise
        except Exception as erro:
            original = f"{type(erro).__name__}: {_resposta_crua(erro)}"
            explicacao = RECUSAS_DE_BACKUP.get(_codigo_da_recusa(erro))
            if explicacao:
                raise ErroIOS(explicacao, original) from erro
            raise ErroIOS(f"O backup do iPhone falhou ({original}).", original) from erro
        return Path(destino) / udid
