"""PT idêntico no DiskPanel (seleção de unidade) após a migração."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.disk_panel import DiskPanel  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


dp = DiskPanel()
igual("título padrão", dp.title(), "Unidade de Disco (computador, HD externo ou pendrive)")
igual("status inicial", dp.label_status.text(), "Nenhuma unidade detectada ainda.")
igual("botão atualizar", dp.botao_atualizar.text(), "🔄 Atualizar Unidades")

dp.atualizar_lista([])
if "✖ Nenhuma unidade detectada." in dp.label_status.text():
    print("  OK   status sem unidades")
else:
    print(f" FALHA status sem unidades: {dp.label_status.text()!r}")
    falhas.append("status sem unidades")

print("\n[moldes]")
igual("linha da unidade", traduzir("dk_item", caminho="E:\\", rotulo="PENDRIVE",
      tipo="Removível", livres="7.0 GB", total="7.3 GB"),
      "E:\\  —  PENDRIVE  [Removível]  7.0 GB livres de 7.3 GB")
igual("status detectadas", traduzir("dk_detectadas", cor="#19c3a6", n=2),
      "<b style='color:#19c3a6;'>✔ 2 unidade(s) detectada(s).</b>")
igual("prefixo estação", traduzir("dk_estacao_prefixo", texto="E: ..."),
      "⚠ ESTAÇÃO DO EXAMINADOR — E: ...")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
