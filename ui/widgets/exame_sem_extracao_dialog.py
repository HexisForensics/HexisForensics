"""
Formulário do exame sem extração: o estado do aparelho e o que se tentou.

Tudo aqui é DECLARAÇÃO do examinador e assim sai no laudo. A tentativa de
conexão não é perguntada: a ferramenta a faz e registra sozinha, logo
depois deste formulário (se o aparelho liga).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from services.exame_service import RECOMENDACAO_PADRAO, RESPOSTAS, TIPOS_DE_BLOQUEIO
from services.idioma import traduzir
from .ajuste_de_tela import caber_na_tela


class ExameSemExtracaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(traduzir("es_titulo"))
        self.setModal(True)
        caber_na_tela(self, 560, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        explicacao = QLabel(traduzir("es_explicacao"))
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        form = QFormLayout()
        form.setSpacing(8)
        self.campo_liga = QComboBox()
        self.campo_liga.addItems(("Sim", "Não"))
        self.campo_liga.currentTextChanged.connect(self._ao_mudar_liga)
        form.addRow(traduzir("es_label_liga"), self.campo_liga)

        self.campo_estado = QComboBox()
        self.campo_estado.addItems(("Ligado", "Desligado", "Não verificado"))
        form.addRow(traduzir("es_label_estado"), self.campo_estado)

        self.campo_bateria = QLineEdit()
        self.campo_bateria.setPlaceholderText(traduzir("es_ph_bateria"))
        form.addRow(traduzir("es_label_bateria"), self.campo_bateria)

        self.campo_isolamento = QComboBox()
        self.campo_isolamento.addItems(RESPOSTAS)
        form.addRow(traduzir("es_label_isolamento"), self.campo_isolamento)

        self.campo_bloqueio = QComboBox()
        self.campo_bloqueio.addItems(TIPOS_DE_BLOQUEIO)
        form.addRow(traduzir("es_label_bloqueio"), self.campo_bloqueio)

        self.campo_tentativas = QPlainTextEdit()
        self.campo_tentativas.setPlaceholderText(traduzir("es_ph_tentativas"))
        form.addRow(traduzir("es_label_tentativas"), self.campo_tentativas)

        self.campo_recomendacao = QPlainTextEdit(RECOMENDACAO_PADRAO)
        self.campo_recomendacao.setFixedHeight(70)
        form.addRow(traduzir("es_label_recomendacao"), self.campo_recomendacao)
        layout.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText(traduzir("es_btn_registrar"))
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _ao_mudar_liga(self, texto: str) -> None:
        if texto == "Não":
            self.campo_bloqueio.setCurrentText(TIPOS_DE_BLOQUEIO[-1])
        elif self.campo_bloqueio.currentText() == TIPOS_DE_BLOQUEIO[-1]:
            self.campo_bloqueio.setCurrentIndex(0)

    def _confirmar(self) -> None:
        if not self.campo_tentativas.toPlainText().strip():
            QMessageBox.warning(
                self, traduzir("es_campo_obrigatorio_titulo"),
                traduzir("es_campo_obrigatorio_corpo"),
            )
            return
        self.accept()

    def dados(self) -> dict:
        return {
            "liga": self.campo_liga.currentText(),
            "estado_ao_receber": self.campo_estado.currentText(),
            "bateria": self.campo_bateria.text().strip(),
            "isolado_da_rede": self.campo_isolamento.currentText(),
            "tipo_de_bloqueio": self.campo_bloqueio.currentText(),
            "tentativas": self.campo_tentativas.toPlainText().strip(),
            "recomendacao": self.campo_recomendacao.toPlainText().strip(),
        }
