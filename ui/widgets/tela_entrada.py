"""
Tela de entrada: escolher o examinador e digitar a senha.

Também é onde se cadastra um examinador novo, onde quem já estava
cadastrado cria a senha no primeiro acesso, e onde quem esqueceu a senha
entra com o próprio código de recuperação. É a mesma tela do bloqueio por
inatividade e da troca de examinador.

Na versão de desenvolvimento, e só nela, aparece o acesso à conta de
testes (Forensic Admin).

Fala só com `services.sessao_service`. Todo texto de tela vem do catálogo
(`services.idioma.traduzir`).
"""

from __future__ import annotations

import platform

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QGuiApplication, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services import sessao_service
from services.branding_service import BrandConfig
from services.extraction_service import identificacao_da_ferramenta
from services.idioma import (
    definir_e_salvar,
    idioma_ativo,
    idiomas_disponiveis,
    nome_do_idioma,
    traduzir,
)

from .termos_dialog import TermosDialog
from .vitrine_entrada import VitrineAnimada
from .ajuste_de_tela import caber_na_tela

ENTRAR, NOVO, RECUPERAR, CODIGO, ADMIN = range(5)

# Código de retorno próprio: o examinador trocou o idioma e a tela precisa
# ser reaberta já no idioma novo (ver `abrir_entrada`). Diferente de
# Accepted (1) e Rejected (0).
REABRIR = 2


def abrir_entrada(marca, **kwargs) -> int:
    """
    Abre a tela de entrada, reabrindo-a se o examinador trocar o idioma.

    Trocar o idioma reconstrói a tela inteira. Em vez de reconstruir ao vivo
    (frágil, com dezenas de widgets e referências), a tela fecha com REABRIR
    e esta função a recria já no idioma novo. Devolve Accepted/Rejected ao
    chamador, como um `exec()` comum.
    """
    while True:
        resultado = TelaEntrada(marca, **kwargs).exec()
        if resultado != REABRIR:
            return resultado

ESTILO = """
#PainelMarca {
    background: qradialgradient(cx:0.2, cy:0.1, radius:1.2, fx:0.2, fy:0.1,
                stop:0 #18304f, stop:0.55 #0f1b2d, stop:1 #0a121e);
}
#PainelMarca QLabel { background: transparent; }
#Cartao, #Cartao QLabel#NomeCartao, #Cartao QLabel#DetalheCartao { background: transparent; }
#RodapeMarca { color: #8fa3bb; font-size: 12px; }
#TituloEntrada { font-size: 24px; font-weight: 600; }
#Sub { color: #9aa4af; font-size: 13px; }
#Nota { color: #7d8792; font-size: 11.5px; }
#ListaExaminadores { background: transparent; border: none; outline: none; }
#ListaExaminadores::item { border: 1px solid #333a42; border-radius: 8px;
    background: #22262d; margin-bottom: 8px; }
#ListaExaminadores::item:selected { border: 1px solid #3f8dfd; background: #1d2a3c; }
#Avatar { border-radius: 19px; background: #2b3440; color: #cfd8e2;
    font-weight: 700; font-size: 13px; }
#NomeCartao { font-weight: 600; font-size: 14px; background: transparent; }
#DetalheCartao { color: #9aa4af; font-size: 12px; background: transparent; }
#SeloAdmin { color: #19c3a6; border: 1px solid rgba(25,195,166,110); border-radius: 9px;
    padding: 1px 7px; font-size: 10px; font-weight: 600; background: transparent; }
#Primario { background: #3f8dfd; color: #0b0d10; font-weight: 600; border: none;
    border-radius: 7px; padding: 0 22px; min-height: 38px; }
#Primario:hover { background: #5a9dfd; }
#Secundario { border-radius: 7px; padding: 0 18px; min-height: 36px; }
#Link { color: #3f8dfd; background: transparent; border: none; text-align: left; }
#Link:hover { text-decoration: underline; }
#Erro { color: #ff6b6b; font-size: 12.5px; }
#Codigo { background: #11202f; border: 1px dashed #3f8dfd; border-radius: 8px;
    font-family: Consolas; font-size: 24px; color: #cfe2ff; padding: 16px; }
QLineEdit { min-height: 36px; border-radius: 7px; padding: 0 10px; }
"""


