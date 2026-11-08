"""Termos de uso para a interface: o texto vem de `core.termos`, fonte única."""

from __future__ import annotations

from core import termos

VERSAO_DOS_TERMOS = termos.VERSAO_DOS_TERMOS


def html() -> str:
    return termos.html()


def texto() -> str:
    return termos.texto()
