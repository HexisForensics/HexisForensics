"""
Construção do tema Qt (paleta + stylesheet) a partir de um perfil de marca.

Nenhuma cor fica fixa neste arquivo — tudo vem do `BrandConfig` carregado
por `services.branding_service`. É isso que torna a UI "de marca branca":
trocar de identidade visual é trocar de perfil de branding, nunca editar
este módulo.

Cores semânticas (sucesso/alerta/erro), usadas por exemplo em
`widgets/device_panel.py`, propositalmente NÃO vêm do branding — elas
comunicam estado (conectado/aguardando/erro) e devem continuar
reconhecíveis independente da marca do cliente.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from services.branding_service import BrandConfig

# ---------------------------------------------------------------------------
# Paleta semântica — comunica ESTADO, não identidade visual.
#
# Fica aqui, e não em cada widget, porque os mesmos valores já estavam
# repetidos em `extraction_panel`, `device_panel` e `disk_panel`: três cópias
# do mesmo vermelho, livres para divergirem na próxima edição. Uma cor de
# falha que difere de tela para tela ensina o operador a não confiar nela.
#
# São as únicas cores fixas da interface. Não vêm do branding de propósito:
# "falhou" precisa continuar reconhecível seja qual for a marca do cliente.
# Todas escolhidas para contrastar sobre o fundo escuro do tema.
# ---------------------------------------------------------------------------
COR_PENDENTE = "#8a8f98"
COR_EM_EXECUCAO = "#1565c0"
COR_SUCESSO = "#2e7d32"
COR_PARCIAL = "#c77700"
COR_FALHA = "#c62828"


def aplicar_tema(app: QApplication, marca: BrandConfig) -> None:
    """Aplica a paleta, o stylesheet e o ícone de janela do perfil de marca informado."""
    app.setStyle("Fusion")
    cores = marca.cores

    paleta = QPalette()
    paleta.setColor(QPalette.Window, QColor(cores.fundo))
    paleta.setColor(QPalette.WindowText, QColor(cores.texto))
    paleta.setColor(QPalette.Base, QColor(cores.fundo_entrada))
    paleta.setColor(QPalette.AlternateBase, QColor(cores.fundo_alt))
    paleta.setColor(QPalette.ToolTipBase, QColor(cores.fundo_alt))
    paleta.setColor(QPalette.ToolTipText, QColor(cores.texto))
    paleta.setColor(QPalette.Text, QColor(cores.texto))
    paleta.setColor(QPalette.Button, QColor(cores.fundo_alt))
    paleta.setColor(QPalette.ButtonText, QColor(cores.texto))
    paleta.setColor(QPalette.BrightText, QColor("#ff6b6b"))
    paleta.setColor(QPalette.Link, QColor(cores.destaque))
    paleta.setColor(QPalette.Highlight, QColor(cores.destaque))
    paleta.setColor(QPalette.HighlightedText, QColor(cores.texto_sobre_destaque))
    paleta.setColor(QPalette.Disabled, QPalette.Text, QColor(cores.texto_secundario))
    paleta.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(cores.texto_secundario))
    paleta.setColor(QPalette.Disabled, QPalette.WindowText, QColor(cores.texto_secundario))
    app.setPalette(paleta)

    app.setStyleSheet(f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {cores.fundo};
            color: {cores.texto};
        }}
        QGroupBox {{
            border: 1px solid {cores.borda};
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 12px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {cores.texto};
        }}
        QPushButton {{
            background-color: {cores.fundo_alt};
            color: {cores.texto};
            border: 1px solid {cores.borda};
            border-radius: 5px;
            padding: 6px 16px;
        }}
        QPushButton:hover {{
            border-color: {cores.destaque};
        }}
        QPushButton:pressed {{
            background-color: {cores.borda};
        }}
        QPushButton:disabled {{
            color: {cores.texto_secundario};
            border-color: {cores.borda};
        }}
        QLineEdit, QListWidget, QTextEdit {{
            background-color: {cores.fundo_entrada};
            color: {cores.texto};
            border: 1px solid {cores.borda};
            border-radius: 4px;
            padding: 4px;
            selection-background-color: {cores.destaque};
            selection-color: {cores.texto_sobre_destaque};
        }}
        QListWidget::item:selected {{
            background-color: {cores.destaque};
            color: {cores.texto_sobre_destaque};
        }}
        QCheckBox {{
            color: {cores.texto};
            padding: 3px 0;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {cores.borda};
            border-radius: 3px;
            background-color: {cores.fundo_entrada};
        }}
        QCheckBox::indicator:checked {{
            background-color: {cores.destaque};
            border-color: {cores.destaque};
        }}
        QProgressBar {{
            background-color: {cores.fundo_alt};
            border: 1px solid {cores.borda};
            border-radius: 4px;
            text-align: center;
            color: {cores.texto};
        }}
        QProgressBar::chunk {{
            background-color: {cores.destaque};
            border-radius: 3px;
        }}
        #Sidebar {{
            background-color: {cores.fundo_alt};
            border-right: 1px solid {cores.borda};
        }}
        #SidebarCabecalho {{
            background-color: {cores.fundo_alt};
            border-bottom: 1px solid {cores.borda};
        }}
        #SidebarLogo {{
            background-color: {cores.fundo_alt};
        }}
        #SidebarNomeMarca {{
            color: {cores.texto};
            font-size: 15px;
            font-weight: 700;
        }}
        QLabel#TextoSecundario {{
            color: {cores.texto_secundario};
            font-size: 11px;
        }}
        QLabel#SidebarSecao {{
            color: {cores.texto_secundario};
            font-size: 9pt;
            font-weight: 700;
            padding: 14px 20px 6px 20px;
            background-color: transparent;
        }}
        QFrame#SidebarSeparador {{
            background-color: {cores.borda};
            border: none;
        }}
        QPushButton#SidebarItem {{
            background-color: transparent;
            color: {cores.texto_secundario};
            border: none;
            border-radius: 0;
            text-align: left;
            padding: 10px 20px;
            font-weight: 400;
        }}
        QPushButton#SidebarItem:hover {{
            background-color: {cores.fundo_entrada};
            color: {cores.texto};
        }}
        QPushButton#SidebarItem:checked {{
            background-color: {cores.destaque};
            color: {cores.texto_sobre_destaque};
            font-weight: 600;
        }}
        QPushButton#SidebarItem:pressed {{
            background-color: {cores.destaque};
            color: {cores.texto_sobre_destaque};
        }}
        QStatusBar {{
            background-color: {cores.fundo_alt};
            color: {cores.texto_secundario};
        }}
        QScrollBar:vertical {{
            background: {cores.fundo};
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {cores.borda};
            min-height: 24px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {cores.destaque};
        }}
        QScrollBar:horizontal {{
            background: {cores.fundo};
            height: 12px;
        }}
        QScrollBar::handle:horizontal {{
            background: {cores.borda};
            min-width: 24px;
            border-radius: 5px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
        }}
        QSplitter::handle {{
            background: {cores.borda};
        }}
        QToolTip {{
            background-color: {cores.fundo_alt};
            color: {cores.texto};
            border: 1px solid {cores.borda};
        }}
    """)

    if marca.caminho_icone:
        app.setWindowIcon(QIcon(str(marca.caminho_icone)))
