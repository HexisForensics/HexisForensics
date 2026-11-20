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
from services.idioma import traduzir


class DeviceInfoDialog(QDialog):
    """
    Diálogo modal para preencher características do aparelho, lacre e gerenciar fotos.
    """

    MINIMO_DE_FOTOS = 2
    MAXIMO_DE_FOTOS = 10

    def __init__(self, parent=None, modo_edicao: bool = False):
        super().__init__(parent)
        self.modo_edicao = modo_edicao
        self.setWindowTitle(traduzir("di_titulo"))
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
        self.campo_marca_modelo.setPlaceholderText(traduzir("di_ph_marca"))

        self.campo_cor = QLineEdit()
        self.campo_cor.setPlaceholderText(traduzir("di_ph_cor"))

        self.campo_estado = QLineEdit()
        self.campo_estado.setPlaceholderText(traduzir("di_ph_estado"))

        # Recebimento da peça (cadeia de custódia): quando e por quem.
        self.campo_recebido_em = QLineEdit()
        self.campo_recebido_em.setPlaceholderText(traduzir("di_ph_recebido_em"))

        self.campo_recebido_por = QLineEdit()
        self.campo_recebido_por.setPlaceholderText(traduzir("di_ph_recebido_por"))

        self.campo_recebido_por_registro = QLineEdit()
        self.campo_recebido_por_registro.setPlaceholderText(traduzir("di_ph_recebido_por_registro"))

        self.campo_lacre = QLineEdit()
        self.campo_lacre.setPlaceholderText(traduzir("di_ph_lacre"))

        # Lacre aposto após romper o original para realizar a perícia.
        self.campo_lacre_novo = QLineEdit()
        self.campo_lacre_novo.setPlaceholderText(traduzir("di_ph_lacre_novo"))

        form.addRow(traduzir("di_label_marca"), self.campo_marca_modelo)
        form.addRow(traduzir("di_label_cor"), self.campo_cor)
        form.addRow(traduzir("di_label_estado"), self.campo_estado)
        form.addRow(traduzir("di_label_recebido_em"), self.campo_recebido_em)
        form.addRow(traduzir("di_label_recebido_por"), self.campo_recebido_por)
        form.addRow(traduzir("di_label_recebido_por_registro"), self.campo_recebido_por_registro)
        form.addRow(traduzir("di_label_lacre"), self.campo_lacre)
        form.addRow(traduzir("di_label_lacre_novo"), self.campo_lacre_novo)

        layout.addLayout(form)

        # Seção de Evidências Fotográficas
        self.rotulo_fotos = QLabel(traduzir(
            "di_rotulo_fotos", min=self.MINIMO_DE_FOTOS, max=self.MAXIMO_DE_FOTOS
        ))
        layout.addWidget(self.rotulo_fotos)
        
        self.lista_fotos = QListWidget()
        self.lista_fotos.setFixedHeight(90)
        layout.addWidget(self.lista_fotos)

        # Botões de gerenciamento de fotos (Adicionar e Remover)
        linha_botoes_fotos = QHBoxLayout()
        btn_adicionar = QPushButton(traduzir("di_btn_adicionar"))
        btn_adicionar.clicked.connect(self._adicionar_fotos)

        btn_remover = QPushButton(traduzir("di_btn_remover"))
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

        self.botao_cancelar = QPushButton(traduzir("di_btn_cancelar"))
        self.botao_cancelar.clicked.connect(self.reject)

        self.botao_ok = QPushButton(traduzir("di_btn_salvar"))
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)

        linha_botoes.addWidget(self.botao_cancelar)
        linha_botoes.addWidget(self.botao_ok)
        layout.addLayout(linha_botoes)

    def _adicionar_fotos(self) -> None:
        arquivos, _ = QFileDialog.getOpenFileNames(
            self, traduzir("di_selecionar_fotos"), "", traduzir("di_filtro_imagens")
        )
        for arq in arquivos:
            if len(self.caminhos_fotos) < self.MAXIMO_DE_FOTOS:
                p = Path(arq)
                if p not in self.caminhos_fotos:
                    self.caminhos_fotos.append(p)
                    self.lista_fotos.addItem(QListWidgetItem(p.name))
            else:
                QMessageBox.warning(
                    self, traduzir("di_limite_titulo"),
                    traduzir("di_limite_corpo", max=self.MAXIMO_DE_FOTOS)
                )
                break

    def _remover_foto(self) -> None:
        linha_selecionada = self.lista_fotos.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, traduzir("di_aviso"), traduzir("di_selecione_foto"))
            return

        # Remove da lista visual e da lista interna de caminhos
        self.lista_fotos.takeItem(linha_selecionada)
        self.caminhos_fotos.pop(linha_selecionada)

    def _confirmar(self) -> None:
        lacre = self.campo_lacre.text().strip()
        if not lacre:
            QMessageBox.warning(self, traduzir("di_aviso"), traduzir("di_lacre_obrigatorio"))
            self.campo_lacre.setFocus()
            return

        if not self.modo_edicao and len(self.caminhos_fotos) < self.MINIMO_DE_FOTOS:
            QMessageBox.warning(
                self,
                traduzir("di_aviso"),
                traduzir("di_fotos_obrigatorias", min=self.MINIMO_DE_FOTOS,
                         n=len(self.caminhos_fotos)),
            )
            return

        self.accept()

    def dados_dispositivo(self) -> dict:
        return {
            "marca_modelo": self.campo_marca_modelo.text().strip(),
            "cor": self.campo_cor.text().strip(),
            "estado": self.campo_estado.text().strip(),
            "recebido_em": self.campo_recebido_em.text().strip(),
            "recebido_por": self.campo_recebido_por.text().strip(),
            "recebido_por_registro": self.campo_recebido_por_registro.text().strip(),
            "lacre": self.campo_lacre.text().strip(),
            "lacre_novo": self.campo_lacre_novo.text().strip(),
            "fotos": self.caminhos_fotos,
        }