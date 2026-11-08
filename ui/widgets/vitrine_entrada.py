"""
Vitrine animada da tela de entrada: três cenas da perícia, em rodízio.

1. Aquisição — o celular ligado ao computador, os dados correndo pelo cabo.
2. Integridade — o arquivo passa pelo SHA-256 e sai como hash conferido.
3. Cadeia de custódia — a peça lacrada, as fotos e as etapas do exame.

Desenhada à mão com `QPainter`, num espaço de 360×262 escalado ao tamanho
do painel: sem imagem de terceiros (direito autoral) e nítida em qualquer
resolução. Cada cena fica 6 s e troca devagar, para não distrair quem
digita a senha. O relógio para quando a tela some.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

AZUL = QColor("#3f8dfd")
VERDE = QColor("#19c3a6")
MARINHO = QColor("#0f1b2d")
CABO = QColor("#5a7aa3")
TEXTO_TELA = QColor("#8fb4e6")
MONO = QColor("#5f84b3")
CLARO = QColor("#cfe2ff")
CINZA = QColor("#8fa3bb")
PAPEL = QColor("#e9eef5")
FUNDO_FOTO = QColor("#1d3352")
TRILHO = QColor("#1f3a5c")
INATIVO = QColor("#2c4466")

LARGURA, ALTURA = 360.0, 262.0
SEGUNDOS_POR_CENA = 6.0
TRANSICAO = 0.5

LEGENDAS = (
    ("Aquisição sem alterar o dispositivo", "Cada comando preservado como evidência"),
    ("Integridade comprovada por hash", "SHA-256 de cada arquivo, no momento da coleta"),
    ("Cadeia de custódia do início ao fim", "Lacre, fotografias e registro de cada etapa"),
)


def _fonte(tamanho: float, peso=QFont.Normal, familia: str = "Segoe UI") -> QFont:
    fonte = QFont(familia)
    fonte.setPixelSize(max(1, round(tamanho)))
    fonte.setWeight(peso)
    return fonte


def _vidro(retangulo: QRectF) -> QBrush:
    gradiente = QLinearGradient(retangulo.topLeft(), retangulo.bottomLeft())
    gradiente.setColorAt(0, QColor("#16324f"))
    gradiente.setColorAt(1, QColor("#0b1626"))
    return QBrush(gradiente)


def _texto(p: QPainter, x: float, y: float, texto: str, fonte: QFont, cor: QColor,
           centro: bool = False) -> None:
    p.setFont(fonte)
    p.setPen(cor)
    if centro:
        x -= QFontMetricsF(fonte).horizontalAdvance(texto) / 2
    p.drawText(QPointF(x, y), texto)


def _barras(p: QPainter, x: float, y: float, larguras, passo: float, altura: float,
            primeira_mais_forte: bool = True) -> None:
    p.setPen(Qt.NoPen)
    for indice, largura in enumerate(larguras):
        cor = QColor(AZUL)
        cor.setAlphaF(0.35 if (indice == 0 and primeira_mais_forte) else 0.25)
        p.setBrush(cor)
        p.drawRoundedRect(QRectF(x, y + indice * passo, largura, altura), 3, 3)


class VitrineAnimada(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(330)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._inicio = time.monotonic()
        self._relogio = QTimer(self)
        self._relogio.setInterval(33)  # ~30 quadros por segundo
        self._relogio.timeout.connect(self.update)

    def showEvent(self, evento) -> None:
        self._relogio.start()
        super().showEvent(evento)

    def hideEvent(self, evento) -> None:
        self._relogio.stop()
        super().hideEvent(evento)

    # ------------------------------------------------------------------
    def paintEvent(self, _evento) -> None:
        t = time.monotonic() - self._inicio
        ciclo = SEGUNDOS_POR_CENA * len(LEGENDAS)
        cena = int((t % ciclo) // SEGUNDOS_POR_CENA)
        local = t % SEGUNDOS_POR_CENA
        if local < TRANSICAO:
            opacidade, deslocamento = local / TRANSICAO, 18 * (1 - local / TRANSICAO)
        elif local > SEGUNDOS_POR_CENA - TRANSICAO:
            fim = (SEGUNDOS_POR_CENA - local) / TRANSICAO
            opacidade, deslocamento = fim, -18 * (1 - fim)
        else:
            opacidade, deslocamento = 1.0, 0.0

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        area_legenda = 70.0
        palco = QRectF(0, 0, self.width(), max(10.0, self.height() - area_legenda))
        escala = min(palco.width() / LARGURA, palco.height() / ALTURA)
        origem_x = (palco.width() - LARGURA * escala) / 2

        p.save()
        p.setOpacity(opacidade)
        p.translate(origem_x + deslocamento * escala, palco.top())
        p.scale(escala, escala)
        (self._aquisicao, self._integridade, self._custodia)[cena](p, t)
        p.restore()

        # --- legenda e indicador
        y = palco.bottom() + 22
        titulo, subtitulo = LEGENDAS[cena]
        p.setOpacity(opacidade)
        _texto(p, 0, y, titulo, _fonte(15, QFont.DemiBold), QColor("#e8f0fb"))
        _texto(p, 0, y + 19, subtitulo, _fonte(12), CINZA)
        p.setOpacity(1.0)
        x = 0.0
        for indice in range(len(LEGENDAS)):
            largura = 20.0 if indice == cena else 7.0
            p.setPen(Qt.NoPen)
            p.setBrush(AZUL if indice == cena else INATIVO)
            p.drawRoundedRect(QRectF(x, y + 34, largura, 7), 3.5, 3.5)
            x += largura + 7
        p.end()

    # ------------------------------------------------------------------
    # Cena 1 — Aquisição
    # ------------------------------------------------------------------
    def _aquisicao(self, p: QPainter, t: float) -> None:
        celular = QRectF(30, 50, 86, 160)
        p.setPen(QPen(AZUL, 3))
        p.setBrush(_vidro(celular))
        p.drawRoundedRect(celular, 14, 14)
        p.setPen(Qt.NoPen)
        cor = QColor(AZUL)
        cor.setAlphaF(0.6)
        p.setBrush(cor)
        p.drawRoundedRect(QRectF(62, 60, 22, 4), 2, 2)
        _barras(p, 44, 76, (58,), 0, 10)
        _barras(p, 44, 92, (44, 52, 38), 14, 8, primeira_mais_forte=False)
        p.setPen(QPen(cor, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(73, 190), 7, 7)

        cabo = QPainterPath(QPointF(73, 210))
        cabo.cubicTo(QPointF(73, 245), QPointF(170, 245), QPointF(205, 205))
        cabo.cubicTo(QPointF(240, 165), QPointF(250, 170), QPointF(262, 168))
        caneta = QPen(CABO, 3)
        caneta.setCapStyle(Qt.RoundCap)
        p.setPen(caneta)
        p.drawPath(cabo)
        p.setPen(Qt.NoPen)
        for atraso, alfa in ((0.0, 1.0), (0.6, 0.7), (1.2, 0.45)):
            fracao = ((t - atraso) % 1.8) / 1.8
            pacote = QColor(VERDE)
            pacote.setAlphaF(alfa)
            p.setBrush(pacote)
            p.drawEllipse(cabo.pointAtPercent(fracao), 4, 4)

        tela = QRectF(196, 78, 140, 92)
        p.setPen(QPen(AZUL, 3))
        p.setBrush(_vidro(tela))
        p.drawRoundedRect(tela, 8, 8)
        p.setPen(QPen(AZUL, 2))
        p.setBrush(QColor("#1d3352"))
        p.drawPolygon(QPolygonF([QPointF(184, 172), QPointF(348, 172),
                                 QPointF(338, 186), QPointF(194, 186)]))
        _texto(p, 210, 102, "Aquisição em andamento", _fonte(10), TEXTO_TELA)
        p.setPen(Qt.NoPen)
        p.setBrush(TRILHO)
        p.drawRoundedRect(QRectF(212, 116, 92, 8), 4, 4)
        p.setBrush(VERDE)
        p.drawRoundedRect(QRectF(212, 116, 92 * ((t % 5.0) / 5.0), 8), 4, 4)
        _texto(p, 212, 146, "adb -s 0030000000 …", _fonte(10, familia="Consolas"), MONO)
        self._piscar(p, t, QPointF(322, 96), 5)

    # ------------------------------------------------------------------
    # Cena 2 — Integridade
    # ------------------------------------------------------------------
    def _integridade(self, p: QPainter, t: float) -> None:
        documento = QPainterPath(QPointF(28, 70))
        for x, y in ((86, 70), (106, 90), (106, 180), (28, 180)):
            documento.lineTo(x, y)
        documento.closeSubpath()
        p.setPen(QPen(AZUL, 3))
        p.setBrush(_vidro(QRectF(28, 70, 78, 110)))
        p.drawPath(documento)
        dobra = QPainterPath(QPointF(86, 70))
        dobra.lineTo(86, 90)
        dobra.lineTo(106, 90)
        p.setBrush(Qt.NoBrush)
        p.drawPath(dobra)
        _barras(p, 40, 104, (54, 44, 50, 36), 14, 6)

        for x1, x2 in ((116, 150), (222, 250)):
            tracejado = QPen(CABO, 3)
            tracejado.setDashPattern([2, 2])  # em unidades da espessura: 6 e 6
            tracejado.setDashOffset(-((t % 0.8) / 0.8) * 4)
            p.setPen(tracejado)
            p.drawLine(QPointF(x1, 125), QPointF(x2, 125))

        hexagono = QPolygonF([QPointF(186, 82), QPointF(222, 103), QPointF(222, 147),
                              QPointF(186, 168), QPointF(150, 147), QPointF(150, 103)])
        p.setPen(QPen(AZUL, 3))
        p.setBrush(MARINHO)
        p.drawPolygon(hexagono)
        _texto(p, 186, 121, "SHA", _fonte(13, QFont.Bold), QColor("white"), centro=True)
        _texto(p, 186, 138, "256", _fonte(13, QFont.Light), AZUL, centro=True)

        caixa = QRectF(252, 88, 94, 74)
        borda = QPen(AZUL, 1)
        borda.setDashPattern([4, 3])
        p.setPen(borda)
        p.setBrush(QColor("#11202f"))
        p.drawRoundedRect(caixa, 8, 8)
        # O hash "se calcula": as linhas aparecem uma a uma.
        linhas = ("3f8d a6c1", "19c3 0f1b", "e2b7 77d4")
        visiveis = min(3, int((t % SEGUNDOS_POR_CENA) / 0.7) + 1)
        for indice, linha in enumerate(linhas[:visiveis]):
            _texto(p, 263, 110 + indice * 17, linha, _fonte(13, familia="Consolas"), CLARO)
        if visiveis == 3:
            p.setPen(Qt.NoPen)
            p.setBrush(VERDE)
            p.drawEllipse(QPointF(333, 88), 14, 14)
            visto = QPen(QColor("#0b1626"), 3)
            visto.setCapStyle(Qt.RoundCap)
            p.setPen(visto)
            p.drawPolyline(QPolygonF([QPointF(326, 88), QPointF(331, 93), QPointF(340, 83)]))
        _texto(p, 186, 206, "mesmo arquivo → mesmo hash · 1 bit alterado → hash diferente",
               _fonte(11), CINZA, centro=True)

    # ------------------------------------------------------------------
    # Cena 3 — Cadeia de custódia
    # ------------------------------------------------------------------
    def _custodia(self, p: QPainter, t: float) -> None:
        saco = QRectF(34, 52, 150, 160)
        p.setPen(QPen(AZUL, 3))
        p.setBrush(QColor("#132a45"))
        p.drawRoundedRect(saco, 10, 10)
        p.drawLine(QPointF(34, 76), QPointF(184, 76))
        fecho = QPen(CABO, 2)
        fecho.setDashPattern([2.5, 2])
        p.setPen(fecho)
        p.drawLine(QPointF(40, 66), QPointF(178, 66))
        aparelho = QRectF(84, 96, 50, 88)
        p.setPen(QPen(CABO, 2))
        p.setBrush(_vidro(aparelho))
        p.drawRoundedRect(aparelho, 9, 9)
        fonte = _fonte(10, QFont.Bold)
        fonte.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        _texto(p, 109, 203, "EVIDÊNCIA", fonte, TEXTO_TELA, centro=True)

        p.save()
        p.translate(168, 92)
        p.rotate(-8)
        p.setPen(Qt.NoPen)
        p.setBrush(VERDE)
        p.drawRoundedRect(QRectF(-28, -12, 62, 26), 4, 4)
        _texto(p, 3, 5, "Nº 004517", _fonte(11, QFont.Bold, "Consolas"), QColor("#0b1626"),
               centro=True)
        p.restore()

        for cx, cy, angulo, x, y, legenda, camera in (
            (262, 98, 7, 222, 58, "frente", False),
            (278, 176, -5, 236, 138, "verso", True),
        ):
            p.save()
            p.translate(cx, cy)
            p.rotate(angulo)
            p.translate(-cx, -cy)
            p.setPen(Qt.NoPen)
            p.setBrush(PAPEL)
            p.drawRoundedRect(QRectF(x, y, 84, 84), 4, 4)
            p.setBrush(FUNDO_FOTO)
            p.drawRect(QRectF(x + 6, y + 6, 72, 58))
            p.setPen(QPen(AZUL, 1))
            p.setBrush(MARINHO)
            p.drawRoundedRect(QRectF(x + 30, y + 14, 22, 42), 4, 4)
            if camera:
                p.setPen(Qt.NoPen)
                p.setBrush(AZUL)
                p.drawEllipse(QPointF(x + 41, y + 24), 4, 4)
            _texto(p, x + 42, y + 77, legenda, _fonte(8), QColor("#5b6675"), centro=True)
            p.restore()

        p.setPen(QPen(INATIVO, 2))
        p.drawLine(QPointF(52, 238), QPointF(308, 238))
        for x, rotulo in ((52, "recebimento"), (137, "aquisição"), (222, "lacre")):
            p.setPen(Qt.NoPen)
            p.setBrush(AZUL)
            p.drawEllipse(QPointF(x, 238), 5, 5)
            _texto(p, x, 256, rotulo, _fonte(9.5), CINZA, centro=True)
        self._piscar(p, t, QPointF(308, 238), 5)
        _texto(p, 308, 256, "laudo", _fonte(9.5), CINZA, centro=True)

    @staticmethod
    def _piscar(p: QPainter, t: float, centro: QPointF, raio: float) -> None:
        cor = QColor(VERDE)
        cor.setAlphaF(0.25 + 0.75 * (0.5 + 0.5 * math.cos(t / 1.2 * 2 * math.pi)))
        p.setPen(Qt.NoPen)
        p.setBrush(cor)
        p.drawEllipse(centro, raio, raio)
