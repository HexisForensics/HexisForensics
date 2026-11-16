"""PT idêntico no MetodoDialog (método e limitações) após a migração.

O diálogo não guarda referências dos rótulos/botões, então conferimos por
varredura de widgets + fidelidade do catálogo. Os NOMES e as LIMITAÇÕES dos
módulos são conteúdo declarado no core (dado), e NÃO são traduzidos aqui.
"""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.metodo_dialog import MetodoDialog  # noqa: E402

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


MODULOS = [{
    "nome": "WhatsApp", "perfil": "DES",
    "limitacoes": ["sem a chave de 64 dígitos, as mensagens não são lidas"],
    "alteracoes": [("instala APK antigo", "necessário para gerar o backup")],
}]

dlg = MetodoDialog(MODULOS)
igual("título", dlg.windowTitle(), "Método e Limitações da Coleta")

textos_botoes = [b.text() for b in dlg.findChildren(QPushButton)]
entre("botão ciente", "Ciente — Prosseguir", textos_botoes)
entre("botão cancelar", "Cancelar", textos_botoes)

textos_labels = [lbl.text() for lbl in dlg.findChildren(QLabel)]
entre("título das limitações", "<b>O que esta coleta NÃO vai alcançar</b>", textos_labels)
entre("título das alterações", "<b>O que pode ser alterado no aparelho</b>", textos_labels)

print("\n[moldes]")
igual("cabeçalho", traduzir("md_cabecalho", n=1, nomes="WhatsApp"),
      "<b>1 módulo(s) selecionado(s):</b> WhatsApp")
igual("competência", traduzir("md_competencia", perfis="DES"),
      "<br><b>Competência exigida:</b> DES")
igual("justificativa (indentada)", traduzir("md_justificativa", valor="necessário"),
      "      Justificativa: necessário")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
