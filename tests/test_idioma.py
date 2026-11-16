"""
Testes da camada de idioma (Fase 0 da internacionalização).

O que estes testes PROVAM, antes de qualquer tradução existir:

1. O mecanismo devolve, em português, exatamente os textos de hoje.
2. O princípio-raiz: traduz-se o MOLDE, nunca o VALOR. A evidência injetada
   (IMEI, hash, caminho) sai literal — mesmo contendo chaves ou caracteres
   de formatação, não é reinterpretada. É o que garante que trocar de idioma
   nunca toca na prova.
3. Degradação segura: chave faltando não estoura; molde sem o campo não
   estoura. Uma coleta em andamento não para por causa de texto.
4. A reexportação em `services.idioma` é a MESMA função de `core.idioma`.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import idioma
from core.idioma import (
    IDIOMA_PADRAO,
    definir_idioma,
    idioma_ativo,
    idiomas_disponiveis,
    traduzir,
)
from services import idioma as idioma_servico

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def _recusou(acao) -> bool:
    """True se `acao` levantou exceção — usado para provar que algo é recusado."""
    try:
        acao()
    except Exception:
        return True
    return False


# ---------------------------------------------------------------------------
print("\n[1] Estado inicial e disponibilidade")
# ---------------------------------------------------------------------------
checar("o idioma ativo começa em português", idioma_ativo() == "pt")
checar("o padrão é 'pt'", IDIOMA_PADRAO == "pt")
checar("o português está disponível", "pt" in idiomas_disponiveis())

# ---------------------------------------------------------------------------
print("\n[2] Em português, o texto é exatamente o de hoje")
# ---------------------------------------------------------------------------
checar("título da cadeia", traduzir("cadeia_titulo") == "CADEIA DE CUSTÓDIA")
checar("rótulo de campo (Lacre)", traduzir("campo_lacre") == "Lacre")
checar("rótulo de campo (Solicitante)", traduzir("campo_solicitante") == "Solicitante")
checar("'não informado' é idêntico", traduzir("cadeia_nao_informado") == "não informado")
checar(
    "aviso de ausência de manifesto é idêntico",
    traduzir("pdf_sem_manifesto")
    == "Aquisição SEM manifesto de integridade — nada se afirma sobre a preservação.",
)

# ---------------------------------------------------------------------------
print("\n[3] Molde + valor: a evidência é injetada, nunca traduzida")
# ---------------------------------------------------------------------------
checar("IMEI simples", traduzir("rotulo_imei", valor="350123456789012") == "IMEI: 350123456789012")
checar(
    "rodapé de página com dois campos",
    traduzir("pdf_pagina_de", n=3, total=7) == "Página 3 de 7",
)
checar(
    "SHA-256 do manifesto injetado",
    traduzir("pdf_selo_manifesto", selo="a" * 64) == "SHA-256 do manifesto: " + "a" * 64,
)
checar(
    "rodapé 'gerado em' injeta a data literal",
    traduzir("pdf_gerado_em", quando="16/11/2026 09:30:00 -0300")
    == "gerado em 16/11/2026 09:30:00 -0300",
)

# O ponto crítico: um VALOR que contém chaves NÃO é reinterpretado como molde.
checar(
    "valor com chaves sai literal (não vira outro campo)",
    traduzir("rotulo_imei", valor="{campo_solicitante}") == "IMEI: {campo_solicitante}",
)
checar(
    "valor com caracteres de formatação sai literal",
    traduzir("rotulo_imei", valor="89%s{0}{{}}") == "IMEI: 89%s{0}{{}}",
)
# Um valor nunca é olhado no catálogo: mesmo que fosse uma chave existente,
# ele entra como texto, não como tradução.
checar(
    "valor igual a uma chave do catálogo NÃO é traduzido",
    traduzir("rotulo_imei", valor="cadeia_titulo") == "IMEI: cadeia_titulo",
)

# ---------------------------------------------------------------------------
print("\n[4] Degradação segura (nunca estoura no meio de uma coleta)")
# ---------------------------------------------------------------------------
checar(
    "chave inexistente devolve a própria chave, sem erro",
    traduzir("chave_que_nao_existe_jamais") == "chave_que_nao_existe_jamais",
)
checar(
    "molde que pede campo não fornecido devolve o molde cru, sem erro",
    traduzir("rotulo_imei") == "IMEI: {valor}",
)

# ---------------------------------------------------------------------------
print("\n[5] Idioma explícito e troca do idioma ativo")
# ---------------------------------------------------------------------------
checar("idioma explícito 'pt' funciona", traduzir("campo_cor", idioma="pt") == "Cor")
checar(
    "idioma indisponível é recusado",
    _recusou(lambda: definir_idioma("klingon")),
)
checar("após recusa, o ativo continua 'pt'", idioma_ativo() == "pt")

# ---------------------------------------------------------------------------
print("\n[6] services.idioma é a MESMA função de core.idioma")
# ---------------------------------------------------------------------------
checar(
    "a reexportação aponta para a mesma função",
    idioma_servico.traduzir is idioma.traduzir,
)
checar(
    "e produz o mesmo resultado",
    idioma_servico.traduzir("campo_lacre") == "Lacre",
)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
