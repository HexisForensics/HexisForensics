"""
Gera os arquivos de imagem da marca a partir dos SVG em `assets/marca/`.

Os SVG são a fonte; PNG e ICO são derivados e ficam versionados para que a
suíte, os documentos e o instalador não dependam de renderizar SVG. Rodar
de novo só quando um SVG mudar:

    py ferramentas/gerar_marca.py
"""

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

PASTA = Path(__file__).resolve().parents[1] / "assets" / "marca"

# (svg, png, largura em pixels)
SAIDAS = (
    ("icone.svg", "icone.png", 512),
    ("logo_claro.svg", "logo_claro.png", 1800),
    ("logo_escuro.svg", "logo_escuro.png", 900),
)
TAMANHOS_DO_ICO = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def renderizar(svg: Path, png: Path, largura: int) -> None:
    renderizador = QSvgRenderer(str(svg))
    proporcao = renderizador.viewBoxF().height() / renderizador.viewBoxF().width()
    imagem = QImage(largura, round(largura * proporcao), QImage.Format_ARGB32)
    imagem.fill(Qt.transparent)
    pintor = QPainter(imagem)
    pintor.setRenderHint(QPainter.Antialiasing)
    pintor.setRenderHint(QPainter.TextAntialiasing)
    renderizador.render(pintor, QRectF(0, 0, imagem.width(), imagem.height()))
    pintor.end()
    imagem.save(str(png))


def main() -> int:
    aplicacao = QGuiApplication(sys.argv)  # noqa: F841 — o texto do SVG precisa das fontes
    for svg, png, largura in SAIDAS:
        renderizar(PASTA / svg, PASTA / png, largura)
        print(f"{png}: {largura}px")
    Image.open(PASTA / "icone.png").save(PASTA / "icone.ico", sizes=TAMANHOS_DO_ICO)
    print("icone.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
