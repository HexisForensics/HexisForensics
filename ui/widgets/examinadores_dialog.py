"""
Cadastro dos examinadores desta estação.

Cada examinador vê e corrige só os próprios dados, troca a própria senha e
gera um código de recuperação novo. Ninguém redefine a senha de outro.

A conta de testes (Forensic Admin, só na versão de desenvolvimento) vê
todos, cadastra e redefine senhas — para testar a suíte. Toda operação de
senha vai para o registro de acessos da estação.

Alterar um examinador aqui NÃO altera as aquisições que ele já fez: cada
uma guarda, sob o selo, o examinador como estava no dia.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services import perfil_service, sessao_service
from services.idioma import traduzir
from .ajuste_de_tela import caber_na_tela


class _SenhaDialog(QDialog):
    """Pede uma senha (e a atual, quando é troca da própria)."""

    def __init__(self, titulo: str, texto: str, pedir_atual: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        layout = QVBoxLayout(self)
        rotulo = QLabel(texto)
        rotulo.setWordWrap(True)
        layout.addWidget(rotulo)
        form = QFormLayout()
        self.atual = QLineEdit()
        self.nova = QLineEdit()
        self.repetir = QLineEdit()
        for campo in (self.atual, self.nova, self.repetir):
            campo.setEchoMode(QLineEdit.Password)
        if pedir_atual:
            form.addRow(traduzir("ex_senha_atual"), self.atual)
        form.addRow(traduzir("ex_nova_senha", min=sessao_service.TAMANHO_MINIMO_DA_SENHA), self.nova)
        form.addRow(traduzir("ex_repita_nova"), self.repetir)
        layout.addLayout(form)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._ok)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _ok(self) -> None:
        if self.nova.text() != self.repetir.text():
            QMessageBox.warning(self, traduzir("ex_senha_titulo"), traduzir("ex_senhas_nao_conferem"))
            return
        self.accept()


class ExaminadoresDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(traduzir("ex_titulo"))
        self.setModal(True)
        caber_na_tela(self, 820, 460)
        self._administrador = sessao_service.e_forensic_admin()
        # Quem excluiu o próprio perfil sai da sessão: a janela principal
        # volta à tela de entrada.
        self.excluiu_o_proprio = False
        # Pedido de cadastro de outro examinador (versão distribuída): a
        # janela principal abre a tela de entrada já no cadastro.
        self.pediu_cadastro = False
        self._editando = ""  # nome aberto no formulário; vazio = novo

        principal = QHBoxLayout(self)
        principal.setContentsMargins(16, 16, 16, 16)
        principal.setSpacing(16)

        # --- lista
        coluna_lista = QVBoxLayout()
        coluna_lista.addWidget(QLabel(
            traduzir("ex_lista_admin") if self._administrador
            else traduzir("ex_lista_proprio")
        ))
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._ao_escolher)
        coluna_lista.addWidget(self.lista, 1)
        botao_novo = QPushButton(traduzir("ex_btn_novo"))
        if self._administrador:
            botao_novo.clicked.connect(self._novo)
        else:
            # Sem administrador, quem cadastra é o próprio examinador novo, na
            # tela de entrada: cria a senha dele e recebe o código dele.
            botao_novo.setToolTip(traduzir("ex_tt_novo"))
            botao_novo.clicked.connect(self._pedir_cadastro)
        coluna_lista.addWidget(botao_novo)
        principal.addLayout(coluna_lista, 2)

        # --- formulário
        painel = QWidget()
        coluna_form = QVBoxLayout(painel)
        coluna_form.setContentsMargins(0, 0, 0, 0)
        self.titulo_form = QLabel()
        coluna_form.addWidget(self.titulo_form)
        form = QFormLayout()
        form.setSpacing(10)
        self._campos: dict[str, QLineEdit] = {}
        for chave, _rotulo in perfil_service.CAMPOS:
            campo = QLineEdit()
            campo.setPlaceholderText(traduzir(f"ex_ex_{chave}"))
            self._campos[chave] = campo
            form.addRow(traduzir(f"ex_label_{chave}") + ":", campo)
        self.senha_inicial = QLineEdit()
        self.senha_inicial.setEchoMode(QLineEdit.Password)
        self.senha_inicial.setPlaceholderText(
            traduzir("ex_ph_senha_inicial", min=sessao_service.TAMANHO_MINIMO_DA_SENHA))
        self.rotulo_senha_inicial = QLabel(traduzir("ex_label_senha_inicial"))
        form.addRow(self.rotulo_senha_inicial, self.senha_inicial)
        coluna_form.addLayout(form)

        self.situacao = QLabel()
        self.situacao.setObjectName("TextoSecundario")
        coluna_form.addWidget(self.situacao)

        acoes_senha = QHBoxLayout()
        self.botao_senha = QPushButton()
        self.botao_senha.clicked.connect(self._senha)
        acoes_senha.addWidget(self.botao_senha)
        self.botao_codigo = QPushButton(traduzir("ex_btn_codigo"))
        self.botao_codigo.clicked.connect(self._novo_codigo)
        acoes_senha.addWidget(self.botao_codigo)
        self.botao_excluir = QPushButton(traduzir("ex_btn_excluir"))
        self.botao_excluir.clicked.connect(self._excluir)
        acoes_senha.addWidget(self.botao_excluir)
        acoes_senha.addStretch()
        coluna_form.addLayout(acoes_senha)

        nota = QLabel(traduzir("ex_nota"))
        nota.setWordWrap(True)
        nota.setObjectName("TextoSecundario")
        coluna_form.addWidget(nota)
        coluna_form.addStretch()

        linha = QHBoxLayout()
        linha.addStretch()
        botao_fechar = QPushButton(traduzir("ex_btn_fechar"))
        botao_fechar.clicked.connect(self.accept)
        self.botao_salvar = QPushButton(traduzir("ex_btn_salvar"))
        self.botao_salvar.setDefault(True)
        self.botao_salvar.clicked.connect(self._salvar)
        linha.addWidget(botao_fechar)
        linha.addWidget(self.botao_salvar)
        coluna_form.addLayout(linha)
        principal.addWidget(painel, 3)

        self._carregar(selecionar=sessao_service.nome())

    # ------------------------------------------------------------------
    def _carregar(self, selecionar: str = "") -> None:
        todos = {e["nome"]: e for e in sessao_service.examinadores()}
        if not self._administrador:
            todos = {n: e for n, e in todos.items() if n.lower() == sessao_service.nome().lower()}
        self._examinadores = todos
        self.lista.blockSignals(True)
        self.lista.clear()
        self.lista.addItems(list(todos))
        self.lista.blockSignals(False)
        nomes = list(todos)
        if selecionar in todos:
            self.lista.setCurrentRow(nomes.index(selecionar))
        elif nomes:
            self.lista.setCurrentRow(0)
        elif self._administrador:
            self._novo()

    def _e_eu(self, nome: str) -> bool:
        return nome.lower() == sessao_service.nome().lower()

    def _ao_escolher(self, nome: str) -> None:
        if not nome:
            return
        self._editando = nome
        dados = self._examinadores.get(nome, {})
        self.titulo_form.setText(traduzir("ex_editando", nome=nome))
        for chave, campo in self._campos.items():
            campo.setText(dados.get(chave, ""))
        self.rotulo_senha_inicial.hide()
        self.senha_inicial.hide()
        partes = []
        partes.append(traduzir("ex_tem_senha") if dados.get("tem_senha")
                      else traduzir("ex_sem_senha"))
        if dados.get("bloqueado_ate"):
            partes.append(traduzir("ex_travado", ate=dados['bloqueado_ate']))
        self.situacao.setText(traduzir("ex_situacao", valor=" · ".join(partes)))
        self.botao_senha.setVisible(True)
        self.botao_senha.setText(
            traduzir("ex_btn_trocar_minha") if self._e_eu(nome) else traduzir("ex_btn_redefinir"))
        self.botao_codigo.setVisible(self._e_eu(nome))
        self.botao_excluir.setVisible(True)
        self.botao_excluir.setText(
            traduzir("ex_btn_excluir_meu") if self._e_eu(nome) else traduzir("ex_btn_excluir"))

    def _pedir_cadastro(self) -> None:
        self.pediu_cadastro = True
        self.accept()

    def _novo(self) -> None:
        self._editando = ""
        self.lista.clearSelection()
        self.titulo_form.setText(traduzir("ex_novo_titulo"))
        for campo in self._campos.values():
            campo.clear()
        self.senha_inicial.clear()
        self.rotulo_senha_inicial.show()
        self.senha_inicial.show()
        self.situacao.setText(traduzir("ex_novo_situacao"))
        self.botao_senha.hide()
        self.botao_codigo.hide()
        self.botao_excluir.hide()
        self._campos["nome"].setFocus()

    def _salvar(self) -> None:
        dados = {chave: campo.text().strip() for chave, campo in self._campos.items()}
        try:
            if self._editando:
                sessao_service.atualizar_dados(dados, nome_anterior=self._editando)
            else:
                codigo = sessao_service.cadastrar_examinador(dados, self.senha_inicial.text())
                QMessageBox.information(
                    self, traduzir("ex_codigo_titulo"),
                    traduzir("ex_codigo_cadastro", nome=dados['nome'], codigo=codigo),
                )
        except (sessao_service.ErroDeAcesso, OSError) as erro:
            QMessageBox.warning(self, traduzir("ex_nao_gravado"), str(erro))
            return
        self._carregar(selecionar=dados["nome"])

    def _senha(self) -> None:
        nome = self._editando
        if not nome:
            return
        proprio = self._e_eu(nome)
        dialogo = _SenhaDialog(
            traduzir("ex_btn_trocar_minha") if proprio else traduzir("ex_btn_redefinir"),
            traduzir("ex_senha_texto_proprio") if proprio else
            traduzir("ex_senha_texto_outro", nome=nome),
            pedir_atual=proprio, parent=self,
        )
        if dialogo.exec() != QDialog.Accepted:
            return
        try:
            if proprio:
                sessao_service.trocar_minha_senha(dialogo.atual.text(), dialogo.nova.text())
            else:
                sessao_service.redefinir_senha(nome, dialogo.nova.text())
        except sessao_service.ErroDeAcesso as erro:
            QMessageBox.warning(self, traduzir("ex_senha_nao_alterada"), str(erro))
            return
        QMessageBox.information(self, traduzir("ex_senha_titulo"), traduzir("ex_senha_alterada"))
        self._carregar(selecionar=nome)

    def _excluir(self) -> None:
        nome = self._editando
        if not nome:
            return
        proprio = self._e_eu(nome)
        if QMessageBox.question(
            self, traduzir("ex_btn_excluir"),
            (traduzir("ex_excluir_proprio") if proprio
             else traduzir("ex_excluir_outro", nome=nome))
            + traduzir("ex_excluir_rodape"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        senha = ""
        if proprio:
            senha, confirmado = QInputDialog.getText(
                self, traduzir("ex_confirmar_senha_titulo"), traduzir("ex_confirmar_senha_corpo"),
                QLineEdit.Password,
            )
            if not confirmado:
                return
        try:
            self.excluiu_o_proprio = sessao_service.excluir_examinador(nome, senha)
        except (sessao_service.ErroDeAcesso, OSError) as erro:
            QMessageBox.warning(self, traduzir("ex_nao_excluido"), str(erro))
            return
        if self.excluiu_o_proprio:
            QMessageBox.information(self, traduzir("ex_perfil_excluido_titulo"),
                                    traduzir("ex_perfil_excluido_corpo"))
            self.accept()
            return
        self._carregar()

    def _novo_codigo(self) -> None:
        if QMessageBox.question(
            self, traduzir("ex_novo_codigo_titulo"),
            traduzir("ex_novo_codigo_corpo"),
        ) != QMessageBox.Yes:
            return
        codigo = sessao_service.novo_codigo_de_recuperacao()
        QMessageBox.information(
            self, traduzir("ex_codigo_titulo"),
            traduzir("ex_codigo_novo", codigo=codigo),
        )
