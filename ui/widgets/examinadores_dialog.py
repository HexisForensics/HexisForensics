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
from .ajuste_de_tela import caber_na_tela

EXEMPLOS = {
    "nome": "Como deve constar nos relatórios e laudos",
    "registro_funcional": "Ex.: registro em conselho, matrícula, certificação",
    "unidade": "Ex.: nome do laboratório ou da empresa",
    "email": "Opcional",
}


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
            form.addRow("Senha atual", self.atual)
        form.addRow(f"Nova senha (mín. {sessao_service.TAMANHO_MINIMO_DA_SENHA})", self.nova)
        form.addRow("Repita a nova senha", self.repetir)
        layout.addLayout(form)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._ok)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _ok(self) -> None:
        if self.nova.text() != self.repetir.text():
            QMessageBox.warning(self, "Senha", "As senhas não conferem.")
            return
        self.accept()


class ExaminadoresDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Examinadores")
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
            "<b>Examinadores cadastrados neste computador</b>" if self._administrador
            else "<b>Seus dados</b>"
        ))
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._ao_escolher)
        coluna_lista.addWidget(self.lista, 1)
        botao_novo = QPushButton("➕ Novo examinador")
        if self._administrador:
            botao_novo.clicked.connect(self._novo)
        else:
            # Sem administrador, quem cadastra é o próprio examinador novo, na
            # tela de entrada: cria a senha dele e recebe o código dele.
            botao_novo.setToolTip("Abre o cadastro: o novo examinador cria a própria senha "
                                  "e passa a ser o examinador da sessão.")
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
        for chave, rotulo in perfil_service.CAMPOS:
            campo = QLineEdit()
            campo.setPlaceholderText(EXEMPLOS.get(chave, ""))
            self._campos[chave] = campo
            form.addRow(f"{rotulo}:", campo)
        self.senha_inicial = QLineEdit()
        self.senha_inicial.setEchoMode(QLineEdit.Password)
        self.senha_inicial.setPlaceholderText(
            f"mínimo {sessao_service.TAMANHO_MINIMO_DA_SENHA} caracteres")
        self.rotulo_senha_inicial = QLabel("Senha inicial:")
        form.addRow(self.rotulo_senha_inicial, self.senha_inicial)
        coluna_form.addLayout(form)

        self.situacao = QLabel()
        self.situacao.setObjectName("TextoSecundario")
        coluna_form.addWidget(self.situacao)

        acoes_senha = QHBoxLayout()
        self.botao_senha = QPushButton()
        self.botao_senha.clicked.connect(self._senha)
        acoes_senha.addWidget(self.botao_senha)
        self.botao_codigo = QPushButton("Novo código de recuperação")
        self.botao_codigo.clicked.connect(self._novo_codigo)
        acoes_senha.addWidget(self.botao_codigo)
        self.botao_excluir = QPushButton("Excluir examinador")
        self.botao_excluir.clicked.connect(self._excluir)
        acoes_senha.addWidget(self.botao_excluir)
        acoes_senha.addStretch()
        coluna_form.addLayout(acoes_senha)

        nota = QLabel(
            "Os dados entram em cada aquisição, sob o selo. Editar um examinador não "
            "altera as aquisições que ele já fez."
        )
        nota.setWordWrap(True)
        nota.setObjectName("TextoSecundario")
        coluna_form.addWidget(nota)
        coluna_form.addStretch()

        linha = QHBoxLayout()
        linha.addStretch()
        botao_fechar = QPushButton("Fechar")
        botao_fechar.clicked.connect(self.accept)
        self.botao_salvar = QPushButton("Salvar")
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
        self.titulo_form.setText(f"<b>Editando:</b> {nome}")
        for chave, campo in self._campos.items():
            campo.setText(dados.get(chave, ""))
        self.rotulo_senha_inicial.hide()
        self.senha_inicial.hide()
        partes = []
        partes.append("tem senha" if dados.get("tem_senha") else "ainda sem senha (cria no primeiro acesso)")
        if dados.get("bloqueado_ate"):
            partes.append(f"travado por senhas erradas até {dados['bloqueado_ate']}")
        self.situacao.setText("Situação: " + " · ".join(partes))
        self.botao_senha.setVisible(True)
        self.botao_senha.setText("Trocar minha senha" if self._e_eu(nome) else "Redefinir senha")
        self.botao_codigo.setVisible(self._e_eu(nome))
        self.botao_excluir.setVisible(True)
        self.botao_excluir.setText("Excluir meu perfil" if self._e_eu(nome) else "Excluir examinador")

    def _pedir_cadastro(self) -> None:
        self.pediu_cadastro = True
        self.accept()

    def _novo(self) -> None:
        self._editando = ""
        self.lista.clearSelection()
        self.titulo_form.setText("<b>Novo examinador</b>")
        for campo in self._campos.values():
            campo.clear()
        self.senha_inicial.clear()
        self.rotulo_senha_inicial.show()
        self.senha_inicial.show()
        self.situacao.setText("O novo examinador entra com a senha inicial e pode trocá-la depois.")
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
                    self, "Código de recuperação",
                    f"Código de recuperação de {dados['nome']}:\n\n    {codigo}\n\n"
                    "Entregue-o ao examinador. Ele não será mostrado de novo.",
                )
        except (sessao_service.ErroDeAcesso, OSError) as erro:
            QMessageBox.warning(self, "Não gravado", str(erro))
            return
        self._carregar(selecionar=dados["nome"])

    def _senha(self) -> None:
        nome = self._editando
        if not nome:
            return
        proprio = self._e_eu(nome)
        dialogo = _SenhaDialog(
            "Trocar minha senha" if proprio else "Redefinir senha",
            "Escolha a nova senha." if proprio else
            f"Nova senha para <b>{nome}</b>. Informe-a a ele; a redefinição fica registrada "
            "no registro de acessos da estação.",
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
            QMessageBox.warning(self, "Senha não alterada", str(erro))
            return
        QMessageBox.information(self, "Senha", "Senha alterada.")
        self._carregar(selecionar=nome)

    def _excluir(self) -> None:
        nome = self._editando
        if not nome:
            return
        proprio = self._e_eu(nome)
        if QMessageBox.question(
            self, "Excluir examinador",
            ("Excluir o SEU perfil desta estação? Você sai da sessão e não poderá entrar "
             "de novo com ele." if proprio else f"Excluir o perfil de {nome} desta estação?")
            + "\n\nAs aquisições já feitas NÃO mudam: o nome de quem as fez está gravado "
            "sob o selo de cada uma.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        senha = ""
        if proprio:
            senha, confirmado = QInputDialog.getText(
                self, "Confirmar com a senha", "Digite a sua senha para excluir o perfil:",
                QLineEdit.Password,
            )
            if not confirmado:
                return
        try:
            self.excluiu_o_proprio = sessao_service.excluir_examinador(nome, senha)
        except (sessao_service.ErroDeAcesso, OSError) as erro:
            QMessageBox.warning(self, "Não excluído", str(erro))
            return
        if self.excluiu_o_proprio:
            QMessageBox.information(self, "Perfil excluído",
                                    "Seu perfil foi excluído. A sessão foi encerrada.")
            self.accept()
            return
        self._carregar()

    def _novo_codigo(self) -> None:
        if QMessageBox.question(
            self, "Novo código de recuperação",
            "Gerar um código novo? O código atual deixa de valer.",
        ) != QMessageBox.Yes:
            return
        codigo = sessao_service.novo_codigo_de_recuperacao()
        QMessageBox.information(
            self, "Código de recuperação",
            f"Seu novo código de recuperação:\n\n    {codigo}\n\n"
            "Anote ou imprima e guarde em local seguro. Ele não será mostrado de novo.",
        )
