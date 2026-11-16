"""PT idêntico no AutorizacaoDialog (fundamento legal) após a migração."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.widgets.fundamento_dialog import AutorizacaoDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


dlg = AutorizacaoDialog([])
igual("título", dlg.windowTitle(), "Autorização de Acesso aos Dados")
igual("botão confirmar", dlg.botao_ok.text(), "Confirmar e Prosseguir")
igual("placeholder descrição", dlg.campo_descricao.placeholderText(),
      "Descrição (opcional) — ex.: aditamento")

igual("tipos no combo: quantos", dlg.combo_tipo.count(), 4)
igual("tipo 0 (texto PT)", dlg.combo_tipo.itemText(0), "Decisão judicial")
igual("tipo 1 (texto PT)", dlg.combo_tipo.itemText(1), "Termo de consentimento do titular")
igual("tipo 3 (texto PT)", dlg.combo_tipo.itemText(3), "Outro documento")
# A CHAVE do enum é preservada no dado do item (o selado usa a chave, não o rótulo):
igual("tipo 0 (chave preservada)", dlg.combo_tipo.itemData(0), "DECISAO_JUDICIAL")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
