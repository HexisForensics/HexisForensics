"""
Janelas que cabem na tela em que abrem.

Cada janela tem um tamanho pensado para um monitor de escritório comum, mas
a suíte roda também em computadores de órgão público com tela de 1366x768.
Nesse monitor, uma janela de 780 ou 860 pixels de altura abria com a parte
de baixo — onde ficam "Gerar Laudo", "Cancelar", "Fechar" — fora da tela.
Sendo modal, ela bloqueava o resto da suíte, e o examinador via todos os
botões sem resposta (relato de 04/11/2026, primeira instalação em
campo).

Aqui o tamanho pedido vale como teto: a janela nunca passa da área útil da
tela (descontada a barra de tarefas), com folga para a barra de título.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

# Fração da área útil que uma janela pode ocupar: sobra espaço para a barra
# de título e para o examinador ver que há outra janela atrás.
FRACAO_MAXIMA = 0.92


def _area_util(janela: QWidget):
    """Área útil da tela onde a janela vai abrir (a da janela-mãe, se houver)."""
    mae = janela.parentWidget()
    tela = (mae.screen() if mae is not None else None) or janela.screen()
    tela = tela or QGuiApplication.primaryScreen()
    return tela.availableGeometry()


def caber_na_tela(janela: QWidget, largura: int, altura: int) -> None:
    """Dá à janela o tamanho pedido, reduzido ao que cabe na tela."""
    area = _area_util(janela)
    janela.resize(
        min(largura, int(area.width() * FRACAO_MAXIMA)),
        min(altura, int(area.height() * FRACAO_MAXIMA)),
    )


def centralizar_na_tela(janela: QWidget) -> None:
    """
    Põe a janela no centro da área útil.

    Para janelas que não são QDialog: o Qt centraliza um diálogo sobre a
    mãe e o mantém dentro da tela sozinho, mas uma janela comum (o
    visualizador de PDF) fica onde o Windows a puser — às vezes com a
    barra de título fora do alcance.
    """
    area = _area_util(janela)
    janela.move(
        area.x() + max(0, (area.width() - janela.width()) // 2),
        area.y() + max(0, (area.height() - janela.height()) // 2),
    )
