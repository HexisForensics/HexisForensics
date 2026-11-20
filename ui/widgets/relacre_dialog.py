"""
Diálogo de reaposição de lacre: registra o NOVO lacre aposto na peça depois
da perícia, com a foto do novo lacre. É a segunda foto da peça — a primeira,
no cadastro, documenta a peça como recebida com o lacre original.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.idioma import traduzir
from .ajuste_de_tela import caber_na_tela


class RelacreDialog(QDialog):
    """Modal para o número do novo lacre, quem relacrou, quando e a foto."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(traduzir("rl_titulo"))
        self.setModal(True)
        caber_na_tela(self, 520, 360)
        self._foto: Optional[Path] = None
        self._dados: dict = {}
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.campo_numero = QLineEdit()
        self.campo_numero.setPlaceholderText(traduzir("rl_ph_numero"))
        self.campo_data = QLineEdit()
        self.campo_data.setPlaceholderText(traduzir("rl_ph_data"))
        self.campo_por = QLineEdit()
        self.campo_por.setPlaceholderText(traduzir("rl_ph_por"))
        self.campo_registro = QLineEdit()
        self.campo_registro.setPlaceholderText(traduzir("rl_ph_registro"))

        form.addRow(traduzir("rl_label_numero"), self.campo_numero)
        form.addRow(traduzir("rl_label_data"), self.campo_data)
        form.addRow(traduzir("rl_label_por"), self.campo_por)
        form.addRow(traduzir("rl_label_registro"), self.campo_registro)
        layout.addLayout(form)

        layout.addWidget(QLabel(traduzir("rl_rotulo_foto")))
        linha_foto = QHBoxLayout()
        self.botao_foto = QPushButton(traduzir("rl_btn_foto"))
        self.botao_foto.clicked.connect(self._escolher_foto)
        self.rotulo_foto = QLabel(traduzir("rl_sem_foto"))
        self.rotulo_foto.setObjectName("TextoSecundario")
        linha_foto.addWidget(self.botao_foto)
        linha_foto.addWidget(self.rotulo_foto, 1)
        layout.addLayout(linha_foto)

        linha_botoes = QHBoxLayout()
        linha_botoes.addStretch()
        self.botao_cancelar = QPushButton(traduzir("rl_btn_cancelar"))
        self.botao_cancelar.clicked.connect(self.reject)
        self.botao_ok = QPushButton(traduzir("rl_btn_salvar"))
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)
        linha_botoes.addWidget(self.botao_cancelar)
        linha_botoes.addWidget(self.botao_ok)
        layout.addLayout(linha_botoes)

    def _escolher_foto(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, traduzir("rl_selecionar_foto"), "", traduzir("di_filtro_imagens"))
        if caminho:
            self._foto = Path(caminho)
            self.rotulo_foto.setText(self._foto.name)

    def _confirmar(self) -> None:
        numero = self.campo_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, traduzir("rl_aviso"), traduzir("rl_erro_numero"))
            self.campo_numero.setFocus()
            return
        if self._foto is None:
            QMessageBox.warning(self, traduzir("rl_aviso"), traduzir("rl_erro_foto"))
            return
        self._dados = {
            "numero": numero,
            "data": self.campo_data.text().strip(),
            "por": self.campo_por.text().strip(),
            "registro": self.campo_registro.text().strip(),
            "foto": self._foto,
        }
        self.accept()

    def dados(self) -> dict:
        return self._dados
