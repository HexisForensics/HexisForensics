"""
Registro central de extratores, por plataforma.

Este módulo é o que torna a arquitetura de extração verdadeiramente
escalável: cada extrator concreto se registra automaticamente através do
decorator `@registrar_extrator`, aplicado à própria classe. A descoberta
dos módulos dentro de cada pacote `extractors/` é automática
(`descobrir_extratores`), então adicionar um novo tipo de extração no
futuro (ex.: Telegram, e-mails) é só criar o arquivo dentro de
`core/android/extractors/` ou `core/ios/extractors/` com a classe
decorada — nenhuma lista manual, nenhum outro arquivo (nem a GUI)
precisa ser tocado.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Dict, List, Type

from .base_extractor import BaseExtractor, Plataforma

_REGISTRO: Dict[Plataforma, List[Type[BaseExtractor]]] = {
    Plataforma.ANDROID: [],
    Plataforma.IOS: [],
    Plataforma.COMPUTADOR: [],
}


def registrar_extrator(classe: Type[BaseExtractor]) -> Type[BaseExtractor]:
    """
    Decorator de classe: registra o extrator na plataforma declarada em
    `classe.plataforma`. Uso:

        @registrar_extrator
        class MeuNovoExtrator(AndroidExtractor):
            id = "android_meu_novo"
            ...
    """
    if classe.plataforma not in _REGISTRO:
        raise ValueError(
            f"Plataforma não reconhecida para '{classe.__name__}': {classe.plataforma!r}. "
            "Defina o atributo de classe 'plataforma' com Plataforma.ANDROID ou Plataforma.IOS."
        )
    if classe not in _REGISTRO[classe.plataforma]:
        _REGISTRO[classe.plataforma].append(classe)
    return classe


def descobrir_extratores(pacote_extractors: ModuleType) -> None:
    """
    Importa todos os módulos dentro de um pacote `extractors`, disparando
    os decorators `@registrar_extrator` de cada um. Chamado uma única vez,
    a partir do `__init__.py` de `core.android` e `core.ios`.
    """
    for info_modulo in pkgutil.iter_modules(pacote_extractors.__path__, pacote_extractors.__name__ + "."):
        importlib.import_module(info_modulo.name)


def listar_extratores(plataforma: Plataforma) -> List[Type[BaseExtractor]]:
    """Retorna os extratores registrados para `plataforma`, ordenados para exibição."""
    extratores = list(_REGISTRO.get(plataforma, []))
    extratores.sort(key=lambda classe: (getattr(classe, "ordem", 100), classe.nome_exibicao))
    return extratores
