"""
Plataforma COMPUTADOR (discos externos e desktops Windows).

Vive dentro de `core/`, lado a lado com `core/android/` e `core/ios/`, no
mesmo espírito: própria camada de acesso ao "dispositivo" (aqui,
`disk_client.py` — API do Windows via `ctypes`, sem dependência externa),
própria classe de fachada (`device.py`) e um pacote `extractors/` com um
módulo por tipo de extração.

Diferente do Android/iOS, não existe um único "dispositivo conectado":
o examinador escolhe qual unidade de disco (entre as detectadas pelo
Windows) será periciada. Ver `extractors/base.py` (`definir_unidade`).

`listar_extratores()` não mantém uma lista manual: os módulos dentro de
`extractors/` são descobertos e registrados automaticamente (ver
`core.registry`), então adicionar um novo tipo de extração no futuro é só
criar o arquivo lá dentro.
"""

from core.base_extractor import Plataforma
from core.registry import descobrir_extratores
from core.registry import listar_extratores as _listar_extratores

from . import extractors as _extractors_pkg
from .device import ComputadorDevice
from .disk_client import UnidadeDisco

descobrir_extratores(_extractors_pkg)


def listar_extratores():
    """Retorna a lista de classes de extratores de Computador, na ordem de exibição."""
    return _listar_extratores(Plataforma.COMPUTADOR)


__all__ = ["ComputadorDevice", "UnidadeDisco", "listar_extratores"]
