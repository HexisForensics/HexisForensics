"""
Reexportação da camada de idioma para a tela.

A implementação mora em ``core.idioma`` (pura, sem Qt, porque o próprio
``core`` traduz os rótulos dos documentos selados). A tela, porém, só pode
falar com ``services`` — regra ``ui → services → core``. Este módulo é a
ponte: a ``ui`` importa ``services.idioma`` e a regra fica intacta, ao custo
de uma linha de encaminhamento. Nada de lógica aqui; se precisar de lógica,
ela nasce em ``core.idioma``.
"""

from __future__ import annotations

from core.case import idioma_para_selar  # noqa: F401  (reexport proposital)
from core.idioma import (  # noqa: F401  (reexport proposital)
    IDIOMA_PADRAO,
    IDIOMAS_PREVISTOS,
    aplicar_idioma_salvo,
    definir_e_salvar,
    definir_idioma,
    idioma_ativo,
    idioma_salvo,
    idiomas_disponiveis,
    nome_do_idioma,
    traduzir,
)
