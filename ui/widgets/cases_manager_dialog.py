"""
Janela de gerenciamento de casos e dispositivos já extraídos.
Permite navegar pelos casos, ver os dispositivos de cada um, retificar dados
e gerar os documentos da aquisição.

A retificação da PEÇA não tem botão próprio aqui: entra-se por "Retificar
Dados do Caso", que lista todos os dispositivos do caso.

Todo texto de tela vem do catálogo (`services.idioma.traduzir`): o molde é
traduzido; o valor capturado (erro, caminho, nome, resumo) é injetado por
`campos` e nunca passa pela tradução.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .case_dialog import CaseDialog
from .chave_dialog import ChaveDialog
from .conversas_dialog import ConversasDialog
from .entrega_dialog import EntregaDialog
from .material_widget import MaterialWidget
from .visualizador_pdf import abrir_pdf
from .device_info_dialog import DeviceInfoDialog
from .fundamento_dialog import AutorizacaoDialog
from .caderno_form_dialog import LAUDO, CadernoFormDialog
from PySide6.QtWidgets import QInputDialog, QLineEdit
from services.caderno_service import escapar
from services.case_service import (
    CaseService,
    gravar_protocolos_respondidos,
    ler_cadeia_custodia,
)
from services import ficha_service, laudo_service, relatorio_extracao_service, sessao_service
from services.idioma import traduzir
from services.decifragem_service import (
    decifrar_backup_ios,
    decifrar_whatsapp,
    senha_gerada_na_aquisicao,
)
from services.relatorio_service import RelatorioService, e_aquisicao_ios
from services.documentos_service import listar_documentos, salvar_copia
from services.exclusao_service import ErroDeExclusao, excluir_caso
from .ajuste_de_tela import caber_na_tela


class CasesManagerDialog(QDialog):
    """
    Gerenciador de casos com edição separada e geração dos documentos.
    """

    def __init__(self, pasta_extracoes: Path, parent=None):
        super().__init__(parent)
        self.pasta_extracoes = pasta_extracoes
        self.case_service = CaseService(pasta_extracoes)

        self.setWindowTitle(traduzir("gc_titulo_janela"))
        self.setModal(True)
        caber_na_tela(self, 1100, 700)
        self.setMinimumSize(900, 560)

        self._init_ui()
        self._carregar_projetos()

    def _init_ui(self) -> None:
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)

        # --- PAINEL ESQUERDO: LISTA DE PROJETOS ---
        widget_projetos = QWidget()
        layout_proj = QVBoxLayout(widget_projetos)
        layout_proj.setContentsMargins(0, 0, 0, 0)

        layout_proj.addWidget(QLabel(traduzir("gc_casos")))
        self.lista_projetos = QListWidget()
        self.lista_projetos.currentRowChanged.connect(self._ao_selecionar_projeto)
        layout_proj.addWidget(self.lista_projetos)
        self.botao_excluir_caso = QPushButton(traduzir("gc_btn_excluir_caso"))
        self.botao_excluir_caso.setEnabled(False)
        self.botao_excluir_caso.setToolTip(traduzir("gc_tt_excluir_caso"))
        self.botao_excluir_caso.clicked.connect(self._excluir_caso)
        layout_proj.addWidget(self.botao_excluir_caso)

        splitter.addWidget(widget_projetos)

        # --- PAINEL DIREITO: DISPOSITIVOS E DETALHES ---
        widget_detalhes = QWidget()
        layout_det = QVBoxLayout(widget_detalhes)
        layout_det.setContentsMargins(0, 0, 0, 0)

        # A ficha do caso aparece assim que o projeto e selecionado, sem
        # exigir que o examinador escolha uma aquisicao antes. Era esse o
        # custo do desenho anterior: o painel ficava vazio ate o segundo
        # clique, e descobrir do que tratava um caso custava dois cliques.
        layout_det.addWidget(QLabel(traduzir("gc_ficha_do_caso")))
        self.texto_ficha = QTextEdit()
        self.texto_ficha.setReadOnly(True)
        layout_det.addWidget(self.texto_ficha, stretch=1)

        layout_det.addWidget(QLabel(traduzir("gc_dispositivos_do_caso")))
        self.lista_dispositivos = QListWidget()
        self.lista_dispositivos.currentRowChanged.connect(self._ao_selecionar_dispositivo)
        self.lista_dispositivos.setMaximumHeight(120)
        layout_det.addWidget(self.lista_dispositivos)

        # Abas da aquisição selecionada: a cadeia de custódia e os
        # documentos gerados — estes abrem aqui mesmo, sem o Explorer.
        self.abas = QTabWidget()
        self.texto_detalhes = QTextEdit()
        self.texto_detalhes.setReadOnly(True)
        self.abas.addTab(self.texto_detalhes, traduzir("gc_aba_cadeia"))

        aba_documentos = QWidget()
        layout_docs = QVBoxLayout(aba_documentos)
        layout_docs.setContentsMargins(6, 6, 6, 6)
        self.lista_documentos = QListWidget()
        self.lista_documentos.setSelectionMode(QListWidget.ExtendedSelection)
        self.lista_documentos.itemDoubleClicked.connect(lambda _item: self._abrir_documento())
        layout_docs.addWidget(self.lista_documentos)
        linha_docs = QHBoxLayout()
        self.rotulo_documentos = QLabel()
        self.rotulo_documentos.setObjectName("TextoSecundario")
        linha_docs.addWidget(self.rotulo_documentos, 1)
        botao_abrir_doc = QPushButton(traduzir("gc_btn_abrir"))
        botao_abrir_doc.clicked.connect(self._abrir_documento)
        botao_copiar_doc = QPushButton(traduzir("gc_btn_salvar_copia"))
        botao_copiar_doc.clicked.connect(self._copiar_documento)
        botao_exportar_doc = QPushButton(traduzir("gc_btn_exportar"))
        botao_exportar_doc.setToolTip(traduzir("gc_tt_exportar"))
        botao_exportar_doc.clicked.connect(self._exportar_documentos)
        linha_docs.addWidget(botao_abrir_doc)
        linha_docs.addWidget(botao_copiar_doc)
        linha_docs.addWidget(botao_exportar_doc)
        layout_docs.addLayout(linha_docs)
        self.abas.addTab(aba_documentos, traduzir("gc_aba_documentos"))
        # O que foi adquirido, examinado aqui mesmo e só para leitura: abrir a
        # pasta lacrada no Explorer pode criar Thumbs.db/desktop.ini dentro dela.
        self.material = MaterialWidget()
        self.abas.addTab(self.material, traduzir("gc_aba_material"))
        layout_det.addWidget(self.abas, stretch=4)

        # --- BOTÕES DE AÇÃO ---

        self.botao_editar_caso = QPushButton(traduzir("gc_btn_editar_caso"))
        self.botao_editar_caso.setEnabled(False)
        self.botao_editar_caso.clicked.connect(self._editar_metadados_caso)

        self.botao_autorizacao = QPushButton(traduzir("gc_btn_autorizacao"))
        self.botao_autorizacao.setEnabled(False)
        self.botao_autorizacao.setToolTip(traduzir("gc_tt_autorizacao"))
        self.botao_autorizacao.clicked.connect(self._anexar_autorizacao)

        # "Relatório" sugeria um documento; o que sai sao varios arquivos --
        # um CSV por artefato, o PDF consolidado, a procedencia e os
        # descartes contados. O rotulo passa a dizer o que o botao faz.
        self.botao_relatorio = QPushButton(traduzir("gc_btn_relatorio"))
        self._habilitar_documentos(False)
        self.botao_relatorio.setToolTip(traduzir("gc_tt_relatorio"))
        self.botao_relatorio.clicked.connect(self._gerar_relatorio_conteudo)


        self.botao_relatorio_extracao = QPushButton(traduzir("gc_btn_relatorio_extracao"))
        self.botao_relatorio_extracao.setEnabled(False)
        self.botao_relatorio_extracao.setToolTip(traduzir("gc_tt_relatorio_extracao"))
        self.botao_relatorio_extracao.clicked.connect(self._gerar_relatorio_de_extracao)

        self.botao_ficha = QPushButton(traduzir("gc_btn_ficha"))
        self.botao_ficha.setEnabled(False)
        self.botao_ficha.setToolTip(traduzir("gc_tt_ficha"))
        self.botao_ficha.clicked.connect(self._gerar_ficha_do_aparelho)

        self.botao_laudo_pericial = QPushButton(traduzir("gc_btn_laudo"))
        self.botao_laudo_pericial.setEnabled(False)
        self.botao_laudo_pericial.setToolTip(traduzir("gc_tt_laudo"))
        self.botao_laudo_pericial.clicked.connect(self._gerar_laudo_pericial)

        self.botao_conversas = QPushButton(traduzir("gc_btn_conversas"))
        self.botao_conversas.setEnabled(False)
        self.botao_conversas.setToolTip(traduzir("gc_tt_conversas"))
        self.botao_conversas.clicked.connect(self._pdf_de_conversas)

        self.botao_decifrar = QPushButton(traduzir("gc_btn_decifrar"))
        self.botao_decifrar.setEnabled(False)
        self.botao_decifrar.setToolTip(traduzir("gc_tt_decifrar"))
        self.botao_decifrar.clicked.connect(self._decifrar_whatsapp)

        # Grade de três colunas, na ordem do trabalho: o caso; o conteúdo
        # (decifrar, ler, escolher conversas); os documentos; e o Laudo, que
        # é o produto final, sozinho na última linha. Em linhas soltas de dois
        # e de um botão a tela parecia montada por acaso.
        grade = QGridLayout()
        grade.setHorizontalSpacing(8)
        grade.setVerticalSpacing(6)
        disposicao = (
            (self.botao_editar_caso, 0, 0), (self.botao_autorizacao, 0, 1),
            (self.botao_decifrar, 0, 2),
            (self.botao_relatorio_extracao, 1, 0), (self.botao_relatorio, 1, 1),
            (self.botao_conversas, 1, 2),
        )
        for botao, linha, coluna in disposicao:
            grade.addWidget(botao, linha, coluna)
        grade.addWidget(self.botao_ficha, 2, 0)
        grade.addWidget(self.botao_laudo_pericial, 2, 1, 1, 2)
        for coluna in range(3):
            grade.setColumnStretch(coluna, 1)
        layout_det.addLayout(grade)



        splitter.addWidget(widget_detalhes)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        # Largura inicial explicita: sem ela o splitter parte do sizeHint e
        # deixa a coluna dos casos estreita demais, cortando justamente a
        # linha (referência, descrição) que existe para o caso ser
        # reconhecido sem abrir.
        splitter.setSizes([380, 720])

        layout_principal.addWidget(splitter)

    def _habilitar_documentos(self, habilitar: bool) -> None:
        """Liga ou desliga, juntos, os botões que dependem de uma aquisição escolhida."""
        self.botao_relatorio.setEnabled(habilitar)
        for nome in ("botao_relatorio_extracao", "botao_ficha", "botao_laudo_pericial",
                     "botao_decifrar", "botao_conversas"):
            botao = getattr(self, nome, None)
            if botao is not None:
                botao.setEnabled(habilitar)

    def _aquisicao_selecionada(self):
        """Pasta da aquisição escolhida na lista, ou `None`."""
        linha = self.lista_dispositivos.currentRow()
        if linha < 0:
            return None
        arq_custodia = self.lista_dispositivos.item(linha).data(Qt.UserRole + 2)
        return Path(arq_custodia).parent if arq_custodia else None

    def _informar_documento(self, titulo: str, documento) -> None:
        if documento.erro:
            QMessageBox.critical(
                self, traduzir("gc_doc_nao_gerado_titulo"),
                traduzir("gc_doc_nao_gerado_corpo", erro=documento.erro),
            )
            return
        self._carregar_documentos()
        abrir_pdf(documento.caminho, self)

    def _pdf_de_conversas(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao"))
            return
        ConversasDialog(pasta_aquisicao, parent=self).exec()

    def _decifrar_whatsapp(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao"))
            return
        if e_aquisicao_ios(pasta_aquisicao):
            # No iPhone o que se decifra é o backup inteiro, com a senha de
            # backup que o dono definiu (não o código de desbloqueio).
            gerada = senha_gerada_na_aquisicao(pasta_aquisicao)
            if gerada:
                # O módulo de backup cifrado gerou a senha e a guardou sob o
                # selo: o examinador só confirma, sem copiar do log.
                senha, confirmado = QInputDialog.getText(
                    self, traduzir("gc_senha_iphone_titulo"),
                    traduzir("gc_senha_iphone_gerada"),
                    QLineEdit.Normal, gerada,
                )
            else:
                senha, confirmado = QInputDialog.getText(
                    self, traduzir("gc_senha_iphone_titulo"),
                    traduzir("gc_senha_iphone_definida"),
                    QLineEdit.Password,
                )
            if not confirmado or not senha:
                return
            decifrar = lambda: decifrar_backup_ios(pasta_aquisicao, senha)  # noqa: E731
        else:
            dialogo_chave = ChaveDialog(parent=self)
            if dialogo_chave.exec() != QDialog.Accepted:
                return
            chave = dialogo_chave.chave()
            decifrar = lambda: decifrar_whatsapp(pasta_aquisicao, chave)  # noqa: E731

        self.setCursor(Qt.WaitCursor)
        try:
            resultado = decifrar()
        finally:
            self.unsetCursor()

        if resultado.erro:
            QMessageBox.warning(self, traduzir("gc_nada_decifrado"), resultado.erro)
            return
        QMessageBox.information(
            self,
            traduzir("gc_backup_decifrado_titulo"),
            traduzir("gc_backup_decifrado_corpo", resumo=resultado.resumo, pasta=resultado.pasta),
        )
        # Decifrar não mostra mensagem nenhuma por si: quem as mostra é o
        # relatório de conteúdo. Sem gerá-lo aqui, o examinador decifra e
        # fica procurando onde as conversas foram parar.
        self._gerar_relatorio_conteudo()

    def _gerar_relatorio_de_extracao(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao"))
            return
        self.setCursor(Qt.WaitCursor)
        try:
            documento = relatorio_extracao_service.gerar(pasta_aquisicao)
        finally:
            self.unsetCursor()
        self._informar_documento(traduzir("gc_relatorio_extracao_gerado"), documento)

    def _gerar_ficha_do_aparelho(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao"))
            return
        self.setCursor(Qt.WaitCursor)
        try:
            documento = ficha_service.gerar(pasta_aquisicao)
        finally:
            self.unsetCursor()
        self._informar_documento(traduzir("gc_ficha_gerada"), documento)

    def _gerar_laudo_pericial(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao"))
            return

        # Quem subscreve é o examinador da sessão, confirmado a cada laudo:
        # pode não ser quem fez a extração, e o laudo mostra os dois.
        resposta = QMessageBox.question(
            self, traduzir("gc_examinador_subscreve_titulo"),
            traduzir("gc_examinador_subscreve_corpo", nome=sessao_service.nome()),
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Ok,
        )
        if resposta != QMessageBox.Ok:
            return

        dados_caso = self._obter_dados_atuais()
        pasta_fotos = pasta_aquisicao / "evidencias_fotos"
        dados_disp = dict(
            dados_caso, fotos=sorted(pasta_fotos.glob("*")) if pasta_fotos.exists() else []
        )
        formulario = CadernoFormDialog(
            dados_caso, dados_disp, pasta_aquisicao=pasta_aquisicao, parent=self,
            finalidade=LAUDO,
        )
        if formulario.exec() != QDialog.Accepted:
            return
        dados_formulario = formulario.dados_atualizados_formulario()

        self.setCursor(Qt.WaitCursor)
        try:
            documento = laudo_service.gerar(
                pasta_aquisicao, dados_formulario, sessao_service.dados()
            )
        finally:
            self.unsetCursor()

        if not documento.erro:
            # As respostas do examinador viram complemento ao caso, como no
            # caderno: sem isso existiriam só dentro do PDF.
            try:
                gravar_protocolos_respondidos(
                    pasta_aquisicao,
                    dados_formulario.get("protocolos") or [],
                    dados_formulario.get("observacoes", ""),
                )
            except OSError as erro:
                QMessageBox.warning(
                    self, traduzir("gc_atencao"),
                    traduzir("gc_laudo_protocolos_falha", erro=erro),
                )
        self._informar_documento(traduzir("gc_laudo_gerado"), documento)

    def _carregar_projetos(self) -> None:
        self.lista_projetos.clear()
        self.botao_editar_caso.setEnabled(False)
        self.botao_autorizacao.setEnabled(False)
        self._habilitar_documentos(False)
        if not self.pasta_extracoes.exists():
            return

        # A lista deixa de ser um diretorio de pastas e passa a ser um
        # indice de casos: o examinador acha o caso VARRENDO a lista, sem
        # abrir um a um. Quem le o disco e monta o resumo e o servico.
        self._resumos = self.case_service.listar_resumos_casos()
        for resumo in self._resumos:
            item = QListWidgetItem(self._rotulo_do_caso(resumo))
            item.setData(Qt.UserRole, resumo.pasta)
            self.lista_projetos.addItem(item)

        if not self._resumos:
            self.texto_ficha.setText(traduzir("gc_nenhum_caso"))

    @staticmethod
    def _rotulo_do_caso(resumo) -> str:
        """
        Duas linhas por caso: o identificador e o que permite reconhece-lo.

        Campo em branco simplesmente nao aparece — nunca vira "N/A" nem
        traco. A lista mostra o que o registro tem, e o silencio dela sobre
        um campo significa que ninguem preencheu aquele campo.
        """
        partes = list(resumo.reconhecimento)
        quantas = len(resumo.aquisicoes)
        partes.append(
            traduzir("gc_rotulo_aquisicoes", quantas=quantas) if quantas != 1
            else traduzir("gc_rotulo_uma_aquisicao")
        )
        if resumo.lacres:
            partes.append(traduzir("gc_rotulo_lacre", lacres=", ".join(resumo.lacres)))
        if resumo.examinadores:
            rotulo = (traduzir("gc_examinador_sing") if len(resumo.examinadores) == 1
                      else traduzir("gc_examinador_plur"))
            partes.append(traduzir(
                "gc_rotulo_examinador_linha", rotulo=rotulo,
                nomes=", ".join(resumo.examinadores),
            ))
        if resumo.ultima_atividade:
            partes.append(resumo.ultima_atividade.strftime("%d/%m/%Y"))
        if resumo.metadados_divergentes:
            partes.append(traduzir("gc_metadados_divergentes"))
        return f"{resumo.identificador}\n{'  ·  '.join(partes)}"

    def _ao_selecionar_projeto(self, row: int) -> None:
        self.lista_dispositivos.clear()
        self.texto_detalhes.clear()
        self.texto_ficha.clear()
        self._habilitar_documentos(False)

        self.botao_excluir_caso.setEnabled(row >= 0)
        if row < 0:
            self.botao_editar_caso.setEnabled(False)
            self.botao_autorizacao.setEnabled(False)
            return

        self.botao_editar_caso.setEnabled(True)
        self.botao_autorizacao.setEnabled(True)

        pasta_proj: Path = self.lista_projetos.item(row).data(Qt.UserRole)
        try:
            resumo = self.case_service.resumo_do_caso(pasta_proj)
        except Exception as erro:
            self.texto_ficha.setText(traduzir("gc_erro_ler_caso", erro=erro))
            return

        self.texto_ficha.setHtml(self._montar_ficha(resumo))

        for aquisicao in resumo.aquisicoes:
            selo = traduzir("gc_selada") if aquisicao.selada else traduzir("gc_aberta")
            item = QListWidgetItem(traduzir(
                "gc_rotulo_aquisicao",
                rotulo=aquisicao.rotulo,
                examinador=aquisicao.examinador or traduzir("gc_nao_registrado"),
                selo=selo,
            ))
            # Contrato de dados preservado: os manipuladores de edicao,
            # caderno e conteudo leem exatamente estes tres papeis.
            item.setData(Qt.UserRole, aquisicao.pasta)
            item.setData(
                Qt.UserRole + 1,
                aquisicao.arquivo_custodia.read_text(encoding="utf-8")
                if aquisicao.arquivo_custodia
                else "",
            )
            item.setData(Qt.UserRole + 2, aquisicao.arquivo_custodia)
            self.lista_dispositivos.addItem(item)

        if not resumo.aquisicoes:
            self.texto_detalhes.setText(traduzir("gc_sem_aquisicao"))
        else:
            # A primeira aquisição já vem selecionada. Sem isso os botões de
            # documento ficavam desligados até um clique na lista de
            # dispositivos, que nada na tela pedia — e pareciam quebrados.
            self.lista_dispositivos.setCurrentRow(0)

    def _montar_ficha(self, resumo) -> str:
        """
        A ficha do caso em HTML: o que foi cadastrado, o que foi anexado e
        quantas aquisições existem — tudo legível sem abrir nada.

        Campo ausente aparece como "não informado", e isso é diferente de
        omiti-lo: quem lê precisa distinguir "o registro não tem esse dado"
        de "a tela não mostra esse dado".
        """
        def linha(rotulo: str, valor: str) -> str:
            valor = escapar(valor) if valor else traduzir("gc_ficha_nao_informado")
            return f"<tr><td><b>{escapar(rotulo)}</b></td><td>{valor}</td></tr>"

        partes = [f"<h3>{escapar(resumo.identificador)}</h3>"]

        if resumo.metadados_divergentes:
            # Num caso antigo os dados do caso vivem dentro de cada
            # aquisicao. Quando elas discordam, escolher uma versao em
            # silencio seria a ferramenta afirmando o que nao verificou.
            campos = ", ".join(resumo.campos_divergentes)
            partes.append(traduzir("gc_ficha_divergentes", campos=escapar(campos)))

        if not resumo.tem_registro:
            partes.append(traduzir("gc_ficha_caso_anterior"))

        partes.append("<table cellpadding='3'>")
        for campo, valor in resumo.dados_do_caso.items():
            partes.append(linha(campo, valor))
        partes.append("</table>")

        if resumo.lacres:
            partes.append(traduzir("gc_ficha_lacres", valor=escapar(', '.join(resumo.lacres))))
        if resumo.examinadores:
            partes.append(traduzir(
                "gc_ficha_examinadores", valor=escapar(', '.join(resumo.examinadores))
            ))

        partes.append(traduzir("gc_ficha_aquisicoes", valor=len(resumo.aquisicoes)))
        self._dados_do_caso_na_ficha = dict(resumo.dados_do_caso)

        if resumo.documentos:
            partes.append(traduzir("gc_ficha_autorizacao_anexada"))
            for documento in resumo.documentos:
                partes.append(traduzir(
                    "gc_ficha_doc_item",
                    rotulo=escapar(documento.get('rotulo') or documento.get('tipo', '')),
                    nome=escapar(documento.get('nome', '')),
                ))
            partes.append("</ul>")
        else:
            partes.append(traduzir("gc_ficha_sem_autorizacao"))

        if resumo.complementos:
            partes.append(traduzir("gc_ficha_complementos", valor=resumo.complementos))

        partes.append(traduzir("gc_ficha_pasta", valor=escapar(str(resumo.pasta))))
        return "".join(partes)

    def _ao_selecionar_dispositivo(self, row: int) -> None:
        if row < 0:
            self._habilitar_documentos(False)
            self._carregar_documentos()
            return

        item = self.lista_dispositivos.item(row)
        conteudo_custodia = item.data(Qt.UserRole + 1)
        caminho_pasta: Path = item.data(Qt.UserRole)

        self._carregar_documentos()
        if conteudo_custodia:
            texto_completo = traduzir(
                "gc_caminho_arquivos", conteudo=conteudo_custodia, caminho=caminho_pasta
            )
            self.texto_detalhes.setText(texto_completo)
            self._habilitar_documentos(True)
        else:
            self.texto_detalhes.setText(traduzir("gc_diretorio", caminho=caminho_pasta))
            self._habilitar_documentos(False)

    def _excluir_caso(self) -> None:
        linha = self.lista_projetos.currentRow()
        if linha < 0:
            return
        pasta_caso: Path = self.lista_projetos.item(linha).data(Qt.UserRole)
        confirmacao, confirmado = QInputDialog.getText(
            self, traduzir("gc_excluir_titulo"),
            traduzir("gc_excluir_corpo", nome=pasta_caso.name),
        )
        if not confirmado:
            return
        try:
            excluir_caso(pasta_caso, confirmacao, casos=self.case_service)
        except ErroDeExclusao as erro:
            QMessageBox.warning(self, traduzir("gc_caso_nao_excluido"), str(erro))
            return
        QMessageBox.information(
            self, traduzir("gc_caso_excluido_titulo"),
            traduzir("gc_caso_excluido_corpo", nome=pasta_caso.name))
        self._carregar_projetos()

    # ------------------------------------------------------------------
    # Documentos do caso
    # ------------------------------------------------------------------
    def _carregar_documentos(self) -> None:
        self.lista_documentos.clear()
        pasta_aquisicao = self._aquisicao_selecionada()
        self.material.definir_aquisicao(pasta_aquisicao)
        if pasta_aquisicao is None:
            self.rotulo_documentos.setText("")
            return
        documentos = listar_documentos(pasta_aquisicao.parent, pasta_aquisicao.name)
        for documento in documentos:
            item = QListWidgetItem(f"{documento.tipo}  ·  {documento.gerado_em:%d/%m/%Y %H:%M}"
                                   f"  ·  {documento.caminho.name}")
            item.setData(Qt.UserRole, str(documento.caminho))
            self.lista_documentos.addItem(item)
        self.rotulo_documentos.setText(
            traduzir("gc_docs_contagem", n=len(documentos)) if documentos
            else traduzir("gc_docs_nenhum")
        )
        self.abas.setTabText(1, traduzir("gc_aba_documentos_contagem", n=len(documentos)))
        if documentos:
            self.lista_documentos.setCurrentRow(0)

    def _documento_escolhido(self):
        item = self.lista_documentos.currentItem()
        if item is None:
            QMessageBox.information(
                self, traduzir("gc_documentos_titulo"), traduzir("gc_escolha_documento")
            )
            return None
        return Path(item.data(Qt.UserRole))

    def _abrir_documento(self) -> None:
        caminho = self._documento_escolhido()
        if caminho is not None:
            abrir_pdf(caminho, self)

    def _exportar_documentos(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        escolhidos = [Path(item.data(Qt.UserRole)) for item in self.lista_documentos.selectedItems()]
        if pasta_aquisicao is None or not escolhidos:
            QMessageBox.information(
                self, traduzir("gc_exportar_titulo"), traduzir("gc_selecione_documentos")
            )
            return
        EntregaDialog(pasta_aquisicao, documentos=escolhidos, parent=self).exec()

    def _copiar_documento(self) -> None:
        caminho = self._documento_escolhido()
        if caminho is None:
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, traduzir("gc_salvar_copia_titulo"), str(Path.home() / caminho.name),
            traduzir("gc_filtro_pdf"),
        )
        if not destino:
            return
        try:
            resumo = salvar_copia(caminho, Path(destino))
        except OSError as erro:
            QMessageBox.critical(self, traduzir("gc_copia_nao_salva"), str(erro))
            return
        QMessageBox.information(
            self, traduzir("gc_copia_salva_titulo"),
            traduzir("gc_copia_salva_corpo", destino=destino, resumo=resumo),
        )

    def _obter_dados_atuais(self) -> dict:
        """
        Dados da aquisição SELECIONADA, ou vazio se nenhuma estiver.

        A versão anterior, sem seleção, caía em
        `pasta_proj.glob("**/cadeia_custodia.txt")[0]` — a primeira que o
        sistema de arquivos devolvesse. Num caso com várias aquisições (que
        é a premissa do projeto) isso escolhia uma aquisição arbitrária para
        receber a retificação, e deixava as outras com o dado velho, sem
        avisar. Escolher em silêncio é pior que exigir a escolha.
        """
        linha_atual = self.lista_dispositivos.currentRow()
        if linha_atual < 0:
            return {}

        arq_custodia = self.lista_dispositivos.item(linha_atual).data(Qt.UserRole + 2)
        if not arq_custodia or not Path(arq_custodia).is_file():
            return {}
        return ler_cadeia_custodia(Path(arq_custodia))

    def _editar_metadados_caso(self) -> None:
        """
        Retifica os dados do CASO, no registro único do caso.

        Já não se escolhe aquisição: os dados do caso deixaram de morar
        dentro delas. Cada aquisição guarda, sob o selo, os dados como
        estavam no dia; a retificação entra como complemento.
        """
        linha = self.lista_projetos.currentRow()
        if linha < 0:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_caso"))
            return
        pasta_caso: Path = self.lista_projetos.item(linha).data(Qt.UserRole)

        dialogo_caso = CaseDialog(
            self.case_service,
            "",
            parent=self,
            modo_edicao=True,
            dados_iniciais=self.case_service.dados_do_caso(pasta_caso.name),
            dispositivos=[
                self.lista_dispositivos.item(i).text()
                for i in range(self.lista_dispositivos.count())
            ],
        )
        if dialogo_caso.exec() != QDialog.Accepted:
            return
        dispositivo = dialogo_caso.dispositivo_a_retificar()

        try:
            alterado = self.case_service.retificar_caso(pasta_caso, dialogo_caso.dados_metadados())
        except OSError as erro:
            QMessageBox.critical(self, traduzir("gc_erro"), traduzir("gc_nao_gravar", erro=erro))
            return
        if alterado:
            QMessageBox.information(
                self,
                traduzir("gc_caso_retificado_titulo"),
                traduzir("gc_caso_retificado_corpo"),
            )
        self._carregar_projetos()
        self.lista_projetos.setCurrentRow(linha)
        # Pedido feito de dentro da janela do caso: segue para a peça escolhida.
        if dispositivo is not None and dispositivo < self.lista_dispositivos.count():
            self.lista_dispositivos.setCurrentRow(dispositivo)
            self._editar_dispositivo_selecionado()

    def _gravar_ou_complementar(self, arquivo_custodia: Path, conteudo: str, titulo: str) -> bool:
        """
        Grava a alteração — mas nunca por cima de uma aquisição já selada.

        Reescrever uma aquisição selada faria o caso divergir do próprio
        manifesto, e destruiria o registro do que existia no momento do
        exame. É a regra de todo registro formal: não se rasura folha,
        junta-se aditamento. Por isso, quando a aquisição está selada, a
        alteração vira **complemento** no nível do caso, preservando o
        original e registrando o que mudou.
        """
        pasta_aquisicao = arquivo_custodia.parent

        if not self.case_service.aquisicao_selada(pasta_aquisicao):
            try:
                arquivo_custodia.write_text(conteudo, encoding="utf-8")
                QMessageBox.information(
                    self, traduzir("gc_sucesso"), traduzir("gc_dados_atualizados")
                )
                return True
            except OSError as erro:
                QMessageBox.critical(self, traduzir("gc_erro"), traduzir("gc_nao_salvar", erro=erro))
                return False

        resposta = QMessageBox.question(
            self,
            traduzir("gc_selada_titulo"),
            traduzir("gc_selada_corpo"),
        )
        if resposta != QMessageBox.Yes:
            return False

        return self._registrar_complemento(pasta_aquisicao.parent, titulo, conteudo)

    def _anexar_autorizacao(self) -> None:
        """
        Anexa o documento de autorização a um caso que já existe.

        É a rotina real: a decisão costuma ser digitalizada dias depois da
        coleta. O documento entra no nível do caso e o caso é reselado —
        nenhuma aquisição já selada é reescrita, e cada uma continua
        registrando o que estava à vista no dia em que foi feita.
        """
        linha = self.lista_projetos.currentRow()
        if linha < 0:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_caso"))
            return

        pasta_caso: Path = self.lista_projetos.item(linha).data(Qt.UserRole)

        dialogo = AutorizacaoDialog(
            self.case_service.documentos_do_caso(pasta_caso.name), parent=self
        )
        if dialogo.exec() != QDialog.Accepted:
            return

        documentos = dialogo.documentos()
        if not documentos:
            return

        anexados = []
        for documento in documentos:
            try:
                caminho = self.case_service.anexar_ao_caso(
                    pasta_caso,
                    documento["tipo"],
                    Path(documento["arquivo"]),
                    documento.get("descricao", ""),
                )
            except (ValueError, OSError) as erro:
                QMessageBox.critical(
                    self,
                    traduzir("gc_erro"),
                    traduzir("gc_nao_anexar", nome=Path(documento['arquivo']).name, erro=erro),
                )
                continue
            anexados.append(caminho.name)

        if not anexados:
            return

        QMessageBox.information(
            self,
            traduzir("gc_autorizacao_anexada_titulo"),
            traduzir("gc_autorizacao_anexada_corpo", lista="\n  ".join(anexados)),
        )
        self._ao_selecionar_projeto(linha)

    def _registrar_complemento(self, pasta_caso: Path, titulo: str, texto: str) -> bool:
        try:
            caminho = self.case_service.juntar_complemento(pasta_caso, titulo, texto)
        except OSError as erro:
            QMessageBox.critical(
                self, traduzir("gc_erro"), traduzir("gc_complemento_erro", erro=erro)
            )
            return False

        QMessageBox.information(
            self,
            traduzir("gc_complemento_juntado_titulo"),
            traduzir("gc_complemento_juntado_corpo", nome=caminho.name),
        )
        return True

    def _editar_dispositivo_selecionado(self) -> None:
        linha_atual = self.lista_dispositivos.currentRow()
        if linha_atual < 0:
            QMessageBox.warning(
                self, traduzir("gc_aviso"), traduzir("gc_selecione_dispositivo_retificar")
            )
            return

        item = self.lista_dispositivos.item(linha_atual)
        arq_custodia: Path = item.data(Qt.UserRole + 2)
        if not arq_custodia or not arq_custodia.is_file():
            return

        dados_atuais = ler_cadeia_custodia(arq_custodia)

        dialogo_disp = DeviceInfoDialog(parent=self, modo_edicao=True)
        dialogo_disp.setWindowTitle(traduzir("gc_retificar_dispositivo_titulo"))

        dialogo_disp.campo_marca_modelo.setText(dados_atuais.get("Equipamento", ""))
        dialogo_disp.campo_cor.setText(dados_atuais.get("Cor", ""))
        dialogo_disp.campo_estado.setText(dados_atuais.get("Estado", ""))
        dialogo_disp.campo_lacre.setText(dados_atuais.get("Lacre", ""))

        if dialogo_disp.exec() != QDialog.Accepted:
            return

        novo_conteudo = self.case_service.cadeia_com_dispositivo_retificado(
            arq_custodia, dialogo_disp.dados_dispositivo()
        )

        if self._gravar_ou_complementar(
            arq_custodia, novo_conteudo, "Retificação de dados do dispositivo"
        ):
            self._ao_selecionar_projeto(self.lista_projetos.currentRow())

    def _gerar_relatorio_conteudo(self) -> None:
        """
        Converte SMS, chamadas e agenda em planilhas e PDF legíveis.

        É o entregável da investigação: a aquisição guarda o dump bruto do
        aparelho, fiel e ilegível, e este relatório o apresenta em forma que
        o analista consegue trabalhar — sem substituí-lo, e sem tocar nele.
        """
        linha = self.lista_dispositivos.currentRow()
        if linha < 0:
            QMessageBox.warning(self, traduzir("gc_aviso"), traduzir("gc_selecione_dispositivo"))
            return

        arq_custodia = self.lista_dispositivos.item(linha).data(Qt.UserRole + 2)
        if arq_custodia is None:
            QMessageBox.warning(
                self, traduzir("gc_aviso"), traduzir("gc_selecione_aquisicao_especifica")
            )
            return

        pasta_aquisicao = Path(arq_custodia).parent

        # O fuso é escolhido, nunca suposto: converter epoch para hora local
        # é interpretação, e o aparelho pode estar em fuso diferente do da
        # estação. O que for escolhido fica declarado no relatório.
        local = datetime.now().astimezone().tzinfo
        rotulo_local = traduzir(
            "gc_fuso_estacao", zona=datetime.now().astimezone().strftime('%Z%z')
        )
        opcoes = [rotulo_local, traduzir("gc_fuso_utc")]
        escolha, confirmado = QInputDialog.getItem(
            self,
            traduzir("gc_fuso_titulo"),
            traduzir("gc_fuso_corpo"),
            opcoes,
            0,
            False,
        )
        if not confirmado:
            return

        fuso = local if escolha == rotulo_local else None
        resultado = RelatorioService.gerar(pasta_aquisicao, fuso=fuso)

        if resultado.erro:
            QMessageBox.warning(self, traduzir("gc_nada_relatar"), resultado.erro)
            return

        partes = [
            traduzir("gc_relatorio_gravado", pasta=resultado.pasta),
            "\n".join(resultado.resumo_por_artefato),
        ]
        if not resultado.total_registros:
            # Sem esta linha, o examinador sai procurando planilha que não
            # existe — foi o que aconteceu na primeira execução real.
            partes.append(traduzir("gc_sem_planilha"))
        if resultado.total_descartes:
            partes.append(traduzir("gc_descartes", n=resultado.total_descartes))
        if resultado.origens_divergentes:
            partes.append(traduzir(
                "gc_origens_divergentes", origens=", ".join(resultado.origens_divergentes)
            ))
        partes += [
            "",
            traduzir("gc_relatorio_nao_altera"),
        ]

        mensagem = "\n\n".join(partes)
        com_ressalva = (
            resultado.total_descartes
            or resultado.origens_divergentes
            or not resultado.total_registros
        )
        if com_ressalva:
            QMessageBox.warning(self, traduzir("gc_relatorio_ressalvas_titulo"), mensagem)
        else:
            QMessageBox.information(self, traduzir("gc_relatorio_conteudo_gerado"), mensagem)

        # Abre o PDF: o relatório existe para ser lido, e dizer só em que
        # pasta ele ficou obrigava a ir buscá-lo.
        pdf = next((arquivo for arquivo in resultado.arquivos_gerados
                    if str(arquivo).lower().endswith(".pdf")), None)
        self._carregar_documentos()
        if pdf is not None:
            abrir_pdf(pdf, self)
