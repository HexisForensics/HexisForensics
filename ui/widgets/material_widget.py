"""
Aba "Material" de Casos e Documentos: navegar pelo que foi adquirido sem
abrir a pasta lacrada no Explorer.

À esquerda, a árvore da aquisição (carregada pasta a pasta, ao abrir) e a
busca por nome. À direita, a ficha do arquivo — tamanho, data e a
conferência do SHA-256 contra o lacre — e a prévia: imagem, texto,
planilha, PDF (no visualizador da suíte) ou as tabelas de um banco.

Tudo SÓ LEITURA (`services.material_service`). Fala só com services.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.material_service import LIMITE_PARA_CONFERIR_SOZINHO, Material
from services.idioma import traduzir

from .entrega_dialog import EntregaDialog
from .visualizador_pdf import abrir_pdf

PAPEL_RELATIVO = Qt.UserRole
PAPEL_PASTA = Qt.UserRole + 1
PAPEL_CARREGADO = Qt.UserRole + 2

VAZIO, IMAGEM, TEXTO, TABELA, AVISO = range(5)


def _tamanho(numero: int) -> str:
    for unidade in ("bytes", "KiB", "MiB", "GiB"):
        if numero < 1024 or unidade == "GiB":
            return f"{numero:,.0f} {unidade}".replace(",", ".") if unidade == "bytes" \
                else f"{numero:.1f} {unidade}".replace(".", ",")
        numero /= 1024
    return str(numero)


class MaterialWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.material: Material | None = None
        self._relativo = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText(traduzir("mt_ph_busca"))
        self.busca.returnPressed.connect(self._buscar)
        topo = QHBoxLayout()
        topo.addWidget(self.busca, 1)
        self.botao_exportar = QPushButton(traduzir("mt_btn_exportar"))
        self.botao_exportar.setToolTip(traduzir("mt_tt_exportar"))
        self.botao_exportar.clicked.connect(self._exportar)
        topo.addWidget(self.botao_exportar)
        layout.addLayout(topo)

        divisor = QSplitter(Qt.Horizontal)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels([traduzir("mt_col_nome"), traduzir("mt_col_tamanho")])
        self.arvore.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.arvore.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.arvore.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.arvore.itemExpanded.connect(self._expandir)
        self.arvore.currentItemChanged.connect(lambda item, _anterior: self._escolher(item))
        divisor.addWidget(self.arvore)

        direita = QWidget()
        coluna = QVBoxLayout(direita)
        coluna.setContentsMargins(6, 0, 0, 0)
        self.ficha = QLabel(traduzir("mt_escolha"))
        self.ficha.setWordWrap(True)
        self.ficha.setTextInteractionFlags(Qt.TextSelectableByMouse)
        coluna.addWidget(self.ficha)
        botoes = QHBoxLayout()
        self.botao_conferir = QPushButton(traduzir("mt_btn_conferir"))
        self.botao_conferir.clicked.connect(lambda: self._conferir(forcar=True))
        self.botao_pdf = QPushButton(traduzir("mt_btn_pdf"))
        self.botao_pdf.clicked.connect(self._abrir_pdf)
        botoes.addWidget(self.botao_conferir)
        botoes.addWidget(self.botao_pdf)
        botoes.addStretch()
        coluna.addLayout(botoes)

        self.previas = QStackedWidget()
        self.previas.addWidget(QLabel())  # VAZIO
        self.imagem = QLabel()
        self.imagem.setAlignment(Qt.AlignCenter)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(self.imagem)
        self.previas.addWidget(rolagem)  # IMAGEM
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.previas.addWidget(self.texto)  # TEXTO
        self.tabela = QTableWidget()
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.previas.addWidget(self.tabela)  # TABELA
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setAlignment(Qt.AlignTop)
        self.previas.addWidget(self.aviso)  # AVISO
        coluna.addWidget(self.previas, 1)
        self.nota = QLabel()
        self.nota.setObjectName("TextoSecundario")
        self.nota.setWordWrap(True)
        coluna.addWidget(self.nota)
        divisor.addWidget(direita)
        divisor.setSizes([340, 560])
        layout.addWidget(divisor, 1)
        self._limpar_ficha()

    # ------------------------------------------------------------------
    def definir_aquisicao(self, pasta_aquisicao) -> None:
        self.material = Material(pasta_aquisicao) if pasta_aquisicao else None
        self.busca.clear()
        self._montar_raiz()

    def _montar_raiz(self) -> None:
        self.arvore.clear()
        self._limpar_ficha()
        if self.material is None:
            return
        self._preencher(self.arvore.invisibleRootItem(), "")

    def _preencher(self, pai: QTreeWidgetItem, relativo: str) -> None:
        for entrada in self.material.listar(relativo):
            item = QTreeWidgetItem([("📁 " if entrada.e_pasta else "") + entrada.nome,
                                    "" if entrada.e_pasta else _tamanho(entrada.tamanho)])
            item.setData(0, PAPEL_RELATIVO, entrada.relativo)
            item.setData(0, PAPEL_PASTA, entrada.e_pasta)
            if entrada.e_pasta:
                # Filho falso: mostra a seta; o conteúdo vem ao abrir.
                item.addChild(QTreeWidgetItem(["…"]))
            pai.addChild(item)

    def _expandir(self, item: QTreeWidgetItem) -> None:
        if item.data(0, PAPEL_CARREGADO):
            return
        item.takeChildren()
        self._preencher(item, item.data(0, PAPEL_RELATIVO))
        item.setData(0, PAPEL_CARREGADO, True)

    def _buscar(self) -> None:
        if self.material is None:
            return
        termo = self.busca.text().strip()
        if not termo:
            self._montar_raiz()
            return
        self.arvore.clear()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            achados, cortado = self.material.buscar(termo)
        finally:
            QApplication.restoreOverrideCursor()
        for entrada in achados:
            item = QTreeWidgetItem([entrada.relativo, _tamanho(entrada.tamanho)])
            item.setData(0, PAPEL_RELATIVO, entrada.relativo)
            item.setData(0, PAPEL_PASTA, False)
            self.arvore.addTopLevelItem(item)
        self.ficha.setText(traduzir(
            "mt_busca_resultado", n=len(achados), termo=termo,
            sufixo=(traduzir("mt_busca_cortado") if cortado else traduzir("mt_busca_fim")),
        ))

    # ------------------------------------------------------------------
    def _limpar_ficha(self) -> None:
        self._relativo = ""
        self.ficha.setText(traduzir("mt_escolha_arvore") if self.material else
                           traduzir("mt_escolha_aquisicao"))
        self.botao_conferir.setVisible(False)
        self.botao_pdf.setVisible(False)
        self.previas.setCurrentIndex(VAZIO)
        self.nota.setText(traduzir("mt_nota_somente_leitura"))

    def _escolher(self, item) -> None:
        if item is None or self.material is None or item.data(0, PAPEL_RELATIVO) is None:
            return
        if item.data(0, PAPEL_PASTA):
            self._limpar_ficha()
            self.ficha.setText(traduzir("mt_pasta", valor=item.data(0, PAPEL_RELATIVO)))
            return
        self._relativo = item.data(0, PAPEL_RELATIVO)
        self._conferir(forcar=False)
        self._mostrar_previa()

    def _conferir(self, forcar: bool) -> None:
        relativo = self._relativo
        try:
            tamanho = self.material.tamanho(relativo)
        except OSError as erro:
            self.ficha.setText(traduzir("mt_nao_leu", relativo=relativo, erro=erro))
            return
        base = traduzir("mt_base", nome=Path(relativo).name, relativo=relativo,
                        tamanho=_tamanho(tamanho))
        no_lacre = self.material.lacre().get(relativo, "")
        if not forcar and tamanho > LIMITE_PARA_CONFERIR_SOZINHO:
            self.ficha.setText(
                base
                + traduzir("mt_sha_lacre", valor=(no_lacre or traduzir("mt_nao_consta_lacre")))
                + traduzir("mt_arquivo_grande"))
            self.botao_conferir.setVisible(True)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            conferencia = self.material.conferir(relativo)
        finally:
            QApplication.restoreOverrideCursor()
        cor = {"confere": "#19c3a6", "DIVERGE": "#ff6b6b"}.get(conferencia.situacao, "#c77700")
        sinal = {"confere": traduzir("mt_sinal_confere"),
                 "DIVERGE": traduzir("mt_sinal_diverge")}.get(
            conferencia.situacao, traduzir("mt_sinal_nao_consta"))
        self.ficha.setText(
            base + traduzir("mt_sha_agora", valor=conferencia.sha256_agora)
            + (traduzir("mt_sha_lacre", valor=conferencia.sha256_no_lacre)
               if conferencia.sha256_no_lacre else "")
            + traduzir("mt_sinal_final", cor=cor, sinal=sinal)
        )
        self.botao_conferir.setVisible(False)

    def _mostrar_previa(self) -> None:
        relativo = self._relativo
        self.botao_pdf.setVisible(False)
        try:
            tipo = self.material.tipo_de_previa(relativo)
            if tipo == "imagem":
                leitor = QImageReader(str(self.material.caminho_para_leitura(relativo)))
                leitor.setAutoTransform(True)
                imagem = leitor.read()
                if imagem.isNull():
                    raise OSError(leitor.errorString())
                pixmap = QPixmap.fromImage(imagem)
                limite = max(200, self.previas.width() - 20)
                if pixmap.width() > limite:
                    pixmap = pixmap.scaledToWidth(limite, Qt.SmoothTransformation)
                self.imagem.setPixmap(pixmap)
                self.previas.setCurrentIndex(IMAGEM)
            elif tipo == "planilha":
                cabecalho, linhas, cortado = self.material.previa_planilha(relativo)
                self.tabela.clear()
                self.tabela.setColumnCount(len(cabecalho))
                self.tabela.setHorizontalHeaderLabels(cabecalho)
                self.tabela.setRowCount(len(linhas))
                for i, linha in enumerate(linhas):
                    for j, valor in enumerate(linha[:len(cabecalho)]):
                        self.tabela.setItem(i, j, QTableWidgetItem(valor))
                self.previas.setCurrentIndex(TABELA)
                if cortado:
                    self.nota.setText(traduzir("mt_previa_planilha", n=len(linhas)))
            elif tipo == "pdf":
                self.botao_pdf.setVisible(True)
                self.aviso.setText(traduzir("mt_aviso_pdf"))
                self.previas.setCurrentIndex(AVISO)
            elif tipo == "banco":
                tabelas, motivo = self.material.previa_banco(relativo)
                self.tabela.clear()
                self.tabela.setColumnCount(2)
                self.tabela.setHorizontalHeaderLabels(
                    [traduzir("mt_col_tabela"), traduzir("mt_col_registros")])
                self.tabela.setRowCount(len(tabelas))
                for i, (nome, quantidade) in enumerate(tabelas):
                    self.tabela.setItem(i, 0, QTableWidgetItem(nome))
                    self.tabela.setItem(i, 1, QTableWidgetItem(
                        str(quantidade) if quantidade >= 0 else traduzir("mt_ilegivel")))
                if tabelas:
                    self.previas.setCurrentIndex(TABELA)
                    self.nota.setText(traduzir("mt_nota_banco")
                                      + (f" {motivo}" if motivo else ""))
                else:
                    self.aviso.setText(traduzir("mt_banco_falhou", motivo=motivo))
                    self.previas.setCurrentIndex(AVISO)
            elif tipo == "texto":
                conteudo, cortado = self.material.previa_texto(relativo)
                self.texto.setPlainText(conteudo)
                self.previas.setCurrentIndex(TEXTO)
                if cortado:
                    self.nota.setText(traduzir("mt_previa_texto"))
            else:
                self.texto.setPlainText(self.material.previa_hex(relativo))
                self.previas.setCurrentIndex(TEXTO)
                self.nota.setText(traduzir("mt_previa_hex"))
        except Exception as erro:  # prévia nunca derruba a tela
            self.aviso.setText(traduzir("mt_previa_indisponivel", erro=erro))
            self.previas.setCurrentIndex(AVISO)

    def _exportar(self) -> None:
        if self.material is None:
            return
        escolhidos = [item.data(0, PAPEL_RELATIVO) for item in self.arvore.selectedItems()
                      if item.data(0, PAPEL_RELATIVO)]
        if not escolhidos:
            QMessageBox.information(self, traduzir("mt_exportar_titulo"), traduzir("mt_exportar_vazio"))
            return
        EntregaDialog(self.material.pasta, material=escolhidos, parent=self).exec()

    def _abrir_pdf(self) -> None:
        if self._relativo:
            abrir_pdf(self.material.caminho_para_leitura(self._relativo), self)
