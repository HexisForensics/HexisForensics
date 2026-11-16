"""PT idêntico no EntregaDialog (exportar para entrega) após a migração."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.entrega_dialog import EntregaDialog  # noqa: E402

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


dlg = EntregaDialog(Path("CASO_1/android_x"), material=["a", "b"], documentos=[Path("x.pdf")])
igual("título", dlg.windowTitle(), "Exportar para entrega")
igual("placeholder destino", dlg.campo_destino.placeholderText(),
      "Pendrive ou pasta onde a entrega será gravada")
igual("placeholder finalidade", dlg.campo_finalidade.placeholderText(),
      "Ex.: entregue ao Juízo da 1ª Vara — Proc. 123/2026")

textos_botoes = [b.text() for b in dlg.findChildren(QPushButton)]
entre("botão exportar", "📤 Exportar", textos_botoes)
entre("botão escolher", "Escolher…", textos_botoes)

textos_labels = [lbl.text() for lbl in dlg.findChildren(QLabel)]
entre("explicação com partes juntadas por ' e '",
      "2 item(ns) do material e 1 documento(s) da aquisição <b>android_x</b>", textos_labels)

print("\n[moldes]")
igual("mensagem de entrega", traduzir("eg_mensagem", n=3, pasta="D:/ENTREGA"),
      "3 arquivo(s) entregue(s), cada um conferido pelo SHA-256.\n\n"
      "Pasta da entrega:\nD:/ENTREGA\n\nA entrega foi registrada no caso.")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
