"""
Plataforma iOS.

Vive dentro de `core/`, lado a lado com `core/android/`, com a MESMA
estrutura interna (client de baixo nível, `device.py`, `extractors/`). A
comunicação é feita pelo `pymobiledevice3`, sobre o serviço de dispositivos
da Apple instalado no Windows.

Assim como em `core.android`, os extratores são descobertos e registrados
automaticamente a partir de `extractors/` — não há lista manual.
"""

from core.base_extractor import Plataforma
from core.registry import descobrir_extratores
from core.registry import listar_extratores as _listar_extratores

from . import extractors as _extractors_pkg
from .client import IOSClient
from .device import IOSDevice

descobrir_extratores(_extractors_pkg)


def listar_extratores():
    """Retorna a lista de classes de extratores iOS, na ordem de exibição."""
    return _listar_extratores(Plataforma.IOS)


__all__ = ["IOSClient", "IOSDevice", "listar_extratores"]
