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
from .ajuste_de_tela import caber_na_tela


class ExameSemExtracaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exame sem extração")
        self.setModal(True)
        caber_na_tela(self, 560, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        explicacao = QLabel(
            "Registre o estado do aparelho e o que foi tentado. Se o aparelho liga, a "
            "ferramenta tenta a conexão em seguida, <b>sem alterá-lo</b>, e guarda a resposta "
            "dele como prova da tentativa. O laudo dirá que não foi possível extrair — e "
            "não que o aparelho não tem dados."
        )
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        form = QFormLayout()
        form.setSpacing(8)
        self.campo_liga = QComboBox()
        self.campo_liga.addItems(("Sim", "Não"))
        self.campo_liga.currentTextChanged.connect(self._ao_mudar_liga)
        form.addRow("O aparelho liga?", self.campo_liga)

        self.campo_estado = QComboBox()
        self.campo_estado.addItems(("Ligado", "Desligado", "Não verificado"))
        form.addRow("Estado em que foi recebido", self.campo_estado)

        self.campo_bateria = QLineEdit()
        self.campo_bateria.setPlaceholderText("Ex.: 45% / sem carga / não exibida")
        form.addRow("Bateria", self.campo_bateria)

        self.campo_isolamento = QComboBox()
        self.campo_isolamento.addItems(RESPOSTAS)
        form.addRow("Isolado da rede (modo avião ou\nbolsa de Faraday)?", self.campo_isolamento)

        self.campo_bloqueio = QComboBox()
        self.campo_bloqueio.addItems(TIPOS_DE_BLOQUEIO)
        form.addRow("Tipo de bloqueio", self.campo_bloqueio)

        self.campo_tentativas = QPlainTextEdit()
        self.campo_tentativas.setPlaceholderText(
            "O que o examinador fez ou tentou. Ex.: aparelho ligado na presença do examinador; "
            "tela de bloqueio por PIN exibida; credencial não fornecida; nenhuma tentativa de "
            "desbloqueio para não acionar o apagamento por tentativas."
        )
        form.addRow("Tentativas e observações", self.campo_tentativas)

        self.campo_recomendacao = QPlainTextEdit(RECOMENDACAO_PADRAO)
        self.campo_recomendacao.setFixedHeight(70)
        form.addRow("Recomendação", self.campo_recomendacao)
        layout.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Registrar exame")
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
                self, "Campo obrigatório",
                "Descreva o que foi feito ou tentado. É o que sustenta o laudo negativo.",
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
