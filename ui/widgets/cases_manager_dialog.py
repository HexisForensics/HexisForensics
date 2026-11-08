"""
Janela de gerenciamento de casos e dispositivos já extraídos.
Permite navegar pelos casos, ver os dispositivos de cada um, retificar dados
e gerar os documentos da aquisição.

A retificação da PEÇA não tem botão próprio aqui: entra-se por "Retificar
Dados do Caso", que lista todos os dispositivos do caso.
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
from services import laudo_service, relatorio_extracao_service, sessao_service
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

        self.setWindowTitle("Gerenciador de Casos e Cadeia de Custódia")
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
        
        layout_proj.addWidget(QLabel("<b>Casos:</b>"))
        self.lista_projetos = QListWidget()
        self.lista_projetos.currentRowChanged.connect(self._ao_selecionar_projeto)
        layout_proj.addWidget(self.lista_projetos)
        self.botao_excluir_caso = QPushButton("🗑 Excluir caso…")
        self.botao_excluir_caso.setEnabled(False)
        self.botao_excluir_caso.setToolTip(
            "Envia o caso inteiro à Lixeira do Windows (restaurável), depois de confirmar "
            "digitando o nome dele. A exclusão fica no registro de acessos.")
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
        layout_det.addWidget(QLabel("<b>Ficha do Caso</b>"))
        self.texto_ficha = QTextEdit()
        self.texto_ficha.setReadOnly(True)
        layout_det.addWidget(self.texto_ficha, stretch=1)

        layout_det.addWidget(QLabel(
            "<b>Dispositivos do caso</b> — os botões de documento abaixo valem para o "
            "dispositivo <b>selecionado nesta lista</b>:"
        ))
        self.lista_dispositivos = QListWidget()
        self.lista_dispositivos.currentRowChanged.connect(self._ao_selecionar_dispositivo)
        self.lista_dispositivos.setMaximumHeight(120)
        layout_det.addWidget(self.lista_dispositivos)

        # Abas da aquisição selecionada: a cadeia de custódia e os
        # documentos gerados — estes abrem aqui mesmo, sem o Explorer.
        self.abas = QTabWidget()
        self.texto_detalhes = QTextEdit()
        self.texto_detalhes.setReadOnly(True)
        self.abas.addTab(self.texto_detalhes, "Cadeia de custódia")

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
        botao_abrir_doc = QPushButton("📄 Abrir")
        botao_abrir_doc.clicked.connect(self._abrir_documento)
        botao_copiar_doc = QPushButton("💾 Salvar cópia em…")
        botao_copiar_doc.clicked.connect(self._copiar_documento)
        botao_exportar_doc = QPushButton("📤 Exportar para entrega…")
        botao_exportar_doc.setToolTip(
            "Copia os documentos selecionados (Ctrl/Shift para vários) para um pendrive ou "
            "pasta, confere cada cópia pelo hash, emite recibo e registra no caso.")
        botao_exportar_doc.clicked.connect(self._exportar_documentos)
        linha_docs.addWidget(botao_abrir_doc)
        linha_docs.addWidget(botao_copiar_doc)
        linha_docs.addWidget(botao_exportar_doc)
        layout_docs.addLayout(linha_docs)
        self.abas.addTab(aba_documentos, "Documentos")
        # O que foi adquirido, examinado aqui mesmo e só para leitura: abrir a
        # pasta lacrada no Explorer pode criar Thumbs.db/desktop.ini dentro dela.
        self.material = MaterialWidget()
        self.abas.addTab(self.material, "Material")
        layout_det.addWidget(self.abas, stretch=4)

        # --- BOTÕES DE AÇÃO ---

        self.botao_editar_caso = QPushButton("📁 Retificar Dados do Caso")
        self.botao_editar_caso.setEnabled(False)
        self.botao_editar_caso.clicked.connect(self._editar_metadados_caso)

        self.botao_autorizacao = QPushButton("⚖ Anexar Autorização")
        self.botao_autorizacao.setEnabled(False)
        self.botao_autorizacao.setToolTip(
            "Anexa ao caso a decisão judicial, o termo de consentimento ou a requisição — inclusive "
            "quando o documento só foi digitalizado depois da coleta."
        )
        self.botao_autorizacao.clicked.connect(self._anexar_autorizacao)

        # "Relatório" sugeria um documento; o que sai sao varios arquivos --
        # um CSV por artefato, o PDF consolidado, a procedencia e os
        # descartes contados. O rotulo passa a dizer o que o botao faz.
        self.botao_relatorio = QPushButton("📊 Relatório de Conteúdo (CSV + PDF)")
        self._habilitar_documentos(False)
        self.botao_relatorio.setToolTip(
            "Converte SMS, chamadas e agenda em um CSV por artefato (abre no Excel) "
            "e um PDF consolidado, fora da aquisição selada."
        )
        self.botao_relatorio.clicked.connect(self._gerar_relatorio_conteudo)


        self.botao_relatorio_extracao = QPushButton("📑 Relatório de Extração (PDF)")
        self.botao_relatorio_extracao.setEnabled(False)
        self.botao_relatorio_extracao.setToolTip(
            "Emite o relatório técnico da aquisição: ambiente, método, desfecho por "
            "módulo, arquivos por categoria, inventário e selo."
        )
        self.botao_relatorio_extracao.clicked.connect(self._gerar_relatorio_de_extracao)

        self.botao_laudo_pericial = QPushButton("⚖ Laudo Pericial (PDF)")
        self.botao_laudo_pericial.setEnabled(False)
        self.botao_laudo_pericial.setToolTip(
            "Emite o laudo do dispositivo: material examinado, metodologia, limitações, "
            "resultados, integridade e conclusão, com as declarações do examinador."
        )
        self.botao_laudo_pericial.clicked.connect(self._gerar_laudo_pericial)

        self.botao_conversas = QPushButton("💬 PDF de conversas selecionadas")
        self.botao_conversas.setEnabled(False)
        self.botao_conversas.setToolTip(
            "Escolha as conversas relevantes (WhatsApp, SMS, MMS) e gere o PDF delas, "
            "completas. A íntegra de todas fica na planilha e no caderno HTML."
        )
        self.botao_conversas.clicked.connect(self._pdf_de_conversas)

        self.botao_decifrar = QPushButton("🔑 Decifrar backup")
        self.botao_decifrar.setEnabled(False)
        self.botao_decifrar.setToolTip(
            "Android: decifra o backup do WhatsApp (.crypt15) com a chave de 64 dígitos. "
            "iPhone: decifra o backup cifrado com a senha de backup. O material em claro "
            "fica fora da aquisição selada."
        )
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
        grade.addWidget(self.botao_laudo_pericial, 2, 0, 1, 3)
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
        for nome in ("botao_relatorio_extracao", "botao_laudo_pericial", "botao_decifrar",
                     "botao_conversas"):
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
                self, "Documento não gerado",
                f"Não foi possível gerar o documento:\n{documento.erro}",
            )
            return
        self._carregar_documentos()
        abrir_pdf(documento.caminho, self)

    def _pdf_de_conversas(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, "Aviso", "Selecione uma aquisição na lista.")
            return
        ConversasDialog(pasta_aquisicao, parent=self).exec()

    def _decifrar_whatsapp(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, "Aviso", "Selecione uma aquisição na lista.")
            return
        if e_aquisicao_ios(pasta_aquisicao):
            # No iPhone o que se decifra é o backup inteiro, com a senha de
            # backup que o dono definiu (não o código de desbloqueio).
            gerada = senha_gerada_na_aquisicao(pasta_aquisicao)
            if gerada:
                # O módulo de backup cifrado gerou a senha e a guardou sob o
                # selo: o examinador só confirma, sem copiar do log.
                senha, confirmado = QInputDialog.getText(
                    self, "Senha do backup do iPhone",
                    "Senha temporária gerada pela suíte nesta aquisição (guardada em "
                    "backup_ios_cifrado/senha_do_backup.txt e conferida com o lacre). Confirme para "
                    "decifrar:",
                    QLineEdit.Normal, gerada,
                )
            else:
                senha, confirmado = QInputDialog.getText(
                    self, "Senha do backup do iPhone",
                    "Senha de backup definida no iPhone (não é o código de desbloqueio). "
                    "Ela constará do registro da decifragem, para que possa ser repetida:",
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
            QMessageBox.warning(self, "Nada foi decifrado", resultado.erro)
            return
        QMessageBox.information(
            self,
            "Backup decifrado",
            f"{resultado.resumo}\n\nGravado em:\n{resultado.pasta}\n\n"
            "A aquisição selada não foi alterada.\n\nEm seguida será gerado o Relatório de "
            "Conteúdo, que é onde as mensagens aparecem. Um Laudo emitido antes desta "
            "decifragem não as traz: emita-o de novo.",
        )
        # Decifrar não mostra mensagem nenhuma por si: quem as mostra é o
        # relatório de conteúdo. Sem gerá-lo aqui, o examinador decifra e
        # fica procurando onde as conversas foram parar.
        self._gerar_relatorio_conteudo()

    def _gerar_relatorio_de_extracao(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, "Aviso", "Selecione uma aquisição na lista.")
            return
        self.setCursor(Qt.WaitCursor)
        try:
            documento = relatorio_extracao_service.gerar(pasta_aquisicao)
        finally:
            self.unsetCursor()
        self._informar_documento("Relatório de Extração gerado", documento)

    def _gerar_laudo_pericial(self) -> None:
        pasta_aquisicao = self._aquisicao_selecionada()
        if pasta_aquisicao is None:
            QMessageBox.warning(self, "Aviso", "Selecione uma aquisição na lista.")
            return

        # Quem subscreve é o examinador da sessão, confirmado a cada laudo:
        # pode não ser quem fez a extração, e o laudo mostra os dois.
        resposta = QMessageBox.question(
            self, "Examinador que subscreve",
            f"Este laudo será subscrito por {sessao_service.nome()}.\n\n"
            "Se não é você, feche esta janela e use 'Trocar examinador', no rodapé da "
            "barra lateral.",
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
                    self, "Atenção",
                    "O laudo foi gerado, mas as respostas aos protocolos NÃO puderam "
                    f"ser juntadas ao caso ({erro}). Elas existem apenas dentro do laudo.",
                )
        self._informar_documento("Laudo Pericial gerado", documento)

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
            self.texto_ficha.setText("Nenhum caso encontrado na pasta de extrações.")

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
        partes.append(f"{quantas} aquisições" if quantas != 1 else "1 aquisição")
        if resumo.lacres:
            partes.append("lacre " + ", ".join(resumo.lacres))
        if resumo.examinadores:
            rotulo = "examinador" if len(resumo.examinadores) == 1 else "examinadores"
            partes.append(f"{rotulo}: " + ", ".join(resumo.examinadores))
        if resumo.ultima_atividade:
            partes.append(resumo.ultima_atividade.strftime("%d/%m/%Y"))
        if resumo.metadados_divergentes:
            partes.append("⚠ metadados divergentes")
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
            self.texto_ficha.setText(f"Erro ao ler informações do caso: {erro}")
            return

        self.texto_ficha.setHtml(self._montar_ficha(resumo))

        for aquisicao in resumo.aquisicoes:
            selo = "🔒 selada" if aquisicao.selada else "aberta"
            item = QListWidgetItem(
                f"{aquisicao.rotulo}  ·  examinador: {aquisicao.examinador or 'não registrado'}"
                f"  ·  {selo}"
            )
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
            self.texto_detalhes.setText(
                "Este caso ainda não tem nenhuma aquisição gravada."
            )
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
            valor = escapar(valor) if valor else "<i>não informado</i>"
            return f"<tr><td><b>{escapar(rotulo)}</b></td><td>{valor}</td></tr>"

        partes = [f"<h3>{escapar(resumo.identificador)}</h3>"]

        if resumo.metadados_divergentes:
            # Num caso antigo os dados do caso vivem dentro de cada
            # aquisicao. Quando elas discordam, escolher uma versao em
            # silencio seria a ferramenta afirmando o que nao verificou.
            campos = ", ".join(resumo.campos_divergentes)
            partes.append(
                "<p style='color:#c62828;'><b>⚠ Dados do caso divergentes entre as "
                f"aquisições:</b> {escapar(campos)}.<br>"
                "A ficha mostra a versão da aquisição mais recente. Use "
                "'Retificar Dados do Caso' para criar o registro único do caso.</p>"
            )

        if not resumo.tem_registro:
            partes.append(
                "<p><i>Caso anterior ao registro único: os dados abaixo foram lidos "
                "de dentro das aquisições.</i></p>"
            )

        partes.append("<table cellpadding='3'>")
        for campo, valor in resumo.dados_do_caso.items():
            partes.append(linha(campo, valor))
        partes.append("</table>")

        if resumo.lacres:
            partes.append(f"<p><b>Lacres:</b> {escapar(', '.join(resumo.lacres))}</p>")
        if resumo.examinadores:
            partes.append(
                f"<p><b>Examinador(es):</b> {escapar(', '.join(resumo.examinadores))}</p>"
            )

        partes.append(f"<p><b>Aquisições:</b> {len(resumo.aquisicoes)}</p>")
        self._dados_do_caso_na_ficha = dict(resumo.dados_do_caso)

        if resumo.documentos:
            partes.append("<p><b>Autorização anexada:</b></p><ul>")
            for documento in resumo.documentos:
                partes.append(
                    f"<li>{escapar(documento.get('rotulo') or documento.get('tipo', ''))}"
                    f" — {escapar(documento.get('nome', ''))}</li>"
                )
            partes.append("</ul>")
        else:
            partes.append(
                "<p><b>Autorização:</b> <i>nenhum documento anexado a este caso.</i></p>"
            )

        if resumo.complementos:
            partes.append(
                f"<p><b>Complementos juntados:</b> {resumo.complementos}</p>"
            )

        partes.append(f"<p style='color:gray;'>Pasta: {escapar(str(resumo.pasta))}</p>")
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
            texto_completo = f"{conteudo_custodia}\n\nCaminho dos arquivos:\n{caminho_pasta}"
            self.texto_detalhes.setText(texto_completo)
            self._habilitar_documentos(True)
        else:
            self.texto_detalhes.setText(f"Diretório: {caminho_pasta}")
            self._habilitar_documentos(False)

    def _excluir_caso(self) -> None:
        linha = self.lista_projetos.currentRow()
        if linha < 0:
            return
        pasta_caso: Path = self.lista_projetos.item(linha).data(Qt.UserRole)
        confirmacao, confirmado = QInputDialog.getText(
            self, "Excluir caso",
            f"O caso {pasta_caso.name} inteiro — aquisições, documentos, relatórios e "
            "complementos — será enviado à Lixeira do Windows. Dá para restaurá-lo de lá; "
            "apagar de vez é esvaziar a Lixeira.\n\n"
            f"Para confirmar, digite o nome do caso ({pasta_caso.name}):",
        )
        if not confirmado:
            return
        try:
            excluir_caso(pasta_caso, confirmacao, casos=self.case_service)
        except ErroDeExclusao as erro:
            QMessageBox.warning(self, "Caso não excluído", str(erro))
            return
        QMessageBox.information(
            self, "Caso excluído",
            f"O caso {pasta_caso.name} foi enviado à Lixeira do Windows e a exclusão foi "
            "registrada.")
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
            f"{len(documentos)} documento(s) desta aquisição — clique duas vezes para abrir."
            if documentos else
            "Nenhum documento gerado ainda para esta aquisição. Use os botões abaixo."
        )
        self.abas.setTabText(1, f"Documentos ({len(documentos)})")
        if documentos:
            self.lista_documentos.setCurrentRow(0)

    def _documento_escolhido(self):
        item = self.lista_documentos.currentItem()
        if item is None:
            QMessageBox.information(self, "Documentos", "Escolha um documento na lista.")
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
            QMessageBox.information(self, "Exportar", "Selecione um ou mais documentos na lista.")
            return
        EntregaDialog(pasta_aquisicao, documentos=escolhidos, parent=self).exec()

    def _copiar_documento(self) -> None:
        caminho = self._documento_escolhido()
        if caminho is None:
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, "Salvar cópia do documento", str(Path.home() / caminho.name),
            "Documento PDF (*.pdf)",
        )
        if not destino:
            return
        try:
            resumo = salvar_copia(caminho, Path(destino))
        except OSError as erro:
            QMessageBox.critical(self, "Cópia não salva", str(erro))
            return
        QMessageBox.information(
            self, "Cópia salva",
            f"Cópia salva em:\n{destino}\n\nConferida pelo SHA-256, idêntica ao original:\n{resumo}",
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
            QMessageBox.warning(self, "Aviso", "Selecione um caso na lista.")
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
            QMessageBox.critical(self, "Erro", f"Não foi possível gravar: {erro}")
            return
        if alterado:
            QMessageBox.information(
                self,
                "Dados do caso retificados",
                "O registro do caso foi atualizado e a alteração ficou registrada "
                "como complemento, com os valores anteriores.\n\n"
                "As aquisições já seladas não foram tocadas.",
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
                QMessageBox.information(self, "Sucesso", "Dados atualizados com sucesso.")
                return True
            except OSError as erro:
                QMessageBox.critical(self, "Erro", f"Não foi possível salvar: {erro}")
                return False

        resposta = QMessageBox.question(
            self,
            "Esta aquisição já está selada",
            "Esta coleta já tem manifesto de integridade.\n\n"
            "Reescrevê-la faria o caso divergir do próprio selo e apagaria o registro do "
            "que existia no momento do exame.\n\n"
            "A alteração pode ser juntada como COMPLEMENTO ao caso: o material coletado "
            "permanece intocado, e a retificação fica registrada com data própria.\n\n"
            "Deseja juntar como complemento?",
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
            QMessageBox.warning(self, "Aviso", "Selecione um caso na lista.")
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
                    "Erro",
                    f"Não foi possível anexar {Path(documento['arquivo']).name}:\n{erro}",
                )
                continue
            anexados.append(caminho.name)

        if not anexados:
            return

        QMessageBox.information(
            self,
            "Autorização anexada",
            "Anexado ao caso:\n  " + "\n  ".join(anexados) + "\n\n"
            "O caso foi reselado e a juntada ficou registrada como complemento, "
            "com o hash de cada documento.\n\n"
            "As aquisições anteriores NÃO foram alteradas e não passam a contar "
            "com este documento: cada uma registra o que estava à vista no momento "
            "em que foi feita.",
        )
        self._ao_selecionar_projeto(linha)

    def _registrar_complemento(self, pasta_caso: Path, titulo: str, texto: str) -> bool:
        try:
            caminho = self.case_service.juntar_complemento(pasta_caso, titulo, texto)
        except OSError as erro:
            QMessageBox.critical(self, "Erro", f"Não foi possível juntar o complemento: {erro}")
            return False

        QMessageBox.information(
            self,
            "Complemento juntado",
            f"Complemento gravado em:\n{caminho.name}\n\n"
            "As aquisições já seladas não foram alteradas, e o caso foi reselado — "
            "o manifesto anterior está preservado.",
        )
        return True

    def _editar_dispositivo_selecionado(self) -> None:
        linha_atual = self.lista_dispositivos.currentRow()
        if linha_atual < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um dispositivo na lista para retificar.")
            return

        item = self.lista_dispositivos.item(linha_atual)
        arq_custodia: Path = item.data(Qt.UserRole + 2)
        if not arq_custodia or not arq_custodia.is_file():
            return

        dados_atuais = ler_cadeia_custodia(arq_custodia)

        dialogo_disp = DeviceInfoDialog(parent=self, modo_edicao=True)
        dialogo_disp.setWindowTitle("Retificar Dados do Dispositivo")

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
            QMessageBox.warning(self, "Aviso", "Selecione um dispositivo na lista.")
            return

        arq_custodia = self.lista_dispositivos.item(linha).data(Qt.UserRole + 2)
        if arq_custodia is None:
            QMessageBox.warning(
                self, "Aviso", "Selecione uma aquisição específica para gerar o relatório."
            )
            return

        pasta_aquisicao = Path(arq_custodia).parent

        # O fuso é escolhido, nunca suposto: converter epoch para hora local
        # é interpretação, e o aparelho pode estar em fuso diferente do da
        # estação. O que for escolhido fica declarado no relatório.
        local = datetime.now().astimezone().tzinfo
        rotulo_local = f"Fuso desta estação ({datetime.now().astimezone().strftime('%Z%z')})"
        opcoes = [rotulo_local, "UTC — sem conversão"]
        escolha, confirmado = QInputDialog.getItem(
            self,
            "Fuso horário das datas",
            "As datas do aparelho estão em formato numérico e precisam ser "
            "convertidas. O fuso escolhido será declarado no relatório.\n\n"
            "O relógio do próprio aparelho, aferido na coleta, está no "
            "registro_procedimento.txt da aquisição — confira-o se houver dúvida.",
            opcoes,
            0,
            False,
        )
        if not confirmado:
            return

        fuso = local if escolha == rotulo_local else None
        resultado = RelatorioService.gerar(pasta_aquisicao, fuso=fuso)

        if resultado.erro:
            QMessageBox.warning(self, "Nada a relatar", resultado.erro)
            return

        partes = [
            f"Relatório gravado em:\n{resultado.pasta}",
            "\n".join(resultado.resumo_por_artefato),
        ]
        if not resultado.total_registros:
            # Sem esta linha, o examinador sai procurando planilha que não
            # existe — foi o que aconteceu na primeira execução real.
            partes.append(
                "NENHUMA PLANILHA CSV FOI GERADA, porque não houve registro a "
                "apresentar. Os motivos estão acima e em PROCEDENCIA.txt."
            )
        if resultado.total_descartes:
            partes.append(
                f"ATENÇÃO: {resultado.total_descartes} trecho(s) do material bruto NÃO "
                "puderam ser interpretados e não constam do relatório. Ele está "
                "incompleto em relação à evidência — ver NAO_INTERPRETADO.txt."
            )
        if resultado.origens_divergentes:
            partes.append(
                "ATENÇÃO: o material de origem não confere mais com o selo da coleta: "
                + ", ".join(resultado.origens_divergentes)
            )
        partes += [
            "",
            "A aquisição não foi alterada: o relatório é documento derivado e "
            "fica fora do que foi selado.",
        ]

        mensagem = "\n\n".join(partes)
        com_ressalva = (
            resultado.total_descartes
            or resultado.origens_divergentes
            or not resultado.total_registros
        )
        if com_ressalva:
            QMessageBox.warning(self, "Relatório gerado com ressalvas", mensagem)
        else:
            QMessageBox.information(self, "Relatório de conteúdo gerado", mensagem)

        # Abre o PDF: o relatório existe para ser lido, e dizer só em que
        # pasta ele ficou obrigava a ir buscá-lo.
        pdf = next((arquivo for arquivo in resultado.arquivos_gerados
                    if str(arquivo).lower().endswith(".pdf")), None)
        self._carregar_documentos()
        if pdf is not None:
            abrir_pdf(pdf, self)
