"""
Menu lateral (sidebar) de navegação.

O cabeçalho mostra o logo do perfil de marca ativo (ou, na falta dele, o
nome de exibição). Em seguida vêm as
seções de navegação ("MENU PRINCIPAL", "FERRAMENTAS"). Emite um sinal com
a chave do item clicado — quem decide o que fazer com cada chave (trocar
de página, abrir um diálogo, etc.) é a `MainWindow`; este widget não
conhece nada além de "o que foi clicado".

Não importa nada de `core` — só recebe um `BrandConfig` (de `services`)
para saber o que desenhar.

Implementado com `QLabel` (títulos de seção) + `QPushButton` (itens),
em vez de um único `QListWidget` misturando os dois: itens não-clicáveis
dentro de um `QListWidget` dependem do cálculo de `sizeHint` do delegate
para cada linha, que trata itens desabilitados (`Qt.NoItemFlags`) de forma
inconsistente entre estilos/plataformas e pode gerar sobreposição visual.
Com widgets normais de layout, cada um sabe seu próprio tamanho e não há
esse tipo de artefato.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.branding_service import BrandConfig

LARGURA_SIDEBAR = 260

# Tamanho máximo do logo dentro do cabeçalho da sidebar — a imagem é
# reduzida (nunca ampliada) mantendo a proporção original, para caber bem
# tanto um logo bem largo (retangular) quanto um ícone quadrado/vertical,
# sem estourar a largura fixa da sidebar. Cada perfil de marca pode trazer
# um PNG totalmente diferente (ver `branding/<perfil>/branding.json`,
# campo "logo") sem precisar tocar neste código.
TAMANHO_MAXIMO_LOGO = QSize(224, 78)

# Chaves que representam páginas de navegação (ficam destacadas/"ativas"
# enquanto a página correspondente estiver visível). As demais chaves são
# ações pontuais (abrir diálogo, abrir pasta, etc.) e nunca ficam marcadas.
CHAVES_NAVEGACAO = {"android", "iphone", "computador"}


class Sidebar(QWidget):
    item_selecionado = Signal(str)

    def __init__(self, marca: BrandConfig, parent=None):
        super().__init__(parent)
        self._marca = marca
        self._botoes: dict[str, QPushButton] = {}
        self.setObjectName("Sidebar")
        self.setFixedWidth(LARGURA_SIDEBAR)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._montar_cabecalho())

        self._corpo = QVBoxLayout()
        self._corpo.setContentsMargins(0, 12, 0, 0)
        self._corpo.setSpacing(2)
        layout.addLayout(self._corpo)
        layout.addStretch(1)
        # A sessão mora no rodapé, separada das ferramentas: "Examinadores"
        # (o cadastro) e "Trocar examinador" (a sessão) não ficam lado a lado.
        layout.addWidget(self._montar_sessao())

        self._grupo_navegacao = QButtonGroup(self)
        self._grupo_navegacao.setExclusive(True)

        self._montar_itens()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    def _montar_cabecalho(self) -> QWidget:
        """
        O logo da marca, no topo. Sem logo configurado (ou com arquivo
        ilegível), o nome de exibição entra no lugar — o logo já traz o
        nome escrito, e mostrar os dois seria dizer a mesma coisa duas vezes.
        """
        cabecalho = QWidget()
        cabecalho.setObjectName("SidebarCabecalho")
        layout = QVBoxLayout(cabecalho)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(10)

        pixmap = QPixmap(str(self._marca.caminho_logo)) if self._marca.caminho_logo else QPixmap()
        if not pixmap.isNull():
            label_logo = QLabel()
            label_logo.setObjectName("SidebarLogo")
            label_logo.setPixmap(
                pixmap.scaled(TAMANHO_MAXIMO_LOGO, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            layout.addWidget(label_logo)
        else:
            label_nome = QLabel(self._marca.nome_exibicao)
            label_nome.setObjectName("SidebarNomeMarca")
            label_nome.setWordWrap(True)
            layout.addWidget(label_nome)

        return cabecalho

    def _montar_itens(self) -> None:
        self._adicionar_secao("MENU PRINCIPAL", primeira=True)
        self._adicionar_item("android", "🤖  Android", navegavel=True)
        self._adicionar_item("iphone", "📱  iPhone", navegavel=True)
        # "Armazenamento", e não "Computador", porque o alvo desta
        # plataforma nunca é uma máquina: é uma unidade montada pelo
        # Windows. No procedimento adotado, o disco do computador
        # periciado chega à estação por dock/adaptador e aparece aqui como
        # mais uma unidade, ao lado de HD externo e pendrive.
        #
        # Também não é "Armazenamento Externo": a lista sempre contém pelo
        # menos um disco interno — a própria estação do examinador, que o
        # DiskPanel mostra NOMEADA em vez de esconder.
        #
        # A CHAVE segue "computador". Rótulo é apresentação; a nomenclatura
        # da evidência (pasta `computador_AAAAMMDD_HHMMSS`, laudo) vem só de
        # core/case.py, que também LÊ as aquisições já gravadas em disco.
        self._adicionar_item("computador", "💾  Armazenamento", navegavel=True)

        self._adicionar_secao("FERRAMENTAS")
        self._adicionar_item("hash", "🔐  Cadeia de Custódia")
        self._adicionar_item("abrir_pasta", "📂  Casos e Documentos")
        self._adicionar_item("examinadores", "👥  Examinadores")

        self._adicionar_separador()
        self._adicionar_item("sobre", "ℹ️  Sobre")

    def _montar_sessao(self) -> QWidget:
        rodape = QFrame()
        rodape.setObjectName("SidebarSessao")
        rodape.setStyleSheet(
            "#SidebarSessao { border-top: 1px solid #333a42; }"
            "#SessaoAvatar { border-radius: 16px; background: #3f8dfd; color: #0b0d10;"
            " font-weight: 700; font-size: 12px; }"
            "#SessaoNome { font-weight: 600; font-size: 13px; }"
            "#SessaoDesde { color: #9aa4af; font-size: 11.5px; }"
        )
        layout = QVBoxLayout(rodape)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(2)
        linha = QHBoxLayout()
        linha.setContentsMargins(18, 0, 12, 4)
        linha.setSpacing(10)
        self._avatar = QLabel("?")
        self._avatar.setObjectName("SessaoAvatar")
        self._avatar.setFixedSize(32, 32)
        self._avatar.setAlignment(Qt.AlignCenter)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self._nome_sessao = QLabel()
        self._nome_sessao.setObjectName("SessaoNome")
        self._desde = QLabel()
        self._desde.setObjectName("SessaoDesde")
        textos.addWidget(self._nome_sessao)
        textos.addWidget(self._desde)
        linha.addWidget(self._avatar)
        linha.addLayout(textos, 1)
        layout.addLayout(linha)
        for chave, rotulo in (("trocar_examinador", "🔄  Trocar examinador"), ("sair", "🚪  Sair")):
            botao = QPushButton(rotulo)
            botao.setObjectName("SidebarItem")
            botao.setFlat(True)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            botao.clicked.connect(lambda _=False, c=chave: self.item_selecionado.emit(c))
            self._botoes[chave] = botao
            layout.addWidget(botao)
        return rodape

    def atualizar_sessao(self, nome: str, iniciais: str, desde: str) -> None:
        """Quem está na sessão, no rodapé da barra."""
        self._avatar.setText(iniciais)
        self._nome_sessao.setText(nome or "—")
        self._nome_sessao.setToolTip(nome)
        self._desde.setText(f"sessão desde {desde}" if desde else "")

    def _adicionar_secao(self, titulo: str, primeira: bool = False) -> None:
        label = QLabel(titulo)
        label.setObjectName("SidebarSecao")
        label.setProperty("primeira", primeira)
        self._corpo.addWidget(label)

    def _adicionar_separador(self) -> None:
        linha = QFrame()
        linha.setObjectName("SidebarSeparador")
        linha.setFrameShape(QFrame.HLine)
        linha.setFixedHeight(1)
        self._corpo.addSpacing(10)
        self._corpo.addWidget(linha)
        self._corpo.addSpacing(10)

    def _adicionar_item(self, chave: str, rotulo: str, navegavel: bool = False) -> None:
        botao = QPushButton(rotulo)
        botao.setObjectName("SidebarItem")
        botao.setFlat(True)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        botao.setCheckable(navegavel)
        botao.clicked.connect(lambda: self.item_selecionado.emit(chave))

        if navegavel:
            self._grupo_navegacao.addButton(botao)

        self._botoes[chave] = botao
        self._corpo.addWidget(botao)

    # ------------------------------------------------------------------
    # Interação
    # ------------------------------------------------------------------
    def selecionar(self, chave: str) -> None:
        """Realça visualmente o item correspondente à página atual.

        Só se aplica a chaves de navegação (`CHAVES_NAVEGACAO`) — itens de
        ação (hash, abrir pasta, sobre) nunca ficam marcados como "ativos".
        """
        botao = self._botoes.get(chave)
        if botao is not None and botao.isCheckable():
            botao.setChecked(True)
