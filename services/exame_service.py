"""
Ponte entre a interface e o exame sem extração (`core.exame_sem_extracao`).

A interface monta o formulário com as opções daqui e recebe o "módulo" de
registro pronto, sem importar nada de `core`.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import Plataforma
from core.exame_sem_extracao import (
    RECOMENDACAO_PADRAO,
    RESPOSTAS,
    TIPOS_DE_BLOQUEIO,
    ExameSemExtracao,
    ler_exame,
)
from services.device_service import IOS

__all__ = ["RECOMENDACAO_PADRAO", "RESPOSTAS", "TIPOS_DE_BLOQUEIO", "criar_registro",
           "e_exame_sem_extracao"]


def criar_registro(nome_plataforma: str, dados: dict) -> ExameSemExtracao:
    """O registro do exame, pronto para correr no `ExtractionService`."""
    plataforma = Plataforma.IOS if nome_plataforma == IOS else Plataforma.ANDROID
    return ExameSemExtracao(plataforma, dados)


def e_exame_sem_extracao(pasta_aquisicao: Path) -> bool:
    return ler_exame(Path(pasta_aquisicao)) is not None
