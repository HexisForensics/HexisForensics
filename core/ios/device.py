"""
O iPhone do exame — contraparte de `core.android.device.AndroidDevice`.

Mesma interface (`verificar_conexao`, `obter_id_dispositivo`), para a
interface tratar Android e iPhone do mesmo jeito.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .client import ErroIOS, IOSClient


@dataclass
class StatusConexaoIOS:
    conectado: bool
    autorizado: bool
    identificador: Optional[str]
    mensagem: str


class IOSDevice:
    def __init__(self, client: Optional[IOSClient] = None):
        self.client = client or IOSClient()

    def verificar_conexao(self) -> StatusConexaoIOS:
        disponivel, motivo = self.client.verificar_disponibilidade()
        if not disponivel:
            return StatusConexaoIOS(False, False, None, motivo)
        try:
            valores = self.client.informacoes()
        except ErroIOS as erro:
            return StatusConexaoIOS(True, False, self.client.udid, str(erro))
        udid = valores.get("UniqueDeviceID", "")
        nome = valores.get("DeviceName", "iPhone")
        modelo = valores.get("ProductType", "")
        versao = valores.get("ProductVersion", "")
        return StatusConexaoIOS(
            True, True, udid,
            f"Conectado e autorizado: {nome} ({modelo}, iOS {versao}) — UDID {udid}",
        )

    def obter_id_dispositivo(self) -> str:
        try:
            return self.client._udid_alvo()
        except ErroIOS:
            from core.aparelho import ID_GENERICO_IOS

            return ID_GENERICO_IOS
