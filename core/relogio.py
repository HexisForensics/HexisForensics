"""
Desvio do relógio do aparelho: por extenso, com alerta e lido de volta do registro.

Um Galaxy A22 sem chip chegou ao exame marcando 9 de maio de 2025, com a
estação em 30 de outubro de 2026. A suíte mediu e registrou o desvio — como
"46588884s atrasado", sem alerta, só no registro do procedimento. Toda data
que esse aparelho grava (fotos, arquivos, o próprio bugreport) está deslocada
em um ano e meio, e quem lê o relatório sem saber disso data errado o
material. O desvio passa a ser dito por extenso, alertado acima de um limite
e levado ao Relatório de Extração e ao laudo.

A fonte é uma só: a linha "Desvio:" que a aquisição grava no registro do
procedimento, sob o selo. Os documentos a leem de volta daqui.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Acima disto o desvio deixa de ser imprecisão de relógio e passa a mudar a
# leitura das datas (dois minutos já desalinham a ordem de eventos próximos).
LIMITE_DE_DESVIO_SEGUNDOS = 120


def por_extenso(segundos: int) -> str:
    """`46588884` → "539 dias, 5 h e 21 min"; sem sinal."""
    segundos = abs(int(segundos))
    if segundos < 60:
        return f"{segundos} s"
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    partes = []
    if dias:
        partes.append(f"{dias} dia" + ("s" if dias != 1 else ""))
    if horas:
        partes.append(f"{horas} h")
    if minutos:
        partes.append(f"{minutos} min")
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]


def descrever_desvio(segundos: int) -> str:
    """O texto da linha "Desvio:" — por extenso, com os segundos exatos ao lado."""
    if segundos == 0:
        return "nenhum"
    sentido = "adiantado" if segundos > 0 else "atrasado"
    return f"{por_extenso(segundos)} {sentido} ({segundos:+d} s)"


def e_relevante(segundos: Optional[int]) -> bool:
    return segundos is not None and abs(segundos) > LIMITE_DE_DESVIO_SEGUNDOS


def alerta(segundos: Optional[int]) -> str:
    """Frase de alerta, ou `""` quando o desvio está dentro do limite."""
    if not e_relevante(segundos):
        return ""
    sentido = "adiantado" if segundos > 0 else "atrasado"
    return (
        f"O relógio do aparelho estava {por_extenso(segundos)} {sentido} em relação à "
        "estação forense no momento da aquisição. As datas registradas pelo próprio "
        "aparelho (arquivos, fotos, registros do sistema) estão deslocadas nessa medida e "
        "devem ser lidas com essa correção."
    )


def ler_desvio_registrado(texto_do_registro: str) -> Optional[int]:
    """
    O desvio em segundos, lido da linha "Desvio:" do registro do procedimento.

    Entende o formato atual ("... (-46588884 s)") e o anterior
    ("46588884s atrasado"). Relógio não lido, ou linha ausente: `None`.
    """
    for linha in texto_do_registro.splitlines():
        if "Desvio:" not in linha:
            continue
        trecho = linha.split("Desvio:", 1)[1]
        atual = re.search(r"\(([+-]?\d+) s\)", trecho)
        if atual:
            return int(atual.group(1))
        antigo = re.search(r"(\d+)s (adiantado|atrasado)", trecho)
        if antigo:
            valor = int(antigo.group(1))
            return valor if antigo.group(2) == "adiantado" else -valor
        if trecho.strip().startswith("nenhum"):
            return 0
    return None


def desvio_da_aquisicao(pasta_aquisicao: Path) -> Optional[int]:
    from core.procedimento import NOME_ARQUIVO

    arquivo = Path(pasta_aquisicao) / NOME_ARQUIVO
    if not arquivo.is_file():
        return None
    return ler_desvio_registrado(arquivo.read_text(encoding="utf-8", errors="replace"))
