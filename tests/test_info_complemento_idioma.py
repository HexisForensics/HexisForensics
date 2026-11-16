"""
Fase 3 — informacoes_caso.txt e os complementos ao caso saem no idioma
carimbado no caso. São texto humano (não são relidos como chave), mas são
parte do dossiê selado e devem falar a língua da perícia.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.idioma import definir_idioma  # noqa: E402
from services.case_service import CaseService  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    definir_idioma("en")
    try:
        servico = CaseService(raiz)
        pasta = servico.abrir_caso("Android", "CASE_EN", "SERIAL-ENX")
        caso = pasta.parent
        info = (pasta / "informacoes_caso.txt").read_text(encoding="utf-8")
        print("\n[1] informacoes_caso.txt em inglês")
        checar("título em inglês", "CASE INFORMATION" in info)
        checar("rótulo device em inglês", "Device identifier:" in info)
        checar("serial no arquivo", "SERIAL-ENX" in info)

        servico.juntar_complemento(caso, "Court reference", "sheets 145/147")
        comp = sorted((caso / "complementos").glob("*.txt"))
        texto = comp[0].read_text(encoding="utf-8") if comp else ""
        indice = (caso / "complementos" / "INDICE.txt")
        idx = indice.read_text(encoding="utf-8") if indice.exists() else ""
        print("\n[2] complemento em inglês")
        checar("título do complemento em inglês", "AMENDMENT TO THE CASE" in texto)
        checar("assunto em inglês", "Subject:   Court reference" in texto)
        checar("ressalva em inglês", "does NOT alter the already sealed" in texto)
        checar("índice em inglês", "Index of this case's amendments" in idx)
    finally:
        definir_idioma("pt")

    print("\n[3] português — inalterado")
    servico_pt = CaseService(raiz)
    pasta_pt = servico_pt.abrir_caso("Android", "CASE_PT", "SERIAL-PTX")
    caso_pt = pasta_pt.parent
    info_pt = (pasta_pt / "informacoes_caso.txt").read_text(encoding="utf-8")
    checar("título em português", "INFORMAÇÕES DO CASO" in info_pt)
    checar("rótulo em português", "Identificador do Dispositivo:" in info_pt)
    servico_pt.juntar_complemento(caso_pt, "Retificação", "Onde se lê X, leia-se Y.")
    comp_pt = sorted((caso_pt / "complementos").glob("*.txt"))
    texto_pt = comp_pt[0].read_text(encoding="utf-8")
    checar("complemento em português", "COMPLEMENTO AO CASO" in texto_pt)
    checar("ressalva em português", "NÃO altera as aquisições já seladas" in texto_pt)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
