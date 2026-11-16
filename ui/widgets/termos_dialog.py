"""
Os termos de uso na tela: para aceitar (entrada) ou só para consultar (Sobre).

O texto vem de `services.termos_service`, a mesma fonte do instalador.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from services import termos_service
from services.idioma import traduzir
from .ajuste_de_tela import caber_na_tela


class TermosDialog(QDialog):
    def __init__(self, parent=None, para_aceitar: bool = True, nome: str = ""):
        super().__init__(parent)
        self.setWindowTitle(traduzir("tm_titulo"))
        self.setModal(True)
        caber_na_tela(self, 640, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        if para_aceitar:
            aviso = QLabel(
                (traduzir("tm_aviso_com_nome", nome=nome) if nome
                 else traduzir("tm_aviso_sem_nome"))
                + traduzir("tm_aviso_sufixo")
            )
            aviso.setWordWrap(True)
            layout.addWidget(aviso)
        texto = QTextBrowser()
        texto.setHtml(termos_service.html())
        layout.addWidget(texto, 1)

        linha = QHBoxLayout()
        linha.addStretch()
        if para_aceitar:
            recusar = QPushButton(traduzir("tm_btn_recusar"))
            recusar.clicked.connect(self.reject)
            aceitar = QPushButton(traduzir("tm_btn_aceitar"))
            aceitar.setDefault(True)
            aceitar.clicked.connect(self.accept)
            linha.addWidget(recusar)
            linha.addWidget(aceitar)
        else:
            fechar = QPushButton(traduzir("tm_btn_fechar"))
            fechar.setDefault(True)
            fechar.clicked.connect(self.accept)
            linha.addWidget(fechar)
        layout.addLayout(linha)
