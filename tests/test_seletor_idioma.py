"""
Seletor de idioma: persistência da preferência (core.idioma) e o controle
na tela de entrada.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import (  # noqa: E402
    aplicar_idioma_salvo,
    definir_e_salvar,
    definir_idioma,
    idioma_ativo,
    idioma_salvo,
)
from services import perfil_service  # noqa: E402
from services.branding_service import carregar_branding  # noqa: E402
from ui.widgets.tela_entrada import REABRIR, TelaEntrada, abrir_entrada  # noqa: E402,F401

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
print("\n[1] Persistência da preferência de idioma")
# ---------------------------------------------------------------------------
definir_idioma("pt")
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    checar("sem preferência gravada, idioma_salvo é None", idioma_salvo(pasta) is None)

    definir_e_salvar("en", pasta=pasta)
    checar("definir_e_salvar troca o ativo", idioma_ativo() == "en")
    checar("o arquivo de preferência foi gravado",
           (pasta / "idioma.txt").read_text(encoding="utf-8").strip() == "en")

    definir_idioma("pt")  # simula reinício
    checar("após 'reinício', o ativo volta ao padrão", idioma_ativo() == "pt")
    checar("a preferência salva é lida de volta", idioma_salvo(pasta) == "en")

    aplicar_idioma_salvo(pasta)
    checar("aplicar_idioma_salvo restaura o idioma escolhido", idioma_ativo() == "en")

    (pasta / "idioma.txt").write_text("klingon", encoding="utf-8")
    checar("preferência inválida (sem catálogo) é ignorada", idioma_salvo(pasta) is None)

definir_idioma("pt")  # não vazar estado para outras verificações

# ---------------------------------------------------------------------------
print("\n[2] O seletor na tela de entrada")
# ---------------------------------------------------------------------------
QApplication.instance() or QApplication(sys.argv)
checar("REABRIR não colide com Accepted/Rejected", REABRIR not in (0, 1))

with tempfile.TemporaryDirectory() as td:
    perfil_service.usar_perfil_em(Path(td) / "estacao")
    try:
        dlg = TelaEntrada(carregar_branding())
        checar("a tela tem o seletor de idioma", hasattr(dlg, "combo_idioma"))
        checar("o seletor lista PT e EN", dlg.combo_idioma.count() == 2)
        checar("primeiro item é pt", dlg.combo_idioma.itemData(0) == "pt")
        checar("segundo item é en", dlg.combo_idioma.itemData(1) == "en")
        checar("começa no idioma ativo (pt)",
               dlg.combo_idioma.itemData(dlg.combo_idioma.currentIndex()) == "pt")

        # [3] Alerta de permanência: trocar o idioma pede confirmação.
        from PySide6.QtWidgets import QMessageBox  # noqa: E402
        orig = QMessageBox.question
        try:
            definir_idioma("pt")
            QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
            dlg._trocar_idioma(1)  # tenta en, mas RECUSA o alerta
            checar("recusar o alerta mantém o idioma ativo", idioma_ativo() == "pt")
            checar("recusar devolve o seletor ao idioma atual",
                   dlg.combo_idioma.itemData(dlg.combo_idioma.currentIndex()) == "pt")

            QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
            dlg._trocar_idioma(1)  # tenta en e ACEITA
            checar("aceitar o alerta troca o idioma", idioma_ativo() == "en")
        finally:
            QMessageBox.question = orig
            definir_idioma("pt")
    finally:
        perfil_service.usar_perfil_em(None)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
