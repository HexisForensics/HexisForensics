"""PT idêntico no ExaminadoresDialog após a migração para o catálogo."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from services import perfil_service  # noqa: E402
from ui.widgets.examinadores_dialog import ExaminadoresDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


def entre(nome, alvo, colecao):
    if alvo in colecao:
        print("  OK   " + nome)
    else:
        print(f" FALHA {nome}\n    não achei: {alvo!r}")
        falhas.append(nome)


with tempfile.TemporaryDirectory() as td:
    perfil_service.usar_perfil_em(Path(td) / "estacao")
    try:
        dlg = ExaminadoresDialog()
        igual("título", dlg.windowTitle(), "Examinadores")
        igual("botão salvar", dlg.botao_salvar.text(), "Salvar")
        igual("botão novo código", dlg.botao_codigo.text(), "Novo código de recuperação")
        igual("botão excluir", dlg.botao_excluir.text(), "Excluir examinador")
        textos = [b.text() for b in dlg.findChildren(QPushButton)]
        entre("botão novo examinador", "➕ Novo examinador", textos)
        entre("botão fechar", "Fechar", textos)
    finally:
        perfil_service.usar_perfil_em(None)

print("\n[moldes]")
igual("editando", traduzir("ex_editando", nome="Ana"), "<b>Editando:</b> Ana")
igual("nova senha (mín.)", traduzir("ex_nova_senha", min=8), "Nova senha (mín. 8)")
igual("excluir outro", traduzir("ex_excluir_outro", nome="Ana"),
      "Excluir o perfil de Ana desta estação?")
igual("código do cadastro", traduzir("ex_codigo_cadastro", nome="Ana", codigo="XX-YY"),
      "Código de recuperação de Ana:\n\n    XX-YY\n\nEntregue-o ao examinador. "
      "Ele não será mostrado de novo.")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
