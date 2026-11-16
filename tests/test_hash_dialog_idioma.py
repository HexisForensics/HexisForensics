"""PT idêntico no HashDialog (cadeia de custódia) após a migração."""

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
from ui.widgets.hash_dialog import HashDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


with tempfile.TemporaryDirectory() as td:
    dlg = HashDialog(Path(td))
    igual("título", dlg.windowTitle(), "Cadeia de Custódia — Conferir e Gerar Manifestos")
    igual("botão conferir", dlg.botao_conferir.text(), "🔍 Conferir Integridade")
    igual("botão gerar", dlg.botao_gerar.text(), "Gerar Manifesto")
    igual("botão fechar", dlg.botao_fechar.text(), "Fechar")
    igual("placeholder resultado", dlg.area_resultado.placeholderText(),
          "O resultado da operação aparece aqui.")

print("\n[moldes]")
igual("rótulo da aquisição", traduzir("hd_rotulo_aquisicao", plataforma="Android",
      quando="16/11/2026 09:00", selo="🔒 selada"),
      "        └─  Android · 16/11/2026 09:00  ·  🔒 selada")
igual("rótulo do caso", traduzir("hd_rotulo_caso", nome="CASO_1", escopo="2 aquisições",
      selo="🔒 caso selado"),
      "📁  CASO_1    —    2 aquisições  ·  🔒 caso selado")
igual("corpo integridade confirmada", traduzir("hd_integro_corpo", resumo="RESUMO"),
      "RESUMO\n\nO relatório da conferência foi gravado na pasta.")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
