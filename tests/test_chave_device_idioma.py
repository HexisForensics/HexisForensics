"""PT idêntico em ChaveDialog (chave do WhatsApp) e DevicePanel (status)."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.widgets.chave_dialog import ChaveDialog  # noqa: E402
from ui.widgets.device_panel import DevicePanel  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


print("\n[1] ChaveDialog")
ck = ChaveDialog()
igual("título", ck.windowTitle(), "Chave de criptografia do backup do WhatsApp")
igual("botão decifrar", ck.botao_ok.text(), "Decifrar")
igual("contagem inicial (0 de 64, molde)", ck.rotulo_contagem.text(),
      "<b>0 de 64</b> dígitos — faltam 64.")

print("\n[2] DevicePanel")
dp = DevicePanel()
igual("título padrão", dp.title(), "Status do Dispositivo")
igual("status inicial", dp.label_status.text(), "Status: desconhecido")
igual("botão verificar", dp.botao_verificar.text(), "🔎 Verificar Conexão")
dp.atualizar_status(True, True, "detalhe do dispositivo")
if "✔ Conectado e autorizado" in dp.label_status.text():
    print("  OK   status conectado")
else:
    print(f" FALHA status conectado: {dp.label_status.text()!r}")
    falhas.append("status conectado")
igual("detalhe é o dado recebido (não traduzido)", dp.label_detalhe.text(),
      "detalhe do dispositivo")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
