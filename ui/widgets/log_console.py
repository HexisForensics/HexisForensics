"""
Console de log em texto monoespaçado, usado como saída em tempo real das
extrações.

Não define cores próprias: herda o estilo de `QTextEdit` do stylesheet
global aplicado por `ui.style.aplicar_tema`, então automaticamente segue
qualquer perfil de marca carregado — nenhuma cor de branding precisa ser
duplicada aqui.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QColor, QFont, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

PREFIXO_DE_ALERTA = "[DESFECHO — ATENÇÃO]"


class LogConsole(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)

        familia = "Consolas" if "Consolas" in QFontDatabase.families() else "Monospace"
        fonte = QFont(familia)
        fonte.setStyleHint(QFont.Monospace)
        fonte.setPointSize(10)
        self.setFont(fonte)

    def adicionar_linha(self, texto: str, com_timestamp: bool = False) -> None:
        if com_timestamp and texto.strip():
            texto = f"[{datetime.now().strftime('%H:%M:%S')}] {texto}"
        self.moveCursor(QTextCursor.End)
        cursor = self.textCursor()
        if texto.startswith(PREFIXO_DE_ALERTA):
            # Desfecho com módulo sem dado: a única linha com cor própria,
            # para não se perder no meio do resto.
            formato = QTextCharFormat()
            formato.setForeground(QColor("#d64545"))
            formato.setFontWeight(QFont.Bold)
            cursor.insertText(texto, formato)
            cursor.insertText("\n", QTextCharFormat())
        else:
            cursor.insertText(texto + "\n", QTextCharFormat())
        self.moveCursor(QTextCursor.End)
