"""
Janela principal da suíte HexisForensics.
Navegação por menu lateral e orquestração de fluxo de extração com cadeia de custódia.
"""

from __future__ import annotations

import time
from pathlib import Path
from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from services.branding_service import PASTA_EXTRACOES, BrandConfig
from services.case_service import CaseService
from services.device_service import ANDROID, COMPUTADOR, IOS, DeviceService
from services import sessao_service
from services.exame_service import criar_registro
from services.extraction_service import identificacao_da_ferramenta as sessao_da_ferramenta
from services.extraction_service import (
    ExtractionService,
    descrever_metodo,
    listar_extratores,
)

from .widgets.case_dialog import CaseDialog
from .widgets.cases_manager_dialog import CasesManagerDialog
from .widgets.device_info_dialog import DeviceInfoDialog
from .widgets.fundamento_dialog import AutorizacaoDialog
from .widgets.examinadores_dialog import ExaminadoresDialog
from .widgets.exame_sem_extracao_dialog import ExameSemExtracaoDialog
from .widgets.tela_entrada import TelaEntrada
from .widgets.termos_dialog import TermosDialog
from .widgets.device_panel import DevicePanel
from .widgets.disk_panel import DiskPanel
from .widgets.extraction_panel import ExtractionPanel
from .widgets.hash_dialog import HashDialog
from .widgets.log_console import LogConsole
from .widgets.metodo_dialog import MetodoDialog
from .widgets.sidebar import Sidebar
from ui.widgets.ajuste_de_tela import caber_na_tela

# `PASTA_EXTRACOES` vem de services (que a obtém de core.instalacao):
# calculada por `__file__`, num executável as extrações iriam para a pasta
# interna do empacotador; e numa cópia instalada elas não ficam ao lado do
# programa.

# Sem uso por este tempo, a sessão é bloqueada (a extração em andamento segue).
MINUTOS_ATE_BLOQUEAR = 15

EVENTOS_DE_USO = (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel, QEvent.MouseMove)


class _VigiaDeUso(QObject):
    """Anota o último uso do teclado e do mouse em qualquer janela da suíte."""

    def __init__(self):
        super().__init__()
        self.ultimo_uso = time.monotonic()

    def eventFilter(self, objeto, evento):
        if evento.type() in EVENTOS_DE_USO:
            self.ultimo_uso = time.monotonic()
        return False


TITULOS_SECAO = {
    "android": ("Extração", "Início › Extração › Android"),
    "iphone": ("Extração", "Início › Extração › iPhone"),
    "computador": ("Extração", "Início › Extração › Armazenamento"),
}


