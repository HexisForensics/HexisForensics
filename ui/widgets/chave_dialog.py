"""
Diálogo da chave de 64 dígitos do backup do WhatsApp.

Dezesseis campos de quatro caracteres, na mesma grade de quatro por quatro
em que o WhatsApp mostra a chave no aparelho. O examinador confere grupo a
grupo contra a tela (ou a fotografia dela), em vez de contar caracteres
numa caixa de texto solta — que era o que gerava dúvida.

Cada campo só aceita os caracteres possíveis numa chave (0 a 9, a até f),
o cursor avança sozinho ao completar um grupo, e colar a chave inteira em
qualquer campo a distribui pelos dezesseis. O botão só liga com os 64
dígitos presentes. Se a chave estiver ERRADA, quem diz é a decifragem — a
conferência de autenticidade recusa, e nada é decifrado.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QRegularExpression, Qt
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

GRUPOS = 16
TAMANHO_DO_GRUPO = 4
COLUNAS = 4


class ChaveDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chave de criptografia do backup do WhatsApp")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        instrucao = QLabel(
            "Digite a <b>chave de 64 dígitos</b> exibida pelo WhatsApp ao ativar o backup "
            "criptografado de ponta a ponta: 16 grupos de 4 caracteres, na mesma ordem "
            "da tela do aparelho (da esquerda para a direita, de cima para baixo).<br>"
            "Você também pode <b>colar</b> a chave inteira em qualquer campo."
        )
        instrucao.setWordWrap(True)
        layout.addWidget(instrucao)

        grade = QGridLayout()
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(10)
        fonte = QFont("Consolas")
        fonte.setPointSize(15)
        fonte.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        validador = QRegularExpressionValidator(
            QRegularExpression(f"[0-9a-fA-F]{{0,{TAMANHO_DO_GRUPO}}}"), self
        )

        self._campos: list[QLineEdit] = []
        for indice in range(GRUPOS):
            campo = QLineEdit()
            campo.setMaxLength(TAMANHO_DO_GRUPO)
            campo.setValidator(validador)
            campo.setFont(fonte)
            campo.setAlignment(Qt.AlignCenter)
            campo.setFixedWidth(104)
            campo.setPlaceholderText("····")
            campo.textEdited.connect(lambda texto, i=indice: self._ao_editar(i, texto))
            campo.installEventFilter(self)
            grade.addWidget(campo, indice // COLUNAS, indice % COLUNAS)
            self._campos.append(campo)
        layout.addLayout(grade)

        self.rotulo_contagem = QLabel()
        layout.addWidget(self.rotulo_contagem)

        aviso = QLabel(
            "A chave ficará registrada no caso, como complemento: é o que permite a outro "
            "examinador repetir a decifragem. Se um dígito estiver errado, nada é decifrado."
        )
        aviso.setWordWrap(True)
        aviso.setObjectName("TextoSecundario")
        layout.addWidget(aviso)

        linha = QHBoxLayout()
        botao_limpar = QPushButton("Limpar")
        botao_limpar.clicked.connect(self._limpar)
        linha.addWidget(botao_limpar)
        linha.addStretch()
        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)
        self.botao_ok = QPushButton("Decifrar")
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self.accept)
        linha.addWidget(botao_cancelar)
        linha.addWidget(self.botao_ok)
        layout.addLayout(linha)

        self._atualizar()
        self._campos[0].setFocus()

    # ------------------------------------------------------------------
    def chave(self) -> str:
        """A chave digitada, em grupos separados por espaço."""
        return " ".join(campo.text().lower() for campo in self._campos)

    def _digitos(self) -> int:
        return sum(len(campo.text()) for campo in self._campos)

    def _atualizar(self) -> None:
        digitos = self._digitos()
        total = GRUPOS * TAMANHO_DO_GRUPO
        self.rotulo_contagem.setText(
            f"<b>{digitos} de {total}</b> dígitos"
            + (" — chave completa." if digitos == total else f" — faltam {total - digitos}.")
        )
        self.botao_ok.setEnabled(digitos == total)

    def _ao_editar(self, indice: int, texto: str) -> None:
        if len(texto) == TAMANHO_DO_GRUPO and indice + 1 < GRUPOS:
            self._campos[indice + 1].setFocus()
            self._campos[indice + 1].selectAll()
        self._atualizar()

    def _limpar(self) -> None:
        for campo in self._campos:
            campo.clear()
        self._atualizar()
        self._campos[0].setFocus()

    def _colar(self, indice: int) -> bool:
        """
        Distribui o que está na área de transferência pelos campos, a partir
        do campo em que se colou. Espaços, hifens e quebras de linha são
        ignorados; se sobrar qualquer outro caractere, não é uma chave e
        nada é colado.
        """
        texto = re.sub(r"[\s\-]", "", QGuiApplication.clipboard().text() or "")
        if not texto or not re.fullmatch(r"[0-9a-fA-F]+", texto):
            return False
        if len(texto) == GRUPOS * TAMANHO_DO_GRUPO:
            indice = 0  # chave inteira: sempre do primeiro campo
        for posicao in range(0, len(texto), TAMANHO_DO_GRUPO):
            if indice >= GRUPOS:
                break
            self._campos[indice].setText(texto[posicao:posicao + TAMANHO_DO_GRUPO].lower())
            indice += 1
        self._campos[min(indice, GRUPOS - 1)].setFocus()
        self._atualizar()
        return True

    def eventFilter(self, origem, evento) -> bool:
        if evento.type() == QEvent.KeyPress and origem in self._campos:
            indice = self._campos.index(origem)
            if evento.matches(QKeySequence.Paste):
                return self._colar(indice) or True
            # Apagar num campo vazio volta para o anterior, como se os
            # dezesseis fossem um campo só.
            if evento.key() == Qt.Key_Backspace and not origem.text() and indice > 0:
                anterior = self._campos[indice - 1]
                anterior.setFocus()
                anterior.setText(anterior.text()[:-1])
                self._atualizar()
                return True
        return super().eventFilter(origem, evento)