def _iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p[:1].isalpha()]
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


class _Cartao(QWidget):
    def __init__(self, examinador: dict):
        super().__init__()
        self.setObjectName("Cartao")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        avatar = QLabel(_iniciais(examinador["nome"]))
        avatar.setObjectName("Avatar")
        avatar.setFixedSize(38, 38)
        avatar.setAlignment(Qt.AlignCenter)
        layout.addWidget(avatar)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        nome = QLabel(examinador["nome"])
        nome.setObjectName("NomeCartao")
        if not examinador["tem_senha"]:
            detalhe = traduzir("te_cartao_primeiro_acesso")
        elif examinador["bloqueado_ate"]:
            detalhe = traduzir("te_cartao_travado", ate=examinador['bloqueado_ate'])
        else:
            detalhe = " · ".join(p for p in (
                traduzir("te_cartao_reg", valor=examinador['registro_funcional'])
                if examinador["registro_funcional"] else "",
                examinador["unidade"],
            ) if p) or traduzir("te_cartao_examinador")
        rotulo = QLabel(detalhe)
        rotulo.setObjectName("DetalheCartao")
        textos.addWidget(nome)
        textos.addWidget(rotulo)
        layout.addLayout(textos, 1)


class TelaEntrada(QDialog):
    """
    `bloqueio=True`: a sessão foi bloqueada por inatividade; o examinador
    da sessão vem escolhido e ninguém precisa cadastrar nada.
    """

    def __init__(self, marca: BrandConfig, parent=None, bloqueio: bool = False,
                 preselecionar: str = "", texto_sair: str = None,
                 abrir_cadastro: bool = False):
        super().__init__(parent)
        self.marca = marca
        self.bloqueio = bloqueio
        if texto_sair is None:
            texto_sair = traduzir("te_sair")
        self.setWindowTitle(
            marca.nome_exibicao + (traduzir("te_sufixo_bloqueada") if bloqueio else "")
        )
        self.setModal(True)
        # Diálogo, no Windows, vem só com o X: a entrada é a primeira tela da
        # suíte e precisa minimizar e maximizar como uma janela comum.
        # Botão a botão: o "~" nas flags do PySide6 apaga também o do X.
        for botao in (Qt.WindowMinimizeButtonHint, Qt.WindowMaximizeButtonHint,
                      Qt.WindowCloseButtonHint):
            self.setWindowFlag(botao, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        caber_na_tela(self, 980, 620)
        self.setStyleSheet(ESTILO)
        self._codigo_mostrado = ""
        self._apos_codigo = None

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._painel_marca(), 42)

        direita = QFrame()
        direita.setObjectName("PainelEntrada")
        coluna = QVBoxLayout(direita)
        coluna.setContentsMargins(46, 40, 46, 30)

        # Seletor de idioma, no topo: escolhido aqui, antes do login, todo o
        # resto do app já abre no idioma escolhido. Trocar reabre esta tela
        # (ver `abrir_entrada`), evitando reconstrução ao vivo.
        disponiveis = idiomas_disponiveis()
        if len(disponiveis) > 1:
            linha_idioma = QHBoxLayout()
            linha_idioma.addStretch()
            linha_idioma.addWidget(QLabel("🌐"))
            self.combo_idioma = QComboBox()
            for cod in disponiveis:
                self.combo_idioma.addItem(nome_do_idioma(cod), cod)
            self.combo_idioma.setCurrentIndex(disponiveis.index(idioma_ativo()))
            self.combo_idioma.setToolTip(traduzir("sel_idioma_tooltip"))
            # Conectar só DEPOIS de posicionar: a montagem não dispara a troca.
            self.combo_idioma.currentIndexChanged.connect(self._trocar_idioma)
            linha_idioma.addWidget(self.combo_idioma)
            coluna.addLayout(linha_idioma)

        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._pagina_entrar())
        self.paginas.addWidget(self._pagina_novo())
        self.paginas.addWidget(self._pagina_recuperar())
        self.paginas.addWidget(self._pagina_codigo())
        self.paginas.addWidget(self._pagina_admin())
        coluna.addWidget(self.paginas)
        # Sair sem precisar achar o "X" da janela — útil sobretudo com a
        # entrada travada por tentativas erradas. Fechar a tela já é sair
        # para quem a abriu (no bloqueio, quem abriu ainda confirma).
        rodape = QHBoxLayout()
        rodape.addStretch()
        self.botao_sair = QPushButton(texto_sair)
        self.botao_sair.setObjectName("Link")
        self.botao_sair.setCursor(Qt.PointingHandCursor)
        self.botao_sair.clicked.connect(self.reject)
        rodape.addWidget(self.botao_sair)
        coluna.addLayout(rodape)
        raiz.addWidget(direita, 58)

        self._recuperando_admin = False
        if bloqueio and sessao_service.e_forensic_admin():
            self._ir_para_admin()
        else:
            self._carregar(preselecionar or sessao_service.ultimo())
            if abrir_cadastro and self._examinadores:
                self._ir_para_novo()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _painel_marca(self) -> QWidget:
        painel = QFrame()
        painel.setObjectName("PainelMarca")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(44, 50, 40, 36)
        logo = QLabel()
        pixmap = QPixmap(str(self.marca.caminho_logo)) if self.marca.caminho_logo else QPixmap()
        if pixmap.isNull():
            logo.setText(self.marca.nome_exibicao)
            logo.setStyleSheet("font-size: 26px; font-weight: 700; color: white;")
        else:
            logo.setPixmap(pixmap.scaled(QSize(270, 94), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
        layout.addWidget(logo)
        layout.addSpacing(18)
        # As três cenas da perícia, no lugar do espaço vazio do painel.
        self.vitrine = VitrineAnimada()
        layout.addWidget(self.vitrine, 1)
        layout.addSpacing(14)
        self.rodape_marca = QLabel(traduzir(
            "te_rodape_marca",
            ferramenta=identificacao_da_ferramenta(),
            estacao=platform.node() or traduzir("te_estacao_nao_identificada"),
        ))
        self.rodape_marca.setObjectName("RodapeMarca")
        layout.addWidget(self.rodape_marca)
        return painel

    def _titulo(self, layout, titulo: str, subtitulo: str) -> QLabel:
        rotulo = QLabel(titulo)
        rotulo.setObjectName("TituloEntrada")
        layout.addWidget(rotulo)
        sub = QLabel(subtitulo)
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(12)
        return sub

    def _botao(self, texto: str, primario: bool = False) -> QPushButton:
        botao = QPushButton(texto)
        botao.setObjectName("Primario" if primario else "Secundario")
        botao.setCursor(Qt.PointingHandCursor)
        return botao

    def _senha(self, placeholder: str) -> QLineEdit:
        campo = QLineEdit()
        campo.setEchoMode(QLineEdit.Password)
        campo.setPlaceholderText(placeholder)
        return campo

    def _erro(self) -> QLabel:
        rotulo = QLabel()
        rotulo.setObjectName("Erro")
        rotulo.setWordWrap(True)
        rotulo.hide()
        return rotulo

    def _pagina_entrar(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sub_entrar = self._titulo(
            layout,
            traduzir("te_titulo_bloqueada") if self.bloqueio else traduzir("te_titulo_entrar"),
            traduzir("te_sub_bloqueada") if self.bloqueio else traduzir("te_sub_entrar"),
        )
        self.lista = QListWidget()
        self.lista.setObjectName("ListaExaminadores")
        self.lista.setSpacing(0)
        self.lista.currentRowChanged.connect(self._ao_escolher)
        layout.addWidget(self.lista, 1)

        self.rotulo_senha = QLabel()
        self.rotulo_senha.setObjectName("Sub")
        layout.addWidget(self.rotulo_senha)
        self.campo_senha = self._senha(traduzir("te_ph_senha"))
        self.campo_senha.returnPressed.connect(self._entrar)
        layout.addWidget(self.campo_senha)
        self.campo_repetir = self._senha(traduzir("te_ph_repita"))
        self.campo_repetir.returnPressed.connect(self._entrar)
        layout.addWidget(self.campo_repetir)
        self.erro_entrar = self._erro()
        layout.addWidget(self.erro_entrar)

        acoes = QHBoxLayout()
        self.botao_entrar = self._botao(traduzir("te_btn_entrar"), primario=True)
        self.botao_entrar.clicked.connect(self._entrar)
        acoes.addWidget(self.botao_entrar)
        self.link_esqueci = QPushButton(traduzir("te_esqueci"))
        self.link_esqueci.setObjectName("Link")
        self.link_esqueci.setCursor(Qt.PointingHandCursor)
        self.link_esqueci.clicked.connect(self._esqueci)
        acoes.addSpacing(10)
        acoes.addWidget(self.link_esqueci)
        acoes.addStretch()
        layout.addLayout(acoes)

        self.botao_novo = self._botao(traduzir("te_btn_novo"))
        self.botao_novo.clicked.connect(lambda: self._ir_para_novo())
        if not self.bloqueio:
            layout.addSpacing(14)
            separador = QLabel(traduzir("te_ou"))
            separador.setAlignment(Qt.AlignCenter)
            separador.setObjectName("Nota")
            layout.addWidget(separador)
            layout.addWidget(self.botao_novo, 0, Qt.AlignLeft)
        nota = QLabel(traduzir("te_nota_sessao"))
        nota.setObjectName("Nota")
        nota.setWordWrap(True)
        layout.addSpacing(10)
        layout.addWidget(nota)
        if sessao_service.forensic_admin_disponivel() and not self.bloqueio:
            link_admin = QPushButton(traduzir("te_link_admin"))
            link_admin.setObjectName("Link")
            link_admin.setCursor(Qt.PointingHandCursor)
            link_admin.clicked.connect(self._ir_para_admin)
            layout.addWidget(link_admin)
        return pagina

    def _pagina_admin(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sub_admin = self._titulo(layout, traduzir("te_admin_titulo"), "")
        aviso = QLabel(traduzir("te_admin_aviso"))
        aviso.setWordWrap(True)
        aviso.setObjectName("Sub")
        layout.addWidget(aviso)
        layout.addSpacing(10)
        self.admin_senha = self._senha(traduzir("te_ph_senha_admin"))
        self.admin_senha.returnPressed.connect(self._entrar_admin)
        self.admin_repetir = self._senha(traduzir("te_ph_repita"))
        self.admin_repetir.returnPressed.connect(self._entrar_admin)
        layout.addWidget(self.admin_senha)
        layout.addWidget(self.admin_repetir)
        self.erro_admin = self._erro()
        layout.addWidget(self.erro_admin)
        acoes = QHBoxLayout()
        self.botao_admin = self._botao(traduzir("te_btn_entrar"), primario=True)
        self.botao_admin.clicked.connect(self._entrar_admin)
        acoes.addWidget(self.botao_admin)
        self.link_esqueci_admin = QPushButton(traduzir("te_esqueci_admin"))
        self.link_esqueci_admin.setObjectName("Link")
        self.link_esqueci_admin.setCursor(Qt.PointingHandCursor)
        self.link_esqueci_admin.clicked.connect(lambda: self._ir_para_recuperar(admin=True))
        acoes.addSpacing(10)
        acoes.addWidget(self.link_esqueci_admin)
        acoes.addStretch()
        layout.addLayout(acoes)
        layout.addStretch()
        self.botao_voltar_admin = self._botao(traduzir("te_voltar"))
        self.botao_voltar_admin.clicked.connect(
            lambda: self._carregar(sessao_service.ultimo()))
        layout.addWidget(self.botao_voltar_admin, 0, Qt.AlignLeft)
        return pagina

    def _ir_para_admin(self) -> None:
        configurado = sessao_service.forensic_admin_configurado()
        self.sub_admin.setText(
            traduzir("te_admin_sub_entrar") if configurado else
            traduzir("te_admin_sub_criar", min=sessao_service.TAMANHO_MINIMO_DA_SENHA)
        )
        self.admin_repetir.setVisible(not configurado)
        self.link_esqueci_admin.setVisible(configurado)
        self.botao_admin.setText(
            traduzir("te_btn_entrar") if configurado else traduzir("te_btn_criar_entrar")
        )
        self.botao_voltar_admin.setVisible(not self.bloqueio)
        self.admin_senha.clear()
        self.admin_repetir.clear()
        self.erro_admin.hide()
        self.paginas.setCurrentIndex(ADMIN)
        self.admin_senha.setFocus()

    def _entrar_admin(self) -> None:
        try:
            if sessao_service.forensic_admin_configurado():
                sessao_service.entrar_forensic_admin(self.admin_senha.text())
                codigo = ""
            else:
                if self.admin_senha.text() != self.admin_repetir.text():
                    self._mostrar_erro(self.erro_admin, traduzir("te_senhas_nao_conferem"))
                    return
                codigo = sessao_service.configurar_forensic_admin(self.admin_senha.text())
        except sessao_service.ErroDeAcesso as erro:
            self._mostrar_erro(self.erro_admin, str(erro))
            self.admin_senha.selectAll()
            return
        self._depois_de_entrar(codigo)

    def _pagina_novo(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sub_novo = self._titulo(layout, traduzir("te_novo_titulo"),
                                     traduzir("te_novo_sub"))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.campos_novo = {}
        for chave, rotulo_key, exemplo_key in (
            ("nome", "te_novo_nome", "te_novo_nome_ex"),
            ("registro_funcional", "te_novo_registro", "te_novo_registro_ex"),
            ("unidade", "te_novo_unidade", "te_novo_unidade_ex"),
            ("email", "te_novo_email", "te_novo_email_ex"),
        ):
            campo = QLineEdit()
            campo.setPlaceholderText(traduzir(exemplo_key))
            self.campos_novo[chave] = campo
            form.addRow(traduzir(rotulo_key), campo)
        self.novo_senha = self._senha(
            traduzir("te_ph_min", min=sessao_service.TAMANHO_MINIMO_DA_SENHA))
        self.novo_repetir = self._senha(traduzir("te_ph_repita_min"))
        self.novo_repetir.returnPressed.connect(self._cadastrar)
        form.addRow(traduzir("te_label_senha"), self.novo_senha)
        form.addRow(traduzir("te_label_repita"), self.novo_repetir)
        layout.addLayout(form)
        linha_termos = QHBoxLayout()
        self.aceite_termos = QCheckBox(traduzir("te_aceite_termos"))
        ler_termos = QPushButton(traduzir("te_ler_termos"))
        ler_termos.setObjectName("Link")
        ler_termos.setCursor(Qt.PointingHandCursor)
        ler_termos.clicked.connect(
            lambda: TermosDialog(self, para_aceitar=False).exec())
        linha_termos.addWidget(self.aceite_termos)
        linha_termos.addWidget(ler_termos)
        linha_termos.addStretch()
        layout.addLayout(linha_termos)
        self.erro_novo = self._erro()
        layout.addWidget(self.erro_novo)
        layout.addStretch()
        acoes = QHBoxLayout()
        self.botao_voltar_novo = self._botao(traduzir("te_voltar"))
        self.botao_voltar_novo.clicked.connect(lambda: self.paginas.setCurrentIndex(ENTRAR))
        cadastrar = self._botao(traduzir("te_cadastrar"), primario=True)
        cadastrar.clicked.connect(self._cadastrar)
        acoes.addWidget(self.botao_voltar_novo)
        acoes.addStretch()
        acoes.addWidget(cadastrar)
        layout.addLayout(acoes)
        if sessao_service.forensic_admin_disponivel() and not self.bloqueio:
            link_admin = QPushButton(traduzir("te_link_admin"))
            link_admin.setObjectName("Link")
            link_admin.setCursor(Qt.PointingHandCursor)
            link_admin.clicked.connect(self._ir_para_admin)
            layout.addWidget(link_admin)
        return pagina

    def _pagina_recuperar(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sub_recuperar = self._titulo(
            layout, traduzir("te_recuperar_titulo"), traduzir("te_recuperar_sub"),
        )
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.campo_codigo = QLineEdit()
        self.campo_codigo.setPlaceholderText(traduzir("te_ph_codigo"))
        self.recuperar_senha = self._senha(traduzir("te_ph_nova_senha"))
        self.recuperar_repetir = self._senha(traduzir("te_ph_repita_nova"))
        self.recuperar_repetir.returnPressed.connect(self._recuperar)
        form.addRow(traduzir("te_label_codigo"), self.campo_codigo)
        form.addRow(traduzir("te_label_nova_senha"), self.recuperar_senha)
        form.addRow(traduzir("te_label_repita_nova"), self.recuperar_repetir)
        layout.addLayout(form)
        self.erro_recuperar = self._erro()
        layout.addWidget(self.erro_recuperar)
        layout.addStretch()
        acoes = QHBoxLayout()
        voltar = self._botao(traduzir("te_voltar"))
        voltar.clicked.connect(lambda: self.paginas.setCurrentIndex(
            ADMIN if self._recuperando_admin else ENTRAR))
        confirmar = self._botao(traduzir("te_redefinir"), primario=True)
        confirmar.clicked.connect(self._recuperar)
        acoes.addWidget(voltar)
        acoes.addStretch()
        acoes.addWidget(confirmar)
        layout.addLayout(acoes)
        return pagina

    def _pagina_codigo(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(0, 0, 0, 0)
        self._titulo(
            layout, traduzir("te_codigo_titulo"), traduzir("te_codigo_sub"),
        )
        self.rotulo_codigo = QLabel()
        self.rotulo_codigo.setObjectName("Codigo")
        self.rotulo_codigo.setAlignment(Qt.AlignCenter)
        self.rotulo_codigo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.rotulo_codigo)
        botoes = QHBoxLayout()
        imprimir = self._botao(traduzir("te_imprimir"))
        imprimir.clicked.connect(self._imprimir_codigo)
        copiar = self._botao(traduzir("te_copiar"))
        copiar.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self._codigo_mostrado))
        botoes.addWidget(imprimir)
        botoes.addWidget(copiar)
        botoes.addStretch()
        layout.addLayout(botoes)
        layout.addSpacing(10)
        self.confirmacao_codigo = QCheckBox(traduzir("te_codigo_confirmo"))
        layout.addWidget(self.confirmacao_codigo)
        layout.addStretch()
        acoes = QHBoxLayout()
        acoes.addStretch()
        self.botao_continuar = self._botao(traduzir("te_continuar"), primario=True)
        self.botao_continuar.setEnabled(False)
        self.confirmacao_codigo.toggled.connect(self.botao_continuar.setEnabled)
        self.botao_continuar.clicked.connect(self.accept)
        acoes.addWidget(self.botao_continuar)
        layout.addLayout(acoes)
        return pagina

    # ------------------------------------------------------------------
    # Comportamento
    # ------------------------------------------------------------------
    def _carregar(self, preselecionar: str) -> None:
        self._examinadores = sessao_service.examinadores()
        if self.bloqueio:
            self._examinadores = [e for e in self._examinadores
                                  if e["nome"].lower() == preselecionar.lower()] or self._examinadores
        self.lista.clear()
        for examinador in self._examinadores:
            item = QListWidgetItem()
            cartao = _Cartao(examinador)
            item.setSizeHint(QSize(0, 62))
            self.lista.addItem(item)
            self.lista.setItemWidget(item, cartao)
        if not self._examinadores:
            # Estação nova: começa pelo cadastro do primeiro examinador.
            self._ir_para_novo(primeiro=True)
            return
        nomes = [e["nome"].lower() for e in self._examinadores]
        indice = nomes.index(preselecionar.lower()) if preselecionar.lower() in nomes else 0
        self.lista.setCurrentRow(indice)
        self.paginas.setCurrentIndex(ENTRAR)

    def _escolhido(self) -> dict:
        linha = self.lista.currentRow()
        return self._examinadores[linha] if 0 <= linha < len(self._examinadores) else {}

    def _ao_escolher(self, _linha: int) -> None:
        examinador = self._escolhido()
        if not examinador:
            return
        primeiro_acesso = not examinador["tem_senha"]
        self.rotulo_senha.setText(
            traduzir("te_primeiro_acesso_de", nome=examinador['nome'],
                     min=sessao_service.TAMANHO_MINIMO_DA_SENHA)
            if primeiro_acesso else traduzir("te_senha_de", nome=examinador['nome'])
        )
        self.campo_repetir.setVisible(primeiro_acesso)
        self.botao_entrar.setText(
            traduzir("te_btn_criar_entrar") if primeiro_acesso else traduzir("te_btn_entrar")
        )
        self.link_esqueci.setVisible(not primeiro_acesso)
        self.campo_senha.clear()
        self.campo_repetir.clear()
        self.erro_entrar.hide()
        self.campo_senha.setFocus()

    def _mostrar_erro(self, rotulo: QLabel, texto: str) -> None:
        rotulo.setText(texto)
        rotulo.show()

    def _depois_de_entrar(self, codigo: str) -> None:
        if codigo:
            self._codigo_mostrado = codigo
            self.rotulo_codigo.setText(codigo)
            self.confirmacao_codigo.setChecked(False)
            self.paginas.setCurrentIndex(CODIGO)
        else:
            self.accept()

    def _entrar(self) -> None:
        examinador = self._escolhido()
        if not examinador:
            return
        senha = self.campo_senha.text()
        try:
            if examinador["tem_senha"]:
                sessao_service.entrar(examinador["nome"], senha)
                codigo = ""
            else:
                if senha != self.campo_repetir.text():
                    self._mostrar_erro(self.erro_entrar, traduzir("te_senhas_nao_conferem"))
                    return
                codigo = sessao_service.criar_senha_e_entrar(examinador["nome"], senha)
        except sessao_service.ErroDeAcesso as erro:
            self._mostrar_erro(self.erro_entrar, str(erro))
            self.campo_senha.selectAll()
            self.campo_senha.setFocus()
            if "às" in str(erro):  # travou agora: atualiza o cartão
                self._carregar(examinador["nome"])
                self._mostrar_erro(self.erro_entrar, str(erro))
            return
        self._depois_de_entrar(codigo)

    def _ir_para_novo(self, primeiro: bool = False) -> None:
        for campo in self.campos_novo.values():
            campo.clear()
        self.novo_senha.clear()
        self.novo_repetir.clear()
        self.erro_novo.hide()
        self.botao_voltar_novo.setVisible(not primeiro)
        self.sub_novo.setText(
            traduzir("te_novo_primeiro") if primeiro else traduzir("te_novo_sub")
        )
        self.paginas.setCurrentIndex(NOVO)
        self.campos_novo["nome"].setFocus()

    def _cadastrar(self) -> None:
        dados = {chave: campo.text().strip() for chave, campo in self.campos_novo.items()}
        if self.novo_senha.text() != self.novo_repetir.text():
            self._mostrar_erro(self.erro_novo, traduzir("te_senhas_nao_conferem"))
            return
        if not self.aceite_termos.isChecked():
            self._mostrar_erro(self.erro_novo, traduzir("te_aceite_obrigatorio"))
            return
        try:
            codigo = sessao_service.cadastrar_e_entrar(dados, self.novo_senha.text())
            sessao_service.aceitar_termos()
        except sessao_service.ErroDeAcesso as erro:
            self._mostrar_erro(self.erro_novo, str(erro))
            return
        self._depois_de_entrar(codigo)

    def accept(self) -> None:
        """
        Toda entrada passa por aqui. Quem ainda não aceitou a versão atual dos
        termos (examinador cadastrado antes deles, ou texto novo) aceita agora,
        em nome próprio — ou não entra.
        """
        if sessao_service.ativa() and not sessao_service.termos_aceitos():
            dialogo = TermosDialog(self, para_aceitar=True, nome=sessao_service.nome())
            if dialogo.exec() != QDialog.Accepted:
                sessao_service.registrar_evento("TERMOS DE USO RECUSADOS")
                sessao_service.encerrar()
                self.paginas.setCurrentIndex(ENTRAR)
                return
            try:
                sessao_service.aceitar_termos()
            except sessao_service.ErroDeAcesso as erro:
                QMessageBox.warning(self, traduzir("te_termos_titulo"), str(erro))
                sessao_service.encerrar()
                return
        super().accept()

    def _trocar_idioma(self, indice: int) -> None:
        cod = self.combo_idioma.itemData(indice)
        if cod and cod != idioma_ativo():
            definir_e_salvar(cod)
            self.done(REABRIR)

    def _esqueci(self) -> None:
        if self._escolhido():
            self._ir_para_recuperar(admin=False)

    def _ir_para_recuperar(self, admin: bool) -> None:
        self._recuperando_admin = admin
        self.campo_codigo.clear()
        self.recuperar_senha.clear()
        self.recuperar_repetir.clear()
        self.erro_recuperar.hide()
        self.paginas.setCurrentIndex(RECUPERAR)
        self.campo_codigo.setFocus()

    def _recuperar(self) -> None:
        if self.recuperar_senha.text() != self.recuperar_repetir.text():
            self._mostrar_erro(self.erro_recuperar, traduzir("te_senhas_nao_conferem"))
            return
        try:
            if self._recuperando_admin:
                novo = sessao_service.recuperar_forensic_admin(
                    self.campo_codigo.text(), self.recuperar_senha.text())
            else:
                novo = sessao_service.recuperar_e_entrar(
                    self._escolhido()["nome"], self.campo_codigo.text(),
                    self.recuperar_senha.text())
        except sessao_service.ErroDeAcesso as erro:
            self._mostrar_erro(self.erro_recuperar, str(erro))
            return
        self._depois_de_entrar(novo)

    def _imprimir_codigo(self) -> None:
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(
                self, traduzir("te_imprimir_titulo"), traduzir("te_impressao_indisponivel")
            )
            return
        impressora = QPrinter()
        if QPrintDialog(impressora, self).exec() != QDialog.Accepted:
            return
        documento = QTextDocument()
        documento.setHtml(traduzir(
            "te_codigo_impresso",
            marca=self.marca.nome_exibicao,
            examinador=sessao_service.nome(),
            estacao=platform.node(),
            codigo=self._codigo_mostrado,
        ))
        documento.print_(impressora)
