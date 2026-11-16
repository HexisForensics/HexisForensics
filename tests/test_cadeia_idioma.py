"""
Fase 3 — a cadeia de custódia é SELADA no idioma carimbado no caso, e lida
de volta por esse idioma. O risco que este teste trava: escrever a cadeia em
inglês e, por ler os campos pelo rótulo português, devolver lacre/equipamento
VAZIOS no laudo — uma conclusão negativa falsa, o pior defeito da ferramenta.

Prova a ida e volta: escreve em inglês, lê em inglês (lacre e equipamento
chegam ao laudo), e o português e o selado antigo (sem carimbo) continuam
lidos como português.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core.case import idioma_do_caso  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from core.idioma import definir_idioma  # noqa: E402
from services import laudo_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402
from services.dossie_service import montar_dossie  # noqa: E402

_app = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def texto_do_pdf(caminho):
    doc = QPdfDocument()
    doc.load(str(caminho))
    return "\n".join(doc.getAllText(p).text() for p in range(doc.pageCount()))


def montar(raiz, caso, idioma, modelo, lacre, momento):
    servico = CaseService(raiz)
    pasta = servico.abrir_caso("Android", caso, "SERIAL-" + lacre)
    servico.abrir_registro_procedimento(pasta, caso, "Android", "SERIAL-" + lacre)
    servico.registrar_operador(pasta, {"nome": "Jane Examiner", "funcao": "Examiner"})
    servico.registrar_ambiente("1.0.41")
    servico.gravar_dados_do_caso(caso, {"referencia": "Ref-" + lacre, "descricao": "Test"})
    servico.gravar_cadeia_custodia(pasta, caso, {"marca_modelo": modelo, "lacre": lacre})
    servico.encerrar_registro_procedimento("1 module(s).")
    gerar_manifesto(pasta)
    return pasta


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    # --- INGLÊS: carimbo, selado em inglês, leitura certa -------------------
    definir_idioma("en")
    try:
        pasta_en = montar(raiz, "CASE_EN", "en", "Galaxy A22", "L-EN-1",
                          datetime(2026, 9, 1, 10, 0, 0))
        bruto = (pasta_en / "cadeia_custodia.txt").read_text(encoding="utf-8")
        print("\n[1] Cadeia SELADA em inglês")
        checar("caso.json carimba idioma=en", idioma_do_caso(pasta_en) == "en")
        checar("título em inglês", "=== CHAIN OF CUSTODY ===" in bruto)
        checar("rótulo da peça em inglês", "Equipment: Galaxy A22" in bruto)
        checar("lacre em inglês", "Seal: L-EN-1" in bruto)
        checar("caso em inglês", "Case: CASE_EN" in bruto)
        checar("fotos em inglês", "Attached photos: none" in bruto)

        print("\n[2] Leitura de volta — lacre e equipamento NÃO ficam vazios")
        dossie = montar_dossie(pasta_en)
        checar("equipamento lido", dossie.equipamento == "Galaxy A22")
        checar("lacre lido", dossie.lacre == "L-EN-1")
        checar("peça com rótulo em inglês", ("Seal", "L-EN-1") in dossie.peca)
        rotulos_caso = [r for r, _ in dossie.dados_do_caso]
        checar("dados do caso não engolem a peça", "Seal" not in rotulos_caso
               and "Equipment" not in rotulos_caso and "Case" not in rotulos_caso)

        print("\n[3] O laudo em inglês mostra o lacre e o equipamento")
        laudo = laudo_service.gerar(pasta_en, {"numero": "7"},
                                    {"nome": "Jane Examiner", "funcao": "Examiner"})
        checar("laudo gerado", laudo.caminho is not None)
        txt = texto_do_pdf(laudo.caminho) if laudo.caminho else ""
        checar("laudo traz o equipamento", "Galaxy A22" in txt)
        checar("laudo traz o lacre", "L-EN-1" in txt)
        checar("laudo traz o rótulo Seal", "Seal" in txt)
    finally:
        definir_idioma("pt")

    # --- PORTUGUÊS: byte igual ao de sempre, leitura certa -----------------
    pasta_pt = montar(raiz, "CASE_PT", "pt", "Moto X4", "L-PT-9",
                      datetime(2026, 9, 2, 10, 0, 0))
    bruto_pt = (pasta_pt / "cadeia_custodia.txt").read_text(encoding="utf-8")
    print("\n[4] Cadeia em português — inalterada")
    checar("título em português", "=== CADEIA DE CUSTÓDIA ===" in bruto_pt)
    checar("lacre em português", "Lacre: L-PT-9" in bruto_pt)
    dossie_pt = montar_dossie(pasta_pt)
    checar("equipamento lido (pt)", dossie_pt.equipamento == "Moto X4")
    checar("lacre lido (pt)", dossie_pt.lacre == "L-PT-9")

    # --- LEGADO: cadeia PT sem carimbo no caso.json ------------------------
    print("\n[5] Selado antigo (sem carimbo) é lido como português")
    legado = raiz / "CASE_LEGADO" / "android_20260101_120000"
    legado.mkdir(parents=True)
    (legado / "cadeia_custodia.txt").write_text(
        "=== CADEIA DE CUSTÓDIA ===\nCaso: CASE_LEGADO\nReferência: R\n\n"
        "Equipamento: iPhone 8\nCor: preto\nEstado: bom\nLacre: L-VELHO\n"
        "Fotos Anexas: nenhuma\n", encoding="utf-8")
    checar("legado assume português", idioma_do_caso(legado) == "pt")
    dossie_legado = montar_dossie(legado)
    checar("equipamento legado lido", dossie_legado.equipamento == "iPhone 8")
    checar("lacre legado lido", dossie_legado.lacre == "L-VELHO")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
