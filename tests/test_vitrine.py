"""
A vitrine animada da tela de entrada desenha as três cenas sem erro, em
qualquer momento do ciclo e em tamanhos diferentes de janela.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)

from ui.widgets import vitrine_entrada  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


print("\n[1] As tres cenas desenham, em todo o ciclo")
vitrine = vitrine_entrada.VitrineAnimada()
erros = []
for largura, altura in ((380, 360), (300, 420), (520, 330)):
    vitrine.resize(largura, altura)
    for decimo in range(0, 180, 3):  # 18 s de ciclo, a cada 0,3 s
        vitrine._inicio = vitrine_entrada.time.monotonic() - decimo / 10
        imagem = QImage(largura, altura, QImage.Format_ARGB32)
        imagem.fill(0)
        try:
            vitrine.render(imagem)
        except Exception as erro:  # noqa: BLE001
            erros.append(f"{largura}x{altura} t={decimo / 10}: {erro}")
checar(f"nenhum erro de desenho ({erros[:2]})", not erros)
checar("as legendas sao tres, uma por cena", len(vitrine_entrada.LEGENDAS) == 3)

print("\n[2] O relogio so roda com a tela visivel")
checar("parado antes de mostrar", not vitrine._relogio.isActive())
vitrine.show()
checar("roda quando aparece", vitrine._relogio.isActive())
vitrine.hide()
checar("para quando some", not vitrine._relogio.isActive())

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificacao(oes):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificacoes passaram.")
