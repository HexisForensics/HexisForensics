"""
Escolha das conversas que vão para o PDF.

Mostra todas as conversas da aquisição — WhatsApp, SMS, MMS — com o
interlocutor, o nome, a quantidade de mensagens e o período. O examinador
marca as relevantes e a suíte gera o PDF delas, completas.

Fala com `services.conversas_service`; não importa nada de `core`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.conversas_service import gerar_pdf_conversas, listar_conversas

from .visualizador_pdf import abrir_pdf
from .ajuste_de_tela import caber_na_tela

COLUNAS = ("", "Via", "Conversa / número", "Nome", "Mensagens", "Período")


class ConversasDialog(QDialog):
    def __init__(self, pasta_aquisicao, parent=None):
        super().__init__(parent)
        self.pasta_aquisicao = pasta_aquisicao
        # Caso e aquisição no título: com a aquisição errada selecionada no
        # gerenciador, a lista vinha vazia e parecia defeito (31/10/2026).
        pasta = Path(pasta_aquisicao)
        self.setWindowTitle(f"PDF de conversas — {pasta.parent.name} · {pasta.name}")
        caber_na_tela(self, 1000, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        explicacao = QLabel(
            "Marque as conversas relevantes ao exame. O PDF traz cada uma <b>completa</b>, "
            "em ordem cronológica, com a origem de cada mensagem. A íntegra de todas as "
            "conversas continua na planilha e no caderno HTML do Relatório de Conteúdo."
        )
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        linha_busca = QHBoxLayout()
        self.campo_filtro = QLineEdit()
        self.campo_filtro.setPlaceholderText("Filtrar por número, nome ou via…")
        self.campo_filtro.textChanged.connect(self._filtrar)
        linha_busca.addWidget(self.campo_filtro, 1)
        layout.addLayout(linha_busca)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        cabecalho = self.tabela.horizontalHeader()
        cabecalho.setSectionResizeMode(2, QHeaderView.Stretch)
        for coluna, largura in ((0, 30), (1, 230), (3, 200), (4, 90), (5, 180)):
            self.tabela.setColumnWidth(coluna, largura)
        self.tabela.itemChanged.connect(self._atualizar_contagem)
        # Clicar na linha marca a conversa. Antes, só a caixinha da primeira
        # coluna marcava: o clique na linha só a destacava, o contador ficava
        # em zero e o botão não acendia (vídeo de demonstração, 01/11/2026).
        self.tabela.cellClicked.connect(self._alternar_linha)
        layout.addWidget(self.tabela, 1)

        self.rotulo_contagem = QLabel()
        layout.addWidget(self.rotulo_contagem)

        linha = QHBoxLayout()
        linha.addStretch()
        botao_cancelar = QPushButton("Fechar")
        botao_cancelar.clicked.connect(self.reject)
        self.botao_gerar = QPushButton("📄 Gerar PDF das selecionadas")
        self.botao_gerar.setDefault(True)
        self.botao_gerar.clicked.connect(self._gerar)
        linha.addWidget(botao_cancelar)
        linha.addWidget(self.botao_gerar)
        layout.addLayout(linha)

        self.setCursor(Qt.WaitCursor)
        try:
            self._conversas, _ = listar_conversas(pasta_aquisicao)
        finally:
            self.unsetCursor()
        self._preencher()

    def _preencher(self) -> None:
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self._conversas))
        for linha, conversa in enumerate(self._conversas):
            marcador = QTableWidgetItem()
            marcador.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            marcador.setCheckState(Qt.Unchecked)
            self.tabela.setItem(linha, 0, marcador)
            for coluna, valor in enumerate(
                (conversa.via, conversa.rotulo, conversa.nome, str(conversa.quantidade),
                 conversa.periodo), start=1
            ):
                item = QTableWidgetItem(valor)
                if coluna == 4:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(linha, coluna, item)
        self.tabela.blockSignals(False)
        self._atualizar_contagem()
        if not self._conversas:
            self.rotulo_contagem.setText(
                f"<b>Nenhuma conversa interpretada na aquisição {Path(self.pasta_aquisicao).name}."
                "</b> Confira se é a aquisição certa. Isso não significa que o aparelho não "
                "tenha conversas: veja o Relatório de Conteúdo para o motivo."
            )

    def _alternar_linha(self, linha: int, coluna: int) -> None:
        if coluna == 0:
            return  # a própria caixinha já alterna sozinha
        marcador = self.tabela.item(linha, 0)
        if marcador is not None:
            marcador.setCheckState(
                Qt.Unchecked if marcador.checkState() == Qt.Checked else Qt.Checked)

    def _selecionadas(self) -> list:
        return [
            (self._conversas[linha].artefato, self._conversas[linha].chave)
            for linha in range(self.tabela.rowCount())
            if self.tabela.item(linha, 0).checkState() == Qt.Checked
        ]

    def _atualizar_contagem(self, *_args) -> None:
        if not self._conversas:
            self.botao_gerar.setEnabled(False)
            return
        escolhidas = self._selecionadas()
        mensagens = sum(
            conversa.quantidade for conversa in self._conversas
            if (conversa.artefato, conversa.chave) in set(escolhidas)
        )
        self.rotulo_contagem.setText(
            f"<b>{len(escolhidas)}</b> de {len(self._conversas)} conversas selecionadas — "
            f"{mensagens} mensagem(ns) no PDF."
        )
        self.botao_gerar.setEnabled(bool(escolhidas))

    def _filtrar(self, texto: str) -> None:
        texto = texto.strip().lower()
        for linha, conversa in enumerate(self._conversas):
            visivel = not texto or any(
                texto in valor.lower() for valor in (conversa.via, conversa.rotulo, conversa.nome)
            )
            self.tabela.setRowHidden(linha, not visivel)

    def _gerar(self) -> None:
        self.setCursor(Qt.WaitCursor)
        try:
            documento = gerar_pdf_conversas(self.pasta_aquisicao, self._selecionadas())
        finally:
            self.unsetCursor()
        if documento.erro:
            QMessageBox.warning(self, "PDF não gerado", documento.erro)
            return
        abrir_pdf(documento.caminho, self)
