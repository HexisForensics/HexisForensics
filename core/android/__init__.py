"""
Plataforma ANDROID.

Vive dentro de `core/`, lado a lado com `core/ios/`, já que toda a lógica
de extração (comum e específica de plataforma) foi centralizada no pacote
`core`. Mantém sua própria camada de comunicação com o dispositivo
(`adb_client.py`), classe de dispositivo (`device.py`) e um pacote
`extractors/` com um módulo por tipo de dado extraído.

`listar_extratores()` não mantém uma lista manual: os módulos dentro de
`extractors/` são descobertos e registrados automaticamente (ver
`core.registry`), então adicionar um novo tipo de extração Android no
futuro (ex.: Telegram) é só criar o arquivo lá dentro.
"""

from core.base_extractor import Plataforma
from core.registry import descobrir_extratores
from core.registry import listar_extratores as _listar_extratores

from . import extractors as _extractors_pkg
from .adb_client import ADBClient
from .device import AndroidDevice

descobrir_extratores(_extractors_pkg)


def listar_extratores():
    """Retorna a lista de classes de extratores Android, na ordem de exibição."""
    return _listar_extratores(Plataforma.ANDROID)


__all__ = ["ADBClient", "AndroidDevice", "listar_extratores"]
