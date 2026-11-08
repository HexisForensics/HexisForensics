"""
Diálogo de identificação do dispositivo recebido para exame: descrição da
peça, número do lacre e fotografias.

São exigidos o lacre, que liga a peça física ao registro, e DUAS
fotografias, que documentam o estado em que ela foi recebida — frente e
verso, lado a lado no relatório. Já foram exigidas quatro; era exagero, e
fazia o examinador anexar imagem qualquer para destravar a tela.
Fotografias adicionais continuam aceitas.
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..style import COR_FALHA
from .ajuste_de_tela import caber_na_tela


class DeviceInfoDialog(QDialog):
    """
    Diálogo modal para preencher características do aparelho, lacre e gerenciar fotos.
    """

    MINIMO_DE_FOTOS = 2
    MAXIMO_DE_FOTOS = 10

    def __init__(self, parent=None, modo_edicao: bool = False):
        super().__init__(parent)
        self.modo_edicao = modo_edicao
        self.setWindowTitle("Dispositivo e Cadeia de Custódia")
        self.setModal(True)
        caber_na_tela(self, 500, 560)

        self.caminhos_fotos: list[Path] = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.campo_marca_modelo = QLineEdit()
        self.campo_marca_modelo.setPlaceholderText("Ex: Samsung Galaxy S23 / iPhone 14")
        
        self.campo_cor = QLineEdit()
        self.campo_cor.setPlaceholderText("Ex: Preto, Prata, Azul")

        self.campo_estado = QLineEdit()
        self.campo_estado.setPlaceholderText("Ex: Ligado, com tela trincada, desligado")

        self.campo_lacre = QLineEdit()
        self.campo_lacre.setPlaceholderText("Ex: Lacre nº 9876543")


        form.addRow("Marca/modelo:", self.campo_marca_modelo)
        form.addRow("Cor:", self.campo_cor)
        form.addRow("Estado do dispositivo:", self.campo_estado)
        form.addRow("Número do lacre:", self.campo_lacre)

        layout.addLayout(form)

        # Seção de Evidências Fotográficas
        self.rotulo_fotos = QLabel(
            f"<b>Fotografias da peça</b> ({self.MINIMO_DE_FOTOS} obrigatórias, "
            f"por exemplo frente e verso; até {self.MAXIMO_DE_FOTOS}):"
        )
        layout.addWidget(self.rotulo_fotos)
        
        self.lista_fotos = QListWidget()
        self.lista_fotos.setFixedHeight(90)
        layout.addWidget(self.lista_fotos)

        # Botões de gerenciamento de fotos (Adicionar e Remover)
        linha_botoes_fotos = QHBoxLayout()
        btn_adicionar = QPushButton("📷 Adicionar Foto")
        btn_adicionar.clicked.connect(self._adicionar_fotos)
        
        btn_remover = QPushButton("🗑️ Remover Foto Selecionada")
        btn_remover.setStyleSheet(f"color: {COR_FALHA};")
        btn_remover.clicked.connect(self._remover_foto)

        linha_botoes_fotos.addWidget(btn_adicionar)
        linha_botoes_fotos.addWidget(btn_remover)
        layout.addLayout(linha_botoes_fotos)

        # Na retificação as fotos não entram: as da aquisição já estão sob
        # o selo, e a tela não teria como trocá-las sem reescrevê-la.
        if self.modo_edicao:
            for widget in (self.rotulo_fotos, self.lista_fotos, btn_adicionar, btn_remover):
                widget.setVisible(False)

        # Botões de Ação Final
        linha_botoes = QHBoxLayout()
        linha_botoes.addStretch()

        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.clicked.connect(self.reject)

        self.botao_ok = QPushButton("Salvar / Confirmar")
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)

        linha_botoes.addWidget(self.botao_cancelar)
        linha_botoes.addWidget(self.botao_ok)
        layout.addLayout(linha_botoes)

    def _adicionar_fotos(self) -> None:
        arquivos, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Fotos do Aparelho", "", "Imagens (*.png *.jpg *.jpeg)"
        )
        for arq in arquivos:
            if len(self.caminhos_fotos) < self.MAXIMO_DE_FOTOS:
                p = Path(arq)
                if p not in self.caminhos_fotos:
                    self.caminhos_fotos.append(p)
                    self.lista_fotos.addItem(QListWidgetItem(p.name))
            else:
                QMessageBox.warning(
                    self, "Limite", f"O limite máximo é de {self.MAXIMO_DE_FOTOS} fotos."
                )
                break

    def _remover_foto(self) -> None:
        linha_selecionada = self.lista_fotos.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Aviso", "Selecione na lista acima a foto que deseja remover.")
            return

        # Remove da lista visual e da lista interna de caminhos
        self.lista_fotos.takeItem(linha_selecionada)
        self.caminhos_fotos.pop(linha_selecionada)

    def _confirmar(self) -> None:
        lacre = self.campo_lacre.text().strip()
        if not lacre:
            QMessageBox.warning(self, "Aviso", "O número do lacre do dispositivo é obrigatório.")
            self.campo_lacre.setFocus()
            return

        if not self.modo_edicao and len(self.caminhos_fotos) < self.MINIMO_DE_FOTOS:
            QMessageBox.warning(
                self,
                "Aviso",
                f"Anexe {self.MINIMO_DE_FOTOS} fotografias da peça (por exemplo, frente e "
                f"verso): elas documentam o estado em que o dispositivo foi recebido. "
                f"Há {len(self.caminhos_fotos)} anexada(s).",
            )
            return

        self.accept()

    def dados_dispositivo(self) -> dict:
        return {
            "marca_modelo": self.campo_marca_modelo.text().strip(),
            "cor": self.campo_cor.text().strip(),
            "estado": self.campo_estado.text().strip(),
            "lacre": self.campo_lacre.text().strip(),
            "fotos": self.caminhos_fotos,
        }