"""
Camada de idioma da suíte — a fonte de todo texto voltado a pessoa.

PRINCÍPIO-RAIZ (ver a doutrina do projeto): traduz-se o MOLDE, nunca o VALOR.
O catálogo guarda ``"IMEI: {valor}"``; o IMEI, o hash, o caminho entram
depois, por ``campos``, e NUNCA passam pela tradução. Assim:

- trocar de idioma jamais toca na evidência — ela não está no catálogo;
- um valor que por acaso contenha chaves (``{...}``) ou caracteres de
  formatação é inserido literalmente, sem ser reinterpretado como molde
  (``str.format`` não reexamina o que foi substituído).

ONDE VIVE O QUÊ.
A implementação mora aqui, em ``core/``, porque o próprio ``core`` precisa
traduzir os rótulos dos documentos selados (cadeia de custódia, registro do
procedimento, manifesto) — e ``core`` não pode depender de ``services``. A
tela fala com ``services.idioma``, que só reexporta isto, para manter a
regra ``ui → services → core`` intacta. Este módulo é puro: não importa Qt.

IDIOMA ATIVO vs IDIOMA EXPLÍCITO.
Há um idioma ATIVO global, por conveniência da tela. Mas todo texto que vai
para DISCO — documento derivado, texto selado — deve receber o idioma por
parâmetro, explícito. Estado global e ``QThread`` não convivem sem corrida;
o que será gravado e selado não pode depender de quem trocou o idioma da
tela no meio do caminho.

FALTA DE CHAVE NUNCA DERRUBA UMA AQUISIÇÃO.
Chave ausente no idioma ativo cai para o português; ausente também no
português, devolve a própria chave em vez de estourar. É escolha forense:
uma coleta em andamento não pode ser interrompida por um texto faltando. A
completude do catálogo português é garantida pelos testes, não por sorte em
tempo de execução.
"""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from core.instalacao import raiz_da_instalacao

IDIOMA_PADRAO = "pt"

# Idiomas previstos pelo projeto, na ordem de apresentação. Estar previsto
# não é estar disponível: só conta quem tem catálogo em `idiomas/` (ver
# `idiomas_disponiveis`). Hoje só o português existe; inglês e espanhol
# entram como catálogos a mais, sem tocar neste código.
IDIOMAS_PREVISTOS: Tuple[Tuple[str, str], ...] = (
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
)

NOME_PASTA = "idiomas"

_idioma_ativo = IDIOMA_PADRAO
_catalogos: Dict[str, Dict[str, str]] = {}


def _caminho_catalogo(idioma: str):
    return raiz_da_instalacao() / NOME_PASTA / f"{idioma}.json"


def _carregar(idioma: str) -> Dict[str, str]:
    """Catálogo do idioma, lido do disco uma vez e guardado em memória."""
    if idioma in _catalogos:
        return _catalogos[idioma]
    caminho = _caminho_catalogo(idioma)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    _catalogos[idioma] = dados
    return dados


def idiomas_disponiveis() -> Tuple[str, ...]:
    """Códigos dos idiomas que têm catálogo no disco, na ordem prevista."""
    return tuple(cod for cod, _ in IDIOMAS_PREVISTOS if _caminho_catalogo(cod).is_file())


def nome_do_idioma(idioma: str) -> str:
    """Nome de apresentação (""Português""), ou o próprio código se não previsto."""
    for cod, nome in IDIOMAS_PREVISTOS:
        if cod == idioma:
            return nome
    return idioma


def idioma_ativo() -> str:
    return _idioma_ativo


def definir_idioma(idioma: str) -> None:
    """
    Troca o idioma ATIVO (o da tela). Recusa idioma sem catálogo, para a
    tela nunca ficar com texto pela metade.
    """
    global _idioma_ativo
    if idioma not in idiomas_disponiveis():
        raise ValueError(
            f"idioma '{idioma}' não tem catálogo em {NOME_PASTA}/ "
            f"(disponíveis: {', '.join(idiomas_disponiveis()) or 'nenhum'})"
        )
    _idioma_ativo = idioma


def _molde(chave: str, idioma: str) -> str:
    cat = _carregar(idioma)
    if chave in cat:
        return cat[chave]
    if idioma != IDIOMA_PADRAO:
        base = _carregar(IDIOMA_PADRAO)
        if chave in base:
            return base[chave]
    # Último recurso: a chave crua. Nunca estoura uma aquisição.
    return chave


def traduzir(chave: str, idioma: Optional[str] = None, **campos) -> str:
    """
    Texto de ``chave`` no idioma dado (ou no ativo), com ``campos`` injetados.

    Os ``campos`` são DADO — valores capturados, nomes, números. São inseridos
    no molde por ``str.format`` e não são reinterpretados: um valor com
    ``{...}`` sai literal. Se o molde pedir um campo que não veio, devolve o
    molde cru em vez de estourar — a falha é de programação, pega nos testes,
    e não pode derrubar uma coleta.
    """
    molde = _molde(chave, idioma or _idioma_ativo)
    if not campos:
        return molde
    try:
        return molde.format(**campos)
    except (KeyError, IndexError):
        return molde


def recarregar() -> None:
    """Esquece os catálogos em memória (para teste, ou após editar um .json)."""
    _catalogos.clear()
