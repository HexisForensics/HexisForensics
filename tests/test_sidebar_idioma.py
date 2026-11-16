"""PT idêntico na sidebar (menu lateral) após a migração para o catálogo."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.branding_service import carregar_branding  # noqa: E402
from ui.widgets.sidebar import Sidebar  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


sb = Sidebar(carregar_branding())
igual("item android", sb._botoes["android"].text(), "🤖  Android")
igual("item iphone", sb._botoes["iphone"].text(), "📱  iPhone")
igual("item armazenamento", sb._botoes["computador"].text(), "💾  Armazenamento")
igual("item cadeia de custódia", sb._botoes["hash"].text(), "🔐  Cadeia de Custódia")
igual("item casos e documentos", sb._botoes["abrir_pasta"].text(), "📂  Casos e Documentos")
igual("item examinadores", sb._botoes["examinadores"].text(), "👥  Examinadores")
igual("item sobre", sb._botoes["sobre"].text(), "ℹ️  Sobre")
igual("item trocar examinador", sb._botoes["trocar_examinador"].text(), "🔄  Trocar examinador")
igual("item sair", sb._botoes["sair"].text(), "🚪  Sair")

sb.atualizar_sessao("Ana", "A", "10:00")
igual("sessão desde", sb._desde.text(), "sessão desde 10:00")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
