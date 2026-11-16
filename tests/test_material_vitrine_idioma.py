"""PT idêntico em MaterialWidget (aba Material) e VitrineAnimada (tela de entrada)."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from ui.widgets.material_widget import MaterialWidget  # noqa: E402
from ui.widgets.vitrine_entrada import LEGENDAS, VitrineAnimada  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


print("\n[1] MaterialWidget")
mw = MaterialWidget()
igual("placeholder busca", mw.busca.placeholderText(),
      "Buscar arquivo pelo nome (Enter)… vazio volta à árvore")
igual("botão exportar", mw.botao_exportar.text(), "📤 Exportar selecionados…")
igual("botão conferir", mw.botao_conferir.text(), "Conferir com o lacre")
igual("botão pdf", mw.botao_pdf.text(), "📄 Abrir no visualizador")
igual("coluna nome", mw.arvore.headerItem().text(0), "Nome")
igual("coluna tamanho", mw.arvore.headerItem().text(1), "Tamanho")
igual("ficha sem aquisição", mw.ficha.text(),
      "Escolha uma aquisição na lista de dispositivos.")
igual("nota somente leitura", mw.nota.text(),
      "Somente leitura: nada é gravado dentro da aquisição lacrada.")

print("\n[moldes material]")
igual("base do arquivo", traduzir("mt_base", nome="a.jpg", relativo="fotos/a.jpg",
      tamanho="1,2 MiB"), "<b>a.jpg</b><br>fotos/a.jpg<br>Tamanho: 1,2 MiB")
igual("resultado da busca", traduzir("mt_busca_resultado", n=3, termo="foto",
      sufixo=traduzir("mt_busca_fim")), "<b>3</b> arquivo(s) com “foto” no nome.")

print("\n[2] VitrineAnimada")
VitrineAnimada()  # smoke: constrói
igual("LEGENDAS virou chaves", LEGENDAS[0], ("vit_cena1_titulo", "vit_cena1_sub"))
igual("legenda cena 1", traduzir("vit_cena1_titulo"), "Aquisição sem alterar o dispositivo")
igual("rótulo evidência", traduzir("vit_evidencia"), "EVIDÊNCIA")
igual("timeline laudo", traduzir("vit_laudo"), "laudo")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
