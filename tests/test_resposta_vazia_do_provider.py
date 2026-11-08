"""
"No result found." é a resposta do próprio Android a uma consulta sem
registro. Samsung sem chip (31/10/2026): o Relatório de Conteúdo tratava a
frase como trecho ilegível e mandava "examinar o arquivo à mão".
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import normalizacao  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


leitores = {nome: getattr(normalizacao, nome) for nome in dir(normalizacao)
            if nome.startswith("normalizar_") and callable(getattr(normalizacao, nome))}
checar("há leitores de content query para testar", bool(leitores))

for nome, leitor in sorted(leitores.items()):
    try:
        resultado = leitor("No result found.\n", "sms/sms_todas.txt")
    except TypeError:
        continue
    checar(f"{nome}: resposta vazia não vira trecho ilegível",
           resultado.total == 0 and not resultado.descartes
           and "respondeu" in resultado.explicacao_do_vazio)

leitor = next(iter(sorted(leitores.items())))[1]
for texto, motivo in (("No result found.\nlixo depois", "com mais coisa depois"),
                      ("Error: No result found.", "dentro de outra frase")):
    try:
        resultado = leitor(texto, "x.txt")
    except TypeError:
        continue
    checar(f"a frase {motivo} continua sendo descarte, para exame", bool(resultado.descartes))

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
