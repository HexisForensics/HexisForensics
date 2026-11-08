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

from .visualizador_pdf import abrir_pdf
from .ajuste_de_tela import caber_na_tela


class EntregaDialog(QDialog):
    def __init__(self, pasta_aquisicao: Path, material=(), documentos=(), parent=None):
        super().__init__(parent)
        self.pasta_aquisicao = Path(pasta_aquisicao)
        self.material = list(material)
        self.documentos = [Path(d) for d in documentos]
        self.setWindowTitle("Exportar para entrega")
        self.setModal(True)
        caber_na_tela(self, 620, 300)

        layout = QVBoxLayout(self)
        partes = []
        if self.material:
            partes.append(f"{len(self.material)} item(ns) do material")
        if self.documentos:
            partes.append(f"{len(self.documentos)} documento(s)")
        explicacao = QLabel(
            f"<b>Vai ser exportado:</b> {' e '.join(partes)} da aquisição "
            f"<b>{self.pasta_aquisicao.name}</b>.<br>Cada cópia é conferida pelo SHA-256 depois "
            "de gravada, a entrega leva um recibo (PDF e texto) e fica registrada no caso."
            + ("<br><b style='color:#ff6b6b'>MODO DE TESTE:</b> o recibo sairá marcado como TESTE."
               if sessao_service.e_forensic_admin() else "")
        )
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        form = QFormLayout()
        linha = QHBoxLayout()
        self.campo_destino = QLineEdit()
        self.campo_destino.setPlaceholderText("Pendrive ou pasta onde a entrega será gravada")
        escolher = QPushButton("Escolher…")
        escolher.clicked.connect(self._escolher)
        linha.addWidget(self.campo_destino, 1)
        linha.addWidget(escolher)
        form.addRow("Destino", linha)
        self.campo_finalidade = QLineEdit()
        self.campo_finalidade.setPlaceholderText("Ex.: entregue ao Juízo da 1ª Vara — Proc. 123/2026")
        form.addRow("Finalidade / destinatário", self.campo_finalidade)
        layout.addLayout(form)
        layout.addStretch()

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("📤 Exportar")
        botoes.accepted.connect(self._exportar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _escolher(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Destino da entrega", str(Path.home()))
        if pasta:
            self.campo_destino.setText(pasta)

    def _exportar(self) -> None:
        destino = self.campo_destino.text().strip()
        if not destino or not Path(destino).is_dir():
            QMessageBox.warning(self, "Destino", "Escolha uma pasta de destino que exista.")
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
            QMessageBox.critical(self, "Nada foi entregue", resultado.erro)
            return
        mensagem = (f"{len(resultado.itens)} arquivo(s) entregue(s), cada um conferido pelo "
                    f"SHA-256.\n\nPasta da entrega:\n{resultado.pasta}\n\nA entrega foi "
                    "registrada no caso.")
        if resultado.falhas:
            mensagem += "\n\nATENÇÃO — não entregues:\n" + "\n".join(resultado.falhas)
            QMessageBox.warning(self, "Entrega com ressalvas", mensagem)
        else:
            QMessageBox.information(self, "Entrega concluída", mensagem)
        self.accept()
        if resultado.recibo_pdf:
            abrir_pdf(resultado.recibo_pdf, self.parent())
