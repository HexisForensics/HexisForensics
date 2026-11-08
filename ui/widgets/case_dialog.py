"""
Diálogo de identificação do caso: abrir um caso novo, vincular a aquisição
a um caso existente ou retificar os dados de um caso.

Um caso reúne vários dispositivos. Os dados do caso são preenchidos uma
vez, na abertura; da segunda aquisição em diante o examinador só escolhe o
caso, e o que foi cadastrado é herdado.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QListWidget,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.case_service import CaseService, campos_do_caso
from .ajuste_de_tela import caber_na_tela

EXEMPLOS = {
    "referencia": "Ex.: número do processo, do contrato ou da requisição",
    "descricao": "Ex.: exame de dois telefones e um disco externo",
    "solicitante": "Ex.: quem requisitou o exame",
}


class CaseDialog(QDialog):
    """
    Diálogo modal para associar a aquisição a um caso novo ou existente, ou
    para retificar os dados de um caso (`modo_edicao`).
    """

    def __init__(
        self,
        case_service: CaseService,
        nome_plataforma: str,
        parent=None,
        modo_edicao: bool = False,
        dados_iniciais: dict | None = None,
        dispositivos: list | None = None,
    ):
        super().__init__(parent)
        self._case_service = case_service
        self.nome_plataforma = nome_plataforma
        self.modo_edicao = modo_edicao
        self.dados_iniciais = dados_iniciais or {}
        # Na retificação: rótulos dos dispositivos do caso, na ordem da lista
        # de quem chamou. `dispositivo_a_retificar` devolve o índice escolhido.
        self._dispositivos = dispositivos or []
        self._dispositivo_a_retificar: Optional[int] = None

        self.setWindowTitle("Retificar Dados do Caso" if modo_edicao else "Identificação do Caso")
        self.setModal(True)
        caber_na_tela(self, 580, 520 if (modo_edicao and dispositivos) else 380)

        self._identificador_confirmado: Optional[str] = None
        self._dados_metadados: dict = {}
        self._campos: dict[str, QLineEdit] = {}

        self._init_ui()

    def _adicionar_campos_do_caso(self, form: QFormLayout) -> None:
        for chave, rotulo in campos_do_caso():
            campo = QLineEdit(self.dados_iniciais.get(chave, ""))
            campo.setPlaceholderText(EXEMPLOS.get(chave, ""))
            self._campos[chave] = campo
            form.addRow(f"{rotulo}:", campo)

    def _init_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(12)

        if self.modo_edicao:
            widget_form = QWidget()
            form_layout = QFormLayout(widget_form)
            form_layout.setContentsMargins(12, 12, 12, 12)
            form_layout.setSpacing(10)
            self._adicionar_campos_do_caso(form_layout)
            layout_principal.addWidget(widget_form)

            aviso = QLabel(
                "A alteração vale para o caso e fica registrada como complemento, "
                "com o valor anterior. As aquisições já seladas não são tocadas."
            )
            aviso.setWordWrap(True)
            aviso.setObjectName("TextoSecundario")
            layout_principal.addWidget(aviso)

            # Os dispositivos do caso, todos, na mesma janela: retificar a
            # peça não pode depender de achar e selecionar uma linha em
            # outra lista antes.
            if self._dispositivos:
                layout_principal.addWidget(QLabel("<b>Dispositivos deste caso:</b>"))
                self.lista_dispositivos = QListWidget()
                self.lista_dispositivos.addItems(self._dispositivos)
                self.lista_dispositivos.setCurrentRow(0)
                self.lista_dispositivos.setMaximumHeight(110)
                layout_principal.addWidget(self.lista_dispositivos)
                botao_dispositivo = QPushButton("📱 Retificar dispositivo…")
                botao_dispositivo.clicked.connect(self._pedir_retificacao_do_dispositivo)
                # Numa linha própria, alinhado à esquerda e do tamanho do
                # texto: solto no layout vertical ele ocupava a janela inteira.
                linha_dispositivo = QHBoxLayout()
                linha_dispositivo.addWidget(botao_dispositivo)
                linha_dispositivo.addStretch()
                layout_principal.addLayout(linha_dispositivo)
        else:
            self.abas = QTabWidget()

            # --- ABA 1: CASO NOVO ---
            tab_novo = QWidget()
            form_novo = QFormLayout(tab_novo)
            form_novo.setContentsMargins(12, 12, 12, 12)
            form_novo.setSpacing(10)

            sugestao = self._case_service.sugerir_identificador()
            self.campo_id_novo = QLineEdit(sugestao)
            form_novo.addRow("Identificador do caso:", self.campo_id_novo)
            self._adicionar_campos_do_caso(form_novo)

            self.abas.addTab(tab_novo, "📁 Caso Novo")

            # --- ABA 2: CASO EXISTENTE ---
            tab_existente = QWidget()
            layout_existente = QVBoxLayout(tab_existente)
            layout_existente.setContentsMargins(12, 12, 12, 12)
            layout_existente.setSpacing(10)

            form_existente = QFormLayout()
            self.combo_projetos = QComboBox()
            form_existente.addRow("Caso:", self.combo_projetos)
            layout_existente.addLayout(form_existente)

            self.label_caso_existente = QLabel()
            self.label_caso_existente.setWordWrap(True)
            layout_existente.addWidget(self.label_caso_existente)
            layout_existente.addStretch()

            self._carregar_projetos_existentes()
            self.combo_projetos.currentTextChanged.connect(self._mostrar_caso_existente)

            self.abas.addTab(tab_existente, "📂 Caso Existente (mais um dispositivo)")
            layout_principal.addWidget(self.abas)

            self.label_preview = QLabel()
            self.label_preview.setObjectName("TextoSecundario")
            self.label_preview.setWordWrap(True)
            layout_principal.addWidget(self.label_preview)
            self.campo_id_novo.textChanged.connect(self._atualizar_preview)
            self._atualizar_preview(sugestao)
            self.abas.currentChanged.connect(self._ao_mudar_aba)

        linha_botoes = QHBoxLayout()
        linha_botoes.addStretch()

        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.clicked.connect(self.reject)

        self.botao_ok = QPushButton("Salvar Alterações" if self.modo_edicao else "Avançar ➔ Dispositivo")
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)

        linha_botoes.addWidget(self.botao_cancelar)
        linha_botoes.addWidget(self.botao_ok)
        layout_principal.addLayout(linha_botoes)

    def _carregar_projetos_existentes(self) -> None:
        self.combo_projetos.clear()
        casos = self._case_service.listar_casos_existentes()
        if casos:
            self.combo_projetos.addItems(casos)
            self._mostrar_caso_existente(self.combo_projetos.currentText())
        else:
            self.combo_projetos.addItem("Nenhum caso encontrado")
            self.combo_projetos.setEnabled(False)

    def _mostrar_caso_existente(self, identificador: str) -> None:
        """O que o caso escolhido já tem: é isso que a nova aquisição herda."""
        if not identificador or not self.combo_projetos.isEnabled():
            self.label_caso_existente.setText("")
            return
        dados = self._case_service.dados_do_caso(identificador)
        if not dados:
            self.label_caso_existente.setText(
                "<i>Este caso é anterior ao registro único do caso e não tem "
                "dados próprios gravados. A aquisição será vinculada a ele, com "
                "os dados do caso em branco; eles podem ser preenchidos depois, "
                "no Gerenciador de Casos.</i>"
            )
            return
        linhas = [
            f"<b>{rotulo}:</b> {dados.get(chave) or '<i>não informado</i>'}"
            for chave, rotulo in campos_do_caso()
        ]
        self.label_caso_existente.setText("<br>".join(linhas))

    def _atualizar_preview(self, texto: str) -> None:
        identificador = self._case_service.sanitizar_preview(texto.strip()) if texto.strip() else "..."
        self.label_preview.setText(
            f"Pasta da aquisição: {identificador}/{self.nome_plataforma.lower()}_<AAAAMMDD_HHMMSS>"
        )

    def _ao_mudar_aba(self, indice: int) -> None:
        if indice == 0:
            self._atualizar_preview(self.campo_id_novo.text())
        else:
            self.label_preview.setText(
                "O novo dispositivo entra como mais uma aquisição do caso escolhido."
            )

    def _pedir_retificacao_do_dispositivo(self) -> None:
        """Fecha esta janela pedindo a retificação da peça escolhida."""
        linha = self.lista_dispositivos.currentRow()
        if linha < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um dispositivo na lista.")
            return
        self._dispositivo_a_retificar = linha
        self._dados_metadados = dict(self._valores_dos_campos(), tipo="edicao")
        self.accept()

    def dispositivo_a_retificar(self) -> Optional[int]:
        """Índice do dispositivo cuja retificação foi pedida, ou `None`."""
        return self._dispositivo_a_retificar

    def _valores_dos_campos(self) -> dict:
        return {chave: campo.text().strip() for chave, campo in self._campos.items()}

    def _confirmar(self) -> None:
        if self.modo_edicao:
            self._dados_metadados = dict(self._valores_dos_campos(), tipo="edicao")
            self.accept()
            return

        if self.abas.currentIndex() == 0:
            valor = self.campo_id_novo.text().strip()
            if not valor:
                QMessageBox.warning(self, "Aviso", "Informe um identificador de caso válido.")
                return
            if self._case_service.pasta_do_caso(valor).exists():
                QMessageBox.warning(
                    self,
                    "Caso já existe",
                    f"Já existe um caso '{valor}'. Para acrescentar um dispositivo a "
                    "ele, use a aba 'Caso Existente'.",
                )
                return
            self._identificador_confirmado = valor
            self._dados_metadados = dict(self._valores_dos_campos(), tipo="novo")
            self.accept()
            return

        selecionado = self.combo_projetos.currentText().strip()
        if not selecionado or not self.combo_projetos.isEnabled():
            QMessageBox.warning(self, "Aviso", "Selecione um caso existente válido.")
            return
        self._identificador_confirmado = selecionado
        self._dados_metadados = {"tipo": "existente"}
        self.accept()

    def identificador_caso(self) -> Optional[str]:
        return self._identificador_confirmado

    def dados_metadados(self) -> dict:
        return self._dados_metadados
