"""PT idêntico em ConversasDialog e ExtractionPanel após a migração."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.conversas_dialog import ConversasDialog  # noqa: E402
from ui.widgets.extraction_panel import ExtractionPanel  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


print("\n[1] ConversasDialog")
with tempfile.TemporaryDirectory() as td:
    aq = Path(td) / "CASO_1" / "android_x"
    aq.mkdir(parents=True)
    dlg = ConversasDialog(aq)
    igual("título", dlg.windowTitle(), "PDF de conversas — CASO_1 · android_x")
    igual("placeholder filtro", dlg.campo_filtro.placeholderText(),
          "Filtrar por número, nome ou via…")
    igual("botão gerar", dlg.botao_gerar.text(), "📄 Gerar PDF das selecionadas")
    igual("cabeçalho Via", dlg.tabela.horizontalHeaderItem(1).text(), "Via")
    igual("cabeçalho Conversa", dlg.tabela.horizontalHeaderItem(2).text(), "Conversa / número")
    igual("cabeçalho Período", dlg.tabela.horizontalHeaderItem(5).text(), "Período")

print("\n[2] ExtractionPanel")
ep = ExtractionPanel([])
igual("título padrão", ep.title(), "Tipos de Extração")
igual("botão marcar todos", ep.botao_marcar_todos.text(), "Marcar todos")
igual("botão desmarcar todos", ep.botao_desmarcar_todos.text(), "Desmarcar todos")
igual("resumo vazio", ep.rotulo_resumo.text(), "<b>Nenhum módulo marcado.</b>")

print("\n[moldes]")
igual("contagem de conversas", traduzir("cv_contagem", n=2, total=5, m=37),
      "<b>2</b> de 5 conversas selecionadas — 37 mensagem(ns) no PDF.")
igual("resumo de módulos", traduzir("xp_marcados", n=3, total=13, lista="SMS · WhatsApp"),
      "<b>3 de 13 módulos marcados:</b> SMS · WhatsApp")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