class PlataformaPage(QWidget):
    """
    Página de uma plataforma: painel superior (status do dispositivo ou,
    no caso do Computador, seletor de unidade de disco) + lista de tipos
    de extração.

    O painel superior é injetado via `painel_superior` em vez de sempre
    construir um `DevicePanel`, porque Computador usa um widget totalmente
    diferente (`DiskPanel` — seleção de unidade, não "conectado/não
    conectado"). Quando omitido, mantém o comportamento original
    (Android/iOS): constrói um `DevicePanel` internamente.
    """

    def __init__(
        self,
        nome_plataforma: str,
        extratores,
        painel_superior: QWidget | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.nome_plataforma = nome_plataforma
        layout = QVBoxLayout(self)
        self.painel_superior = painel_superior or DevicePanel(
            f"Status do Dispositivo — {nome_plataforma}"
        )
        self.painel_extracao = ExtractionPanel(
            extratores, f"Tipos de Extração — {nome_plataforma}"
        )
        layout.addWidget(self.painel_superior)
        layout.addWidget(self.painel_extracao, stretch=1)

    @property
    def painel_dispositivo(self) -> QWidget:
        """Alias de compatibilidade: código existente (Android/iOS) referencia `painel_dispositivo`."""
        return self.painel_superior


class MainWindow(QMainWindow):
    """
    Classe principal da janela da aplicação HexisForensics.
    """

    def __init__(self, marca: BrandConfig):
        super().__init__()
        self.marca = marca
        self.setWindowTitle(f"{marca.nome_exibicao} — Suíte de Extração Forense")
        caber_na_tela(self, 1200, 800)
        PASTA_EXTRACOES.mkdir(parents=True, exist_ok=True)
        self.device_service = DeviceService()
        self.case_service = CaseService(PASTA_EXTRACOES)
        self._servico_extracao: ExtractionService | None = None
        self._aba_execucao_atual: PlataformaPage | None = None
        self._pagina_atual = "android"
        self._sair_sem_perguntar = False
        self._bloqueada = False
        self._montar_ui()
        self._navegar("android")
        self._atualizar_sessao()

        self._vigia = _VigiaDeUso()
        QApplication.instance().installEventFilter(self._vigia)
        self._relogio_de_bloqueio = QTimer(self)
        self._relogio_de_bloqueio.timeout.connect(self._conferir_inatividade)
        self._relogio_de_bloqueio.start(30_000)

    def _montar_ui(self) -> None:
        self.sidebar = Sidebar(self.marca)
        self.sidebar.item_selecionado.connect(self._ao_selecionar_item)
        self.aba_android = PlataformaPage(ANDROID, listar_extratores(ANDROID))
        self.aba_iphone = PlataformaPage(IOS, listar_extratores(IOS))
        self.painel_disco = DiskPanel()
        self.aba_computador = PlataformaPage(
            COMPUTADOR, listar_extratores(COMPUTADOR), painel_superior=self.painel_disco
        )
        self._paginas_por_chave = {
            "android": self.aba_android,
            "iphone": self.aba_iphone,
            "computador": self.aba_computador,
        }
        self.paginas = QStackedWidget()
        for pagina in self._paginas_por_chave.values():
            self.paginas.addWidget(pagina)
        self.aba_android.painel_dispositivo.verificar_solicitado.connect(
            lambda: self._verificar_dispositivo(self.aba_android)
        )
        self.aba_iphone.painel_dispositivo.verificar_solicitado.connect(
            lambda: self._verificar_dispositivo(self.aba_iphone)
        )
        self.painel_disco.atualizar_solicitado.connect(
            self._atualizar_unidades_computador
        )

        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        layout_conteudo.setContentsMargins(18, 20, 18, 12)
        layout_conteudo.addWidget(self._montar_cabecalho_conteudo())

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.paginas)
        splitter.addWidget(self._montar_painel_execucao())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout_conteudo.addWidget(splitter, stretch=1)

        central = QWidget()
        layout_central = QHBoxLayout(central)
        layout_central.setContentsMargins(0, 0, 0, 0)
        layout_central.setSpacing(0)
        layout_central.addWidget(self.sidebar)
        layout_central.addWidget(conteudo, stretch=1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Pronto.")
        self.label_examinador = QLabel(sessao_service.resumo())
        self.statusBar().addPermanentWidget(self.label_examinador)
        self._atualizar_unidades_computador()

    def _montar_cabecalho_conteudo(self) -> QWidget:
        cabecalho = QWidget()
        layout = QVBoxLayout(cabecalho)
        layout.setContentsMargins(0, 0, 0, 8)
        self.label_titulo_secao = QLabel()
        self.label_titulo_secao.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.label_breadcrumb = QLabel()
        self.label_breadcrumb.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.label_titulo_secao)
        layout.addWidget(self.label_breadcrumb)
        return cabecalho

    def _montar_painel_execucao(self) -> QWidget:
        painel_execucao = QWidget()
        layout_execucao = QVBoxLayout(painel_execucao)
        linha_botoes = QHBoxLayout()
        self.botao_iniciar = QPushButton("▶ Iniciar Extração")
        self.botao_iniciar.clicked.connect(self._iniciar_extracao)
        self.botao_cancelar = QPushButton("■ Cancelar")
        self.botao_cancelar.setEnabled(False)
        self.botao_cancelar.clicked.connect(self._cancelar_extracao)
        # Aparelho bloqueado, que não liga, quebrado: o exame existe mesmo
        # sem extração, e o laudo negativo precisa da mesma cadeia de custódia.
        self.botao_sem_extracao = QPushButton("📝 Exame sem extração")
        self.botao_sem_extracao.setToolTip(
            "Para aparelho bloqueado por credencial, que não liga ou está danificado: "
            "registra a peça, o estado e a tentativa de conexão, e permite emitir o laudo "
            "negativo. Nenhum dado do conteúdo é obtido."
        )
        self.botao_sem_extracao.clicked.connect(
            lambda: self._iniciar_extracao(sem_extracao=True)
        )
        linha_botoes.addWidget(self.botao_iniciar)
        linha_botoes.addWidget(self.botao_cancelar)
        linha_botoes.addWidget(self.botao_sem_extracao)
        linha_botoes.addStretch()
        self.barra_progresso = QProgressBar()
        self.console_log = LogConsole()
        layout_execucao.addLayout(linha_botoes)
        layout_execucao.addWidget(self.barra_progresso)
        layout_execucao.addWidget(QLabel("Console de Execução:"))
        layout_execucao.addWidget(self.console_log)
        return painel_execucao

    def _abrir_registro_procedimento(
        self,
        pasta_caso,
        identificador_caso,
        nome_plataforma,
        id_dispositivo,
        serial_android,
        documentos_autorizacao=None,
        sem_extracao: bool = False,
    ) -> None:
        """
        Abre o `registro_procedimento.txt` do caso: ambiente da estação,
        aferição de relógio, alterações provocadas no aparelho e decisões
        metodológicas — os quatro registros que a ISO/IEC 27037 exige e que
        nenhum log técnico cobre.
        """
        self.case_service.abrir_registro_procedimento(
            pasta_caso, identificador_caso, nome_plataforma, id_dispositivo
        )

        # Quem executa vem logo depois do cabeçalho: o que o examinador
        # declara no perfil. A conta da estação entra ao lado, porque essa
        # a ferramenta apura sozinha.
        resumo_operador = self.case_service.registrar_operador(
            pasta_caso, sessao_service.perfil_para_a_aquisicao()
        )
        self.console_log.adicionar_linha(f"[*] Operador: {resumo_operador}", com_timestamp=True)

        # A autorização é a primeira entrada substantiva do diário: é a
        # primeira coisa que se questiona sobre uma extração. Roda mesmo sem
        # documento nenhum — nesse caso o registro declara a ausência, que é
        # justamente o que não pode passar em silêncio.
        try:
            resumo = self.case_service.registrar_autorizacao(
                pasta_caso, documentos_autorizacao or []
            )
            self.console_log.adicionar_linha(f"[*] Autorização: {resumo}", com_timestamp=True)
        except (ValueError, OSError) as exc:
            self.console_log.adicionar_linha(
                f"[ERRO] Não foi possível registrar a autorização: {exc}", com_timestamp=True
            )

        e_android = nome_plataforma == ANDROID
        self.case_service.registrar_ambiente(
            self.device_service.obter_versao_adb() if e_android else None
        )
        # Sem extração não houve depuração autorizada nem relógio lido do
        # aparelho: registrar isso seria afirmar o que não aconteceu.
        if not e_android or sem_extracao:
            return

        resumo_relogio, alerta_relogio = self.device_service.obter_relogio_android()
        self.case_service.registrar_relogio(resumo_relogio)
        self.console_log.adicionar_linha(f"[*] {resumo_relogio}", com_timestamp=True)
        if alerta_relogio:
            self.console_log.adicionar_linha(f"[ATENÇÃO] {alerta_relogio}", com_timestamp=True)

        self.case_service.registrar_alteracao(
            "Depuração USB ativada no aparelho e chave RSA desta estação autorizada.",
            "Imposição do protocolo ADB: sem essa autorização não existe via de aquisição "
            "lógica em aparelho sem root. A alteração se restringe a configuração do "
            "sistema, sem escrita em área de dados do usuário.",
        )

        if serial_android:
            self.case_service.registrar_decisao(
                f"Todos os comandos ADB vinculados ao serial '{serial_android}'.",
                "Garante que nenhum comando atinja outro dispositivo eventualmente conectado "
                "à estação durante o procedimento.",
            )

    def _iniciar_extracao(self, sem_extracao: bool = False) -> None:
        if self._servico_extracao is not None and self._servico_extracao.isRunning():
            QMessageBox.warning(self, "Aviso", "Já existe uma extração em andamento.")
            return

        aba = self._aba_atual()
        if sem_extracao and aba.nome_plataforma == COMPUTADOR:
            QMessageBox.information(
                self, "Exame sem extração",
                "O exame sem extração é para aparelho celular (Android ou iPhone).",
            )
            return
        classes_selecionadas = (
            [] if sem_extracao else aba.painel_extracao.extratores_selecionados()
        )
        if not classes_selecionadas and not sem_extracao:
            QMessageBox.warning(
                self, "Aviso", "Selecione ao menos um tipo de extração."
            )
            return

        # Computador não tem "o dispositivo conectado" — o examinador
        # precisa ter escolhido uma unidade de disco no DiskPanel antes de
        # prosseguir (checado aqui, antes dos diálogos de caso/dispositivo,
        # para não fazer o examinador preencher tudo e só então descobrir
        # que faltou selecionar a unidade).
        caminho_unidade_computador: str | None = None
        if aba.nome_plataforma == COMPUTADOR:
            caminho_unidade_computador = self.painel_disco.unidade_selecionada()
            if not caminho_unidade_computador:
                QMessageBox.warning(
                    self, "Aviso", "Selecione uma unidade de disco antes de iniciar."
                )
                return

        self._aba_execucao_atual = aba
        aba.painel_extracao.resetar_status()

        # Passo 0: QUEM executa — o examinador da sessão, confirmado. Custa um
        # clique e evita extração no nome de quem esqueceu de trocar.
        if not self._confirmar_examinador(
            "Confirmar examinador",
            ("Este exame sem extração será registrado como feito por " if sem_extracao
             else "Esta extração será registrada como feita por ")
            + f"<b>{sessao_service.nome()}</b>.<br>Se não é você, troque de examinador antes."
            + ("<br><br><b style='color:#ff6b6b'>MODO DE TESTE:</b> a aquisição e todos os "
               "documentos dela sairão marcados como TESTE, sem valor pericial."
               if sessao_service.e_forensic_admin() else ""),
        ):
            return

        # Passo 1: método e limitações dos módulos escolhidos.
        # Vem antes de tudo porque é o único momento em que a informação
        # ainda serve para DECIDIR — depois da coleta ela vira registro.
        if not sem_extracao:
            dialogo_metodo = MetodoDialog(descrever_metodo(classes_selecionadas), parent=self)
            if dialogo_metodo.exec() != QDialog.Accepted:
                return

        # Passo 2: o caso
        dialogo_caso = CaseDialog(self.case_service, aba.nome_plataforma, parent=self)
        if dialogo_caso.exec() != QDialog.Accepted:
            return

        identificador_caso = dialogo_caso.identificador_caso()
        dados_metadados = dialogo_caso.dados_metadados()

        # Passo 3: autorização de acesso aos dados.
        # Vem antes de qualquer coisa ser criada em disco: o examinador
        # escolhe o que anexar, e nada é copiado enquanto a aquisição não
        # for efetivamente aberta.
        dialogo_autorizacao = AutorizacaoDialog(
            self.case_service.documentos_do_caso(identificador_caso), parent=self
        )
        if dialogo_autorizacao.exec() != QDialog.Accepted:
            return

        documentos_autorizacao = dialogo_autorizacao.documentos()

        # Passo 4: a peça — descrição, lacre e fotografias
        dialogo_dispositivo = DeviceInfoDialog(parent=self)
        if dialogo_dispositivo.exec() != QDialog.Accepted:
            return
        dados_dispositivo = dialogo_dispositivo.dados_dispositivo()

        # Passo 5 (só no exame sem extração): estado do aparelho e tentativas.
        dados_do_exame = None
        if sem_extracao:
            dialogo_exame = ExameSemExtracaoDialog(parent=self)
            if dialogo_exame.exec() != QDialog.Accepted:
                return
            dados_do_exame = dialogo_exame.dados()

        if caminho_unidade_computador:
            id_dispositivo = self.device_service.obter_id_unidade_computador(
                caminho_unidade_computador
            )
        else:
            id_dispositivo = self.device_service.obter_id_dispositivo(
                aba.nome_plataforma
            )

        extratores = [classe() for classe in classes_selecionadas]
        if sem_extracao:
            extratores = [criar_registro(aba.nome_plataforma, dados_do_exame)]
        if caminho_unidade_computador:
            # Só extratores de Computador têm `definir_unidade` — `getattr`
            # em vez de importar `ComputadorExtractor` de `core`, para não
            # violar a regra "ui/ não importa core.*" (ver services/__init__.py).
            for extrator in extratores:
                definir_unidade = getattr(extrator, "definir_unidade", None)
                if definir_unidade is not None:
                    definir_unidade(caminho_unidade_computador)

        # Android: vincula todos os extratores ao serial do aparelho do caso.
        # Sem isso, um segundo aparelho conectado no meio do procedimento
        # poderia receber comandos e contaminar o caso. Mesmo padrão de
        # `definir_unidade`: `getattr` para não violar "ui/ não importa core".
        serial_android = None
        self._plataforma_do_caso = aba.nome_plataforma
        self._serial_do_caso = None
        if sem_extracao:
            # Nada a vincular: o registro só lista o que responde, sem comando
            # dirigido a aparelho algum.
            pass
        elif aba.nome_plataforma == IOS:
            # Mesmo vínculo, pelo UDID: nenhuma operação alcança outro iPhone.
            udid = self.device_service.obter_udid_ios()
            if not udid:
                QMessageBox.warning(
                    self, "iPhone não autorizado",
                    "Nenhum iPhone conectado que confie nesta estação. Conecte o cabo, "
                    "desbloqueie a tela, toque em 'Confiar' e clique em 'Verificar'.",
                )
                return
            self._serial_do_caso = udid
            for extrator in extratores:
                definir_udid = getattr(extrator, "definir_udid", None)
                if definir_udid is not None:
                    definir_udid(udid)
        elif aba.nome_plataforma == ANDROID:
            serial_android = self.device_service.obter_serial_android()
            self._serial_do_caso = serial_android
            for extrator in extratores:
                definir_serial = getattr(extrator, "definir_serial", None)
                if definir_serial is not None:
                    definir_serial(serial_android)

        pasta_caso = self.case_service.abrir_caso(
            aba.nome_plataforma, identificador_caso, id_dispositivo
        )

        # Caso novo: o registro do caso nasce aqui, uma vez. Caso existente:
        # nada é perguntado de novo — a aquisição herda o que já está gravado.
        try:
            if dados_metadados.get("tipo") == "novo":
                self.case_service.gravar_dados_do_caso(identificador_caso, dados_metadados)
            self.case_service.gravar_cadeia_custodia(
                pasta_caso, identificador_caso, dados_dispositivo
            )
        except OSError as erro:
            self.console_log.adicionar_linha(
                f"[!] Erro ao salvar cadeia de custódia: {erro}", com_timestamp=True
            )
        self._abrir_registro_procedimento(
            pasta_caso,
            identificador_caso,
            aba.nome_plataforma,
            id_dispositivo,
            serial_android,
            documentos_autorizacao,
            sem_extracao=sem_extracao,
        )
        if aba.nome_plataforma == IOS and not sem_extracao:
            self.case_service.registrar_decisao(
                f"Todas as operações vinculadas ao UDID '{self._serial_do_caso}'.",
                "Garante que nenhuma operação atinja outro iPhone eventualmente conectado "
                "à estação durante o procedimento.",
            )
        self.console_log.adicionar_linha(
            f"[*] Pasta de destino: {pasta_caso}", com_timestamp=True
        )

        self.barra_progresso.setValue(0)
        self._servico_extracao = ExtractionService(
            extratores, pasta_caso, ao_finalizar=self._conferir_aparelho_ao_final
        )
        self._servico_extracao.log_emitido.connect(self.console_log.adicionar_linha)
        self._servico_extracao.progresso_emitido.connect(self.barra_progresso.setValue)
        self._servico_extracao.extrator_iniciado.connect(self._ao_iniciar_extrator)
        self._servico_extracao.extrator_concluido.connect(self._ao_concluir_extrator)
        self._servico_extracao.tudo_concluido.connect(self._ao_concluir_tudo)
        self._servico_extracao.start()

        self.botao_iniciar.setEnabled(False)
        self.botao_sem_extracao.setEnabled(False)
        self.botao_cancelar.setEnabled(True)

    def _ao_selecionar_item(self, chave: str) -> None:
        if chave in ("android", "iphone", "computador"):
            self._navegar(chave)
        elif chave == "hash":
            self._abrir_dialogo_hash()
        elif chave == "abrir_pasta":
            self._abrir_gerenciador_projetos()
        elif chave == "examinadores":
            dialogo = ExaminadoresDialog(parent=self)
            dialogo.exec()
            if dialogo.excluiu_o_proprio:
                # Sem sessão não se usa a suíte: volta a entrada, e fechá-la sai.
                self.hide()
                if TelaEntrada(self.marca).exec() != QDialog.Accepted:
                    self._sair_sem_perguntar = True
                    self.close()
                    return
                self.show()
            elif dialogo.pediu_cadastro:
                self._trocar_examinador(abrir_cadastro=True)
            self._atualizar_sessao()
        elif chave == "trocar_examinador":
            self._trocar_examinador()
        elif chave == "sobre":
            self._mostrar_sobre()
        elif chave == "sair":
            self.close()

    def _navegar(self, chave: str) -> None:
        self._pagina_atual = chave
        self.paginas.setCurrentWidget(self._paginas_por_chave[chave])
        self.botao_sem_extracao.setVisible(chave != "computador")
        titulo, breadcrumb = TITULOS_SECAO[chave]
        self.label_titulo_secao.setText(titulo)
        self.label_breadcrumb.setText(breadcrumb)
        self.sidebar.selecionar(chave)

    def _aba_atual(self) -> PlataformaPage:
        return self.paginas.currentWidget()

    def _atualizar_unidades_computador(self) -> None:
        """
        Consulta as unidades de disco detectadas e repovoa o `DiskPanel`.
        Chamado na montagem da janela e sempre que o examinador clica em
        'Atualizar Unidades' (ex.: depois de conectar um pendrive).
        """
        unidades = self.device_service.listar_unidades_computador()
        self.painel_disco.atualizar_lista(unidades)
        if unidades:
            self.console_log.adicionar_linha(
                f"[Computador] {len(unidades)} unidade(s) de disco detectada(s).",
                com_timestamp=True,
            )
        else:
            self.console_log.adicionar_linha(
                "[Computador] Nenhuma unidade detectada (fora do Windows, ou nenhum disco conectado).",
                com_timestamp=True,
            )

    def _verificar_dispositivo(self, aba: PlataformaPage) -> None:
        status = self.device_service.verificar_conexao(aba.nome_plataforma)
        aba.painel_dispositivo.atualizar_status(
            status.conectado, status.autorizado, status.mensagem
        )
        self.console_log.adicionar_linha(
            f"[{aba.nome_plataforma}] {status.mensagem}", com_timestamp=True
        )

    def _cancelar_extracao(self) -> None:
        if self._servico_extracao:
            self._servico_extracao.cancelar()

    def _ao_iniciar_extrator(self, id_e, nome) -> None:
        self.statusBar().showMessage(f"Executando: {nome}")
        self._aba_execucao_atual.painel_extracao.marcar_em_execucao(id_e)

    def _ao_concluir_extrator(self, id_e, nome, sucesso, msg, det) -> None:
        self._aba_execucao_atual.painel_extracao.marcar_concluido(
            id_e, sucesso, msg, det
        )

    def _ao_concluir_tudo(self) -> None:
        self.botao_iniciar.setEnabled(True)
        self.botao_sem_extracao.setEnabled(True)
        self.botao_cancelar.setEnabled(False)
        servico = self._servico_extracao
        self.statusBar().showMessage(
            servico.texto_da_barra_de_status() if servico else "Extração finalizada.")

    def _conferir_aparelho_ao_final(self):
        """
        Confirma que o aparelho do caso é o mesmo do início da aquisição.

        Um aparelho desconectado, trocado ou substituído durante o
        procedimento é evento de cadeia de custódia. O registro do caso
        precisa afirmar que o dispositivo examinado é o mesmo do começo ao
        fim — ou dizer, com todas as letras, que isso não pôde ser
        confirmado.

        Roda como **finalizador do serviço de extração**, e não depois que
        ele termina: escrever no caso após o manifesto ter sido gerado
        tornaria o próprio caso divergente do seu selo. Por isso não toca em
        nenhum widget — devolve a mensagem, e quem registra no log é o
        serviço, ainda dentro da janela em que escrever é permitido.
        """
        serial = getattr(self, "_serial_do_caso", None)
        if not serial:
            return None

        if getattr(self, "_plataforma_do_caso", None) == IOS:
            _confirmado, mensagem = self.device_service.conferir_iphone_do_caso(serial)
        else:
            _confirmado, mensagem = self.device_service.conferir_aparelho_do_caso(serial)
        self.case_service.registrar_decisao(
            "Conferência do aparelho no encerramento da aquisição.", mensagem
        )
        self._serial_do_caso = None
        return mensagem

    def _abrir_dialogo_hash(self) -> None:
        HashDialog(PASTA_EXTRACOES, parent=self).exec()

    def _abrir_gerenciador_projetos(self) -> None:
        CasesManagerDialog(PASTA_EXTRACOES, parent=self).exec()

    # ------------------------------------------------------------------
    # Sessão
    # ------------------------------------------------------------------
    def _atualizar_sessao(self) -> None:
        self.sidebar.atualizar_sessao(
            sessao_service.nome(), sessao_service.iniciais(), sessao_service.inicio())
        self.label_examinador.setText(sessao_service.resumo())

    def _extracao_em_andamento(self) -> bool:
        return self._servico_extracao is not None and self._servico_extracao.isRunning()

    def _confirmar_examinador(self, titulo: str, texto: str) -> bool:
        """Confirma quem assina o que vai começar; oferece a troca. `True` segue."""
        caixa = QMessageBox(self)
        caixa.setWindowTitle(titulo)
        caixa.setTextFormat(Qt.RichText)
        caixa.setText(texto)
        trocar = caixa.addButton("Trocar examinador", QMessageBox.ActionRole)
        confirmar = caixa.addButton("Confirmar", QMessageBox.AcceptRole)
        caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.setDefaultButton(confirmar)
        caixa.exec()
        if caixa.clickedButton() is trocar:
            self._trocar_examinador()
            return False
        return caixa.clickedButton() is confirmar

    def _trocar_examinador(self, abrir_cadastro: bool = False) -> None:
        if self._extracao_em_andamento():
            QMessageBox.information(
                self, "Extração em andamento",
                "Aguarde o fim da extração para trocar de examinador: ela está registrada "
                f"em nome de {sessao_service.nome()}.",
            )
            return
        self.hide()
        entrada = TelaEntrada(self.marca, texto_sair="←  Voltar à sessão atual",
                              abrir_cadastro=abrir_cadastro)
        if entrada.exec() == QDialog.Accepted:
            self._atualizar_sessao()
            self.console_log.adicionar_linha(
                f"[*] Sessão aberta por {sessao_service.nome()}.", com_timestamp=True)
        elif not sessao_service.ativa():
            # Quem entrou e recusou os termos encerrou a sessão: não há mais a
            # sessão anterior para onde voltar. Sem sessão não se usa a suíte.
            if TelaEntrada(self.marca).exec() != QDialog.Accepted:
                self._sair_sem_perguntar = True
                self.close()
                return
            self._atualizar_sessao()
        self.show()

    def _conferir_inatividade(self) -> None:
        parado = time.monotonic() - self._vigia.ultimo_uso
        if not self._bloqueada and parado >= MINUTOS_ATE_BLOQUEAR * 60:
            self._bloquear()

    def _bloquear(self) -> None:
        """
        Esconde a janela e pede a senha de novo. A extração em andamento
        continua rodando por trás.

        Fechar a tela de bloqueio PERGUNTA se é para sair da suíte. Antes
        saía direto, sem aviso, e para quem estava na frente o sistema
        simplesmente sumia. Com extração rodando, não se sai.
        """
        self._bloqueada = True
        sessao_service.registrar_evento(
            "SESSÃO BLOQUEADA", f"{MINUTOS_ATE_BLOQUEAR} minutos sem uso"
            + (" — extração em andamento" if self._extracao_em_andamento() else ""))
        self.hide()
        try:
            while True:
                entrada = TelaEntrada(self.marca, bloqueio=True,
                                      preselecionar=sessao_service.nome())
                if entrada.exec() == QDialog.Accepted:
                    self._atualizar_sessao()
                    self.show()
                    return
                if self._extracao_em_andamento():
                    QMessageBox.information(
                        None, "Extração em andamento",
                        "Há uma extração em andamento: a suíte não pode ser fechada agora. "
                        "Digite a senha para voltar.",
                    )
                    continue
                if QMessageBox.question(
                    None, "Sair", f"Deseja sair do {self.marca.nome_exibicao}?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                ) == QMessageBox.Yes:
                    self._sair_sem_perguntar = True
                    self.close()
                    return
        finally:
            self._vigia.ultimo_uso = time.monotonic()
            self._bloqueada = False

    def closeEvent(self, evento) -> None:
        """
        Sair pelo botão ou pelo "X" passa por aqui.

        Com extração em andamento, NÃO se sai: encerrar o programa no meio
        mataria a coleta antes do manifesto e do registro de encerramento, e
        a aquisição ficaria sem selo. O caminho é cancelar e esperar — o
        cancelamento fecha a aquisição corretamente.
        """
        if self._servico_extracao is not None and self._servico_extracao.isRunning():
            QMessageBox.warning(
                self, "Extração em andamento",
                "Há uma extração em andamento. Sair agora deixaria a aquisição sem o "
                "lacre (manifesto) e sem o registro de encerramento.\n\n"
                "Clique em 'Cancelar', aguarde a mensagem de extração finalizada e "
                "então saia.",
            )
            evento.ignore()
            return
        if not self._sair_sem_perguntar:
            resposta = QMessageBox.question(
                self, "Sair", f"Deseja sair do {self.marca.nome_exibicao}?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if resposta != QMessageBox.Yes:
                evento.ignore()
                return
        evento.accept()
        # A suíte só termina aqui (ver `main.py`): esconder a janela para
        # bloquear ou trocar de examinador não pode encerrar o programa. O
        # `quit` do Qt 6 pede de novo o fechamento das janelas; a marca
        # evita perguntar duas vezes.
        self._sair_sem_perguntar = True
        sessao_service.registrar_evento("SAÍDA DA SUÍTE")
        QApplication.instance().quit()

    def _mostrar_sobre(self) -> None:
        caixa = QMessageBox(self)
        caixa.setWindowTitle(f"Sobre o {self.marca.nome_exibicao}")
        caixa.setIconPixmap(self.windowIcon().pixmap(64, 64))
        caixa.setText(
            f"<b>{sessao_da_ferramenta()}</b><br><br>"
            "Suíte de aquisição e preservação de evidência digital para "
            "Android, iPhone e mídias de armazenamento, orientada pela "
            "ABNT NBR ISO/IEC 27037.<br><br>"
            "A ferramenta nunca afirma o que não verificou: ausência de dado "
            "no material adquirido não autoriza concluir ausência do dado no "
            "dispositivo.<br><br>"
            "Copyright © 2026 Hexis Forensics. Software livre, distribuído nos "
            "termos da GNU General Public License, versão 3 (GPL-3.0), <b>sem "
            "nenhuma garantia</b>. O texto da licença está no arquivo LICENSE."
        )
        termos = caixa.addButton("Termos de uso", QMessageBox.HelpRole)
        caixa.addButton("Fechar", QMessageBox.AcceptRole)
        caixa.exec()
        if caixa.clickedButton() is termos:
            TermosDialog(self, para_aceitar=False).exec()
