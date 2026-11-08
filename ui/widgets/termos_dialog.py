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
from .ajuste_de_tela import caber_na_tela


class TermosDialog(QDialog):
    def __init__(self, parent=None, para_aceitar: bool = True, nome: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Termos de uso")
        self.setModal(True)
        caber_na_tela(self, 640, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        if para_aceitar:
            aviso = QLabel(
                (f"<b>{nome}</b>, antes de continuar, leia os termos de uso. " if nome else
                 "Antes de continuar, leia os termos de uso. ")
                + "O aceite é pessoal e fica no registro de acessos desta estação."
            )
            aviso.setWordWrap(True)
            layout.addWidget(aviso)
        texto = QTextBrowser()
        texto.setHtml(termos_service.html())
        layout.addWidget(texto, 1)

        linha = QHBoxLayout()
        linha.addStretch()
        if para_aceitar:
            recusar = QPushButton("Não aceito")
            recusar.clicked.connect(self.reject)
            aceitar = QPushButton("Eu aceito")
            aceitar.setDefault(True)
            aceitar.clicked.connect(self.accept)
            linha.addWidget(recusar)
            linha.addWidget(aceitar)
        else:
            fechar = QPushButton("Fechar")
            fechar.setDefault(True)
            fechar.clicked.connect(self.accept)
            linha.addWidget(fechar)
        layout.addLayout(linha)
