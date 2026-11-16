"""PT idêntico no CaseDialog (o caso) após a migração para o catálogo."""

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
from services.case_service import CaseService  # noqa: E402
from ui.widgets.case_dialog import CaseDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


def contem(nome, texto, trecho):
    if trecho not in texto:
        print(f" FALHA {nome}\n    não contém: {trecho!r}\n    em: {texto!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


with tempfile.TemporaryDirectory() as td:
    cs = CaseService(Path(td))

    print("\n[1] Caso novo")
    dlg = CaseDialog(cs, "Android")
    igual("título", dlg.windowTitle(), "Identificação do Caso")
    igual("aba caso novo", dlg.abas.tabText(0), "📁 Caso Novo")
    igual("aba caso existente", dlg.abas.tabText(1),
          "📂 Caso Existente (mais um dispositivo)")
    igual("botão avançar", dlg.botao_ok.text(), "Avançar ➔ Dispositivo")
    igual("botão cancelar", dlg.botao_cancelar.text(), "Cancelar")
    contem("preview cita a pasta", dlg.label_preview.text(), "Pasta da aquisição:")
    contem("preview mostra o padrão da pasta", dlg.label_preview.text(),
           "android_<AAAAMMDD_HHMMSS>")

    print("\n[2] Modo retificação")
    dlg2 = CaseDialog(cs, "Android", modo_edicao=True, dados_iniciais={}, dispositivos=["d1"])
    igual("título edição", dlg2.windowTitle(), "Retificar Dados do Caso")
    igual("botão salvar alterações", dlg2.botao_ok.text(), "Salvar Alterações")

print("\n[3] Moldes")
igual("preview da pasta", traduzir("cd_preview_pasta", id="CASO_1", plataforma="android"),
      "Pasta da aquisição: CASO_1/android_<AAAAMMDD_HHMMSS>")
igual("caso já existe", traduzir("cd_caso_existe_corpo", valor="CASO_1"),
      "Já existe um caso 'CASO_1'. Para acrescentar um dispositivo a ele, use a aba "
      "'Caso Existente'.")
igual("rótulo de campo reaproveitado (Solicitante)", traduzir("campo_solicitante"),
      "Solicitante")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
