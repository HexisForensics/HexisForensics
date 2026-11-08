"""
Visualizador de PDF da própria ferramenta.

Relatórios, laudos e conversas abrem aqui, e não no leitor de PDF do
Windows: o examinador não precisa ir ao Explorer atrás do arquivo. Tem
páginas, zoom, imprimir e "salvar cópia", que confere a cópia pelo
SHA-256 antes de dizer que salvou.

Janela própria, mas FILHA de quem a abriu: as janelas de Casos e
Documentos e de Conversas são modais (enquanto abertas, só elas recebem
clique), e um visualizador independente ficava atrás delas, inalcançável.
Por isso, aberto de dentro de uma delas, ele é filho dela e também modal:
fica na frente, recebe os cliques e, fechado, devolve à janela de origem.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from services.documentos_service import salvar_copia
from .ajuste_de_tela import caber_na_tela, centralizar_na_tela

PASSO_DE_ZOOM = 1.2

# Mantém as janelas abertas vivas (sem pai, o Python as coletaria).
_ABERTAS: list = []


class VisualizadorPdf(QWidget):
    def __init__(self, caminho: Path, parent=None):
        super().__init__(parent, Qt.Window)
        self.caminho = Path(caminho)
        self.setWindowTitle(f"{self.caminho.name} — Hexis Forensics")
        caber_na_tela(self, 980, 860)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self.documento = QPdfDocument(self)
        self.documento.load(str(self.caminho))

        self.vista = QPdfView(self)
        self.vista.setDocument(self.documento)
        self.vista.setPageMode(QPdfView.PageMode.MultiPage)
        self.vista.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.vista.pageNavigator().currentPageChanged.connect(self._atualizar_pagina)

        barra = QToolBar()
        barra.setMovable(False)
        self._acao(barra, "◀ Anterior", self._anterior, QKeySequence.MoveToPreviousPage)
        self.rotulo_pagina = QLabel()
        self.rotulo_pagina.setContentsMargins(10, 0, 10, 0)
        barra.addWidget(self.rotulo_pagina)
        self._acao(barra, "Próxima ▶", self._proxima, QKeySequence.MoveToNextPage)
        barra.addSeparator()
        self._acao(barra, "－", self._diminuir, QKeySequence.ZoomOut)
        self._acao(barra, "＋", self._aumentar, QKeySequence.ZoomIn)
        self._acao(barra, "Ajustar à largura", self._ajustar)
        barra.addSeparator()
        self._acao(barra, "🖨 Imprimir", self._imprimir, QKeySequence.Print)
        self._acao(barra, "💾 Salvar cópia em…", self._salvar_copia, QKeySequence.Save)
        self._acao(barra, "Abrir no leitor do Windows", self._abrir_externo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(barra)
        if self.documento.status() != QPdfDocument.Status.Ready:
            aviso = QLabel(f"Não foi possível abrir o documento:\n{self.caminho}")
            aviso.setAlignment(Qt.AlignCenter)
            layout.addWidget(aviso, 1)
        else:
            layout.addWidget(self.vista, 1)
        self._atualizar_pagina(0)

    def _acao(self, barra: QToolBar, texto: str, funcao, atalho=None) -> None:
        acao = QAction(texto, self)
        acao.triggered.connect(funcao)
        if atalho is not None:
            acao.setShortcut(atalho)
        barra.addAction(acao)

    # ------------------------------------------------------------------
    def _total(self) -> int:
        return max(1, self.documento.pageCount())

    def _pagina_atual(self) -> int:
        return self.vista.pageNavigator().currentPage()

    def _ir(self, pagina: int) -> None:
        pagina = max(0, min(self._total() - 1, pagina))
        self.vista.pageNavigator().jump(pagina, QPointF(), self.vista.pageNavigator().currentZoom())

    def _anterior(self) -> None:
        self._ir(self._pagina_atual() - 1)

    def _proxima(self) -> None:
        self._ir(self._pagina_atual() + 1)

    def _atualizar_pagina(self, pagina: int) -> None:
        self.rotulo_pagina.setText(f"Página {pagina + 1} de {self._total()}")

    def _zoom(self, fator: float) -> None:
        self.vista.setZoomMode(QPdfView.ZoomMode.Custom)
        self.vista.setZoomFactor(max(0.25, min(5.0, self.vista.zoomFactor() * fator)))

    def _aumentar(self) -> None:
        self._zoom(PASSO_DE_ZOOM)

    def _diminuir(self) -> None:
        self._zoom(1 / PASSO_DE_ZOOM)

    def _ajustar(self) -> None:
        self.vista.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    # ------------------------------------------------------------------
    def _imprimir(self) -> None:
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(self, "Imprimir", "Impressão indisponível nesta estação.")
            return
        impressora = QPrinter(QPrinter.HighResolution)
        dialogo = QPrintDialog(impressora, self)
        dialogo.setMinMax(1, self._total())
        if dialogo.exec() != QPrintDialog.Accepted:
            return
        primeira = max(1, impressora.fromPage() or 1)
        ultima = min(self._total(), impressora.toPage() or self._total())
        pintor = QPainter()
        if not pintor.begin(impressora):
            QMessageBox.warning(self, "Imprimir", "A impressora não aceitou o trabalho.")
            return
        try:
            for numero in range(primeira - 1, ultima):
                if numero > primeira - 1:
                    impressora.newPage()
                area = impressora.pageRect(QPrinter.DevicePixel).toRect()
                imagem = self.documento.render(numero, area.size())
                pintor.drawImage(area.topLeft(), imagem)
        finally:
            pintor.end()

    def _salvar_copia(self) -> None:
        destino, _ = QFileDialog.getSaveFileName(
            self, "Salvar cópia do documento", str(Path.home() / self.caminho.name),
            "Documento PDF (*.pdf)",
        )
        if not destino:
            return
        try:
            resumo = salvar_copia(self.caminho, Path(destino))
        except OSError as erro:
            QMessageBox.critical(self, "Cópia não salva", str(erro))
            return
        QMessageBox.information(
            self, "Cópia salva",
            f"Cópia salva em:\n{destino}\n\nConferida pelo SHA-256, idêntica ao original:\n{resumo}",
        )

    def _abrir_externo(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.caminho)))


def abrir_pdf(caminho: Path, parent=None) -> VisualizadorPdf:
    """Abre o PDF na ferramenta, na frente de quem o pediu, e devolve a janela."""
    mae = parent.window() if parent is not None else None
    janela = VisualizadorPdf(caminho, mae)
    # Aberto de dentro de uma janela modal, o visualizador também é modal:
    # a janela modal mais recente fica sempre na frente e recebe os
    # cliques. Fechado, volta-se à janela de onde ele veio.
    if mae is not None and (mae.isModal() if hasattr(mae, "isModal") else False):
        janela.setWindowModality(Qt.ApplicationModal)
        # Sem botão de minimizar quando modal. Janela aberta de dentro de
        # outra não ganha ícone na barra de tarefas: minimizada, ela sumia
        # e continuava bloqueando a suíte inteira, sem que o examinador
        # tivesse como trazê-la de volta (provável causa da "pane" relatada
        # em 04/11/2026, ao gerar o laudo em campo).
        # Botão a botão, como na tela de entrada: desligar um só deixava o
        # Windows sem saber quais mostrar, e o X sumia junto.
        janela.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        janela.setWindowFlag(Qt.WindowCloseButtonHint, True)
        janela.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
    centralizar_na_tela(janela)
    _ABERTAS.append(janela)
    janela.destroyed.connect(lambda *_: _ABERTAS.remove(janela) if janela in _ABERTAS else None)
    janela.show()
    janela.raise_()
    janela.activateWindow()
    return janela
