"""
Janela de entrega: o que vai, para onde e para quem. A cópia, a
conferência pelo hash, o recibo e o registro no caso ficam com
`services.entrega_service`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services import entrega_service, sessao_service
from services.idioma import traduzir

from .visualizador_pdf import abrir_pdf
from .ajuste_de_tela import caber_na_tela


class EntregaDialog(QDialog):
    def __init__(self, pasta_aquisicao: Path, material=(), documentos=(), parent=None):
        super().__init__(parent)
        self.pasta_aquisicao = Path(pasta_aquisicao)
        self.material = list(material)
        self.documentos = [Path(d) for d in documentos]
        self.setWindowTitle(traduzir("eg_titulo"))
        self.setModal(True)
        caber_na_tela(self, 620, 300)

        layout = QVBoxLayout(self)
        partes = []
        if self.material:
            partes.append(traduzir("eg_partes_material", n=len(self.material)))
        if self.documentos:
            partes.append(traduzir("eg_partes_documentos", n=len(self.documentos)))
        explicacao = QLabel(
            traduzir("eg_explicacao", partes=traduzir("eg_e").join(partes),
                     nome=self.pasta_aquisicao.name)
            + (traduzir("eg_teste") if sessao_service.e_forensic_admin() else "")
        )
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        form = QFormLayout()
        linha = QHBoxLayout()
        self.campo_destino = QLineEdit()
        self.campo_destino.setPlaceholderText(traduzir("eg_ph_destino"))
        escolher = QPushButton(traduzir("eg_btn_escolher"))
        escolher.clicked.connect(self._escolher)
        linha.addWidget(self.campo_destino, 1)
        linha.addWidget(escolher)
        form.addRow(traduzir("eg_label_destino"), linha)
        self.campo_finalidade = QLineEdit()
        self.campo_finalidade.setPlaceholderText(traduzir("eg_ph_finalidade"))
        form.addRow(traduzir("eg_label_finalidade"), self.campo_finalidade)
        layout.addLayout(form)
        layout.addStretch()

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText(traduzir("eg_btn_exportar"))
        botoes.accepted.connect(self._exportar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _escolher(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, traduzir("eg_destino_dialogo"), str(Path.home()))
        if pasta:
            self.campo_destino.setText(pasta)

    def _exportar(self) -> None:
        destino = self.campo_destino.text().strip()
        if not destino or not Path(destino).is_dir():
            QMessageBox.warning(self, traduzir("eg_destino_titulo"), traduzir("eg_destino_invalido"))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            resultado = entrega_service.exportar(
                self.pasta_aquisicao, Path(destino), self.material, self.documentos,
                examinador=sessao_service.nome(), finalidade=self.campo_finalidade.text().strip(),
                teste=sessao_service.e_forensic_admin(),
            )
        finally:
            QApplication.restoreOverrideCursor()
        if resultado.erro:
            QMessageBox.critical(self, traduzir("eg_nada_entregue"), resultado.erro)
            return
        mensagem = traduzir("eg_mensagem", n=len(resultado.itens), pasta=resultado.pasta)
        if resultado.falhas:
            mensagem += traduzir("eg_falhas_prefixo", lista="\n".join(resultado.falhas))
            QMessageBox.warning(self, traduzir("eg_ressalvas_titulo"), mensagem)
        else:
            QMessageBox.information(self, traduzir("eg_concluida_titulo"), mensagem)
        self.accept()
        if resultado.recibo_pdf:
            abrir_pdf(resultado.recibo_pdf, self.parent())
