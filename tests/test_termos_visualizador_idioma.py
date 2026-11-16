"""PT idêntico em TermosDialog (termos de uso) e VisualizadorPdf após a migração."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from ui.widgets.termos_dialog import TermosDialog  # noqa: E402
from ui.widgets.visualizador_pdf import VisualizadorPdf  # noqa: E402

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


print("\n[1] TermosDialog")
td = TermosDialog(para_aceitar=True, nome="Ana")
igual("título", td.windowTitle(), "Termos de uso")
botoes = [b.text() for b in td.findChildren(QPushButton)]
entre("botão não aceito", "Não aceito", botoes)
entre("botão eu aceito", "Eu aceito", botoes)
labels = [lbl.text() for lbl in td.findChildren(QLabel)]
entre("aviso com nome e sufixo",
      "<b>Ana</b>, antes de continuar, leia os termos de uso. "
      "O aceite é pessoal e fica no registro de acessos desta estação.", labels)

td2 = TermosDialog(para_aceitar=False)
entre("botão fechar (só consulta)", "Fechar", [b.text() for b in td2.findChildren(QPushButton)])

print("\n[2] VisualizadorPdf")
vp = VisualizadorPdf(Path("inexistente.pdf"))
igual("título", vp.windowTitle(), "inexistente.pdf — Hexis Forensics")
igual("rótulo de página", vp.rotulo_pagina.text(), "Página 1 de 1")
acoes = [a.text() for a in vp.findChildren(QAction)]
entre("ação anterior", "◀ Anterior", acoes)
entre("ação próxima", "Próxima ▶", acoes)
entre("ação imprimir", "🖨 Imprimir", acoes)
entre("ação salvar cópia (reusa gc_)", "💾 Salvar cópia em…", acoes)
entre("ação abrir externo", "Abrir no leitor do Windows", acoes)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
