"""PT idêntico no DeviceInfoDialog (a peça e o lacre) após a migração."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.device_info_dialog import DeviceInfoDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


dlg = DeviceInfoDialog()
igual("título", dlg.windowTitle(), "Dispositivo e Cadeia de Custódia")
igual("placeholder lacre", dlg.campo_lacre.placeholderText(), "Ex: Lacre nº 9876543")
igual("placeholder estado", dlg.campo_estado.placeholderText(),
      "Ex: Ligado, com tela trincada, desligado")
igual("botão salvar", dlg.botao_ok.text(), "Salvar / Confirmar")
igual("botão cancelar", dlg.botao_cancelar.text(), "Cancelar")
igual("rótulo das fotos (molde com min/max)", dlg.rotulo_fotos.text(),
      "<b>Fotografia da peça</b> (1 obrigatória: a peça como recebida, com o lacre "
      "original; até 10). A foto do novo lacre é anexada na reaposição:")

igual("fotos obrigatórias (molde)", traduzir("di_fotos_obrigatorias", min=1, n=0),
      "Anexe ao menos 1 fotografia da peça como recebida (com o lacre original): "
      "documenta o estado em que o dispositivo chegou. A foto do novo lacre entra na "
      "reaposição, após a perícia. Há 0 anexada(s).")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
