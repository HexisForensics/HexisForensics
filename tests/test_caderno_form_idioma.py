"""
PT idêntico no CadernoFormDialog (formulário do laudo) após a migração — e
a prova de que a RESPOSTA aos protocolos continua canônica em PT (ela vira
registro do laudo via obter_protocolos, independente do idioma da tela).
"""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton, QRadioButton  # noqa: E402

from ui.widgets.caderno_form_dialog import CADERNO, LAUDO, CadernoFormDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


def entre(nome, alvo, colecao):
    if any(alvo in x for x in colecao):
        print("  OK   " + nome)
    else:
        print(f" FALHA {nome}\n    não achei: {alvo!r}")
        falhas.append(nome)


DADOS_CASO = {"Referência": "123/2026"}
DADOS_DISP = {"Equipamento": "Galaxy", "Lacre": "L-1", "fotos": []}

print("\n[1] Finalidade LAUDO")
dlg = CadernoFormDialog(DADOS_CASO, DADOS_DISP, finalidade=LAUDO)
igual("título laudo", dlg.windowTitle(), "Dados para o Laudo Pericial")
grupos = [g.title() for g in dlg.findChildren(QGroupBox)]
entre("seção modalidade", "3. Modalidade de Acesso", grupos)
entre("seção protocolos", "4. Protocolos Periciais (ABNT NBR ISO/IEC 27037)", grupos)
entre("seção considerações", "5. Considerações do examinador", grupos)
radios = [r.text() for r in dlg.findChildren(QRadioButton)]
for opc in ("Sim", "Não", "Não se aplica"):
    entre(f"radio {opc}", opc, radios)
botoes = [b.text() for b in dlg.findChildren(QPushButton)]
entre("botão gerar laudo", "📄 Gerar Laudo Pericial (PDF)", botoes)

print("\n[2] A RESPOSTA é canônica em PT (dado do laudo)")
protocolos = dlg.obter_protocolos()
if protocolos and all(item[2] == "Não respondido" for item in protocolos):
    print("  OK   protocolos não respondidos devolvem 'Não respondido' (PT)")
else:
    print(f" FALHA resposta canônica: {[p[2] for p in protocolos][:3]}")
    falhas.append("resposta canônica PT")

print("\n[3] Finalidade CADERNO")
dlg2 = CadernoFormDialog(DADOS_CASO, DADOS_DISP, finalidade=CADERNO)
igual("título caderno", dlg2.windowTitle(), "Dados para o Caderno de Extração")
entre("botão gerar caderno", "💾 Salvar e Gerar Caderno",
      [b.text() for b in dlg2.findChildren(QPushButton)])

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
