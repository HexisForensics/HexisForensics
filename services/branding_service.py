"""
Serviço de identidade visual (branding).

Carrega um "perfil de marca" — nome de exibição, paleta de cores, logo e
ícone — a partir de um arquivo JSON simples em `branding/<perfil>/branding.json`.
É isso que permite a mesma base de código vestir a identidade visual de
empresas diferentes sem tocar em nenhum código da UI: trocar de marca é
trocar o campo "perfil" de `branding/active.json`, nunca editar
`ui/style.py` ou qualquer widget.

Este módulo não importa nada de `core` nem de `ui` — só lê arquivos e
monta um objeto de dados simples (`BrandConfig`). É a UI (`ui/style.py`)
quem sabe transformar essa configuração em QPalette/stylesheet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.instalacao import pasta_das_extracoes, raiz_da_instalacao

RAIZ_PROJETO = raiz_da_instalacao()
# Exposta aqui para a interface saber onde gravar os casos sem importar `core`.
PASTA_EXTRACOES = pasta_das_extracoes()
PASTA_BRANDING = RAIZ_PROJETO / "branding"
CAMINHO_PERFIL_ATIVO = PASTA_BRANDING / "active.json"
PERFIL_PADRAO = "default"

# Paleta embutida, usada como fallback caso nenhum arquivo de branding seja
# encontrado — a aplicação nunca falha ao iniciar por falta de um perfil.
_CORES_PADRAO = {
    "fundo": "#1b1e23",
    "fundo_alt": "#22262d",
    "fundo_entrada": "#12151a",
    "texto": "#e2e6ea",
    "texto_secundario": "#9aa4af",
    "destaque": "#3f8dfd",
    "borda": "#333a42",
    "texto_sobre_destaque": "#0b0d10",
}


@dataclass
class PaletaCores:
    fundo: str = _CORES_PADRAO["fundo"]
    fundo_alt: str = _CORES_PADRAO["fundo_alt"]
    fundo_entrada: str = _CORES_PADRAO["fundo_entrada"]
    texto: str = _CORES_PADRAO["texto"]
    texto_secundario: str = _CORES_PADRAO["texto_secundario"]
    destaque: str = _CORES_PADRAO["destaque"]
    borda: str = _CORES_PADRAO["borda"]
    texto_sobre_destaque: str = _CORES_PADRAO["texto_sobre_destaque"]


@dataclass
class BrandConfig:
    """Configuração de identidade visual de um perfil de marca."""

    nome_exibicao: str = "HexisForensics"
    modo: str = "dark"
    cores: PaletaCores = field(default_factory=PaletaCores)
    caminho_logo: Optional[Path] = None
    caminho_icone: Optional[Path] = None


def _resolver_caminho_opcional(pasta_perfil: Path, nome_arquivo: Optional[str]) -> Optional[Path]:
    if not nome_arquivo:
        return None
    caminho = pasta_perfil / nome_arquivo
    return caminho if caminho.exists() else None


def obter_perfil_ativo() -> str:
    """
    Lê `branding/active.json` para saber qual perfil de marca está em uso —
    ex.: `{"perfil": "exemplo_empresa"}`. Trocar de identidade visual é só
    editar esse campo, sem precisar de variável de ambiente nem reinstalar
    nada. Arquivo ausente ou malformado cai silenciosamente para `default`.
    """
    if CAMINHO_PERFIL_ATIVO.exists():
        try:
            dados = json.loads(CAMINHO_PERFIL_ATIVO.read_text(encoding="utf-8"))
            perfil = dados.get("perfil")
            if perfil:
                return perfil
        except (json.JSONDecodeError, OSError):
            pass
    return PERFIL_PADRAO


def carregar_branding(nome_perfil: Optional[str] = None) -> BrandConfig:
    """
    Carrega um perfil de marca de `branding/<nome_perfil>/branding.json`.

    Se `nome_perfil` não for informado, resolve automaticamente qual usar
    via `obter_perfil_ativo()` (ou seja, `branding/active.json`). Se o
    perfil não existir, cai de volta ao perfil `default`; se nem esse
    existir (ex.: pasta `branding/` removida), retorna a paleta embutida —
    a aplicação sempre sobe com alguma identidade visual válida.
    """
    nome_perfil = nome_perfil or obter_perfil_ativo()
    pasta_perfil = PASTA_BRANDING / nome_perfil
    caminho_json = pasta_perfil / "branding.json"

    if not caminho_json.exists():
        if nome_perfil != PERFIL_PADRAO:
            return carregar_branding(PERFIL_PADRAO)
        return BrandConfig()

    dados = json.loads(caminho_json.read_text(encoding="utf-8"))
    cores_customizadas = dados.get("cores", {})
    cores = PaletaCores(**{**PaletaCores().__dict__, **cores_customizadas})

    return BrandConfig(
        nome_exibicao=dados.get("nome_exibicao", "HexisForensics"),
        modo=dados.get("modo", "dark"),
        cores=cores,
        caminho_logo=_resolver_caminho_opcional(pasta_perfil, dados.get("logo")),
        caminho_icone=_resolver_caminho_opcional(pasta_perfil, dados.get("icone")),
    )


def listar_perfis_disponiveis() -> List[str]:
    """Lista os nomes de perfis de marca disponíveis em `branding/`."""
    if not PASTA_BRANDING.exists():
        return [PERFIL_PADRAO]
    return sorted(
        pasta.name
        for pasta in PASTA_BRANDING.iterdir()
        if pasta.is_dir() and (pasta / "branding.json").exists()
    )
