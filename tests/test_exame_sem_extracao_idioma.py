"""
PT idêntico no ExameSemExtracaoDialog após a migração — e, sobretudo, a
prova de que a DATA não mudou: os combos e a recomendação (que viram
registro selado via dados()) continuam em português, só a moldura foi
traduzida.
"""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.exame_service import RECOMENDACAO_PADRAO  # noqa: E402
from ui.widgets.exame_sem_extracao_dialog import ExameSemExtracaoDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


dlg = ExameSemExtracaoDialog()
print("\n[1] Moldura em português idêntica")
igual("título", dlg.windowTitle(), "Exame sem extração")
igual("placeholder bateria", dlg.campo_bateria.placeholderText(),
      "Ex.: 45% / sem carga / não exibida")

print("\n[2] A DATA não foi tocada (continua canônica em PT)")
dados = dlg.dados()
igual("combo 'liga' devolve valor PT", dados["liga"], "Sim")
igual("combo 'estado' devolve valor PT", dados["estado_ao_receber"], "Ligado")
igual("recomendação padrão intacta", dados["recomendacao"], RECOMENDACAO_PADRAO)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
