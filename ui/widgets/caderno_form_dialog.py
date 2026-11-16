"""
Formulário do que o examinador declara para o Laudo Pericial e para o
Caderno de Extração.

Reúne o que a aquisição não sabe de si: o objetivo do exame, a modalidade
de acesso, as respostas aos protocolos periciais e as considerações de
quem assina. O que a ferramenta já registrou durante a coleta não é
perguntado aqui — pedir confirmação de fato que o sistema conhece abriria
porta para a resposta divergir da evidência gravada ao lado. Pelo mesmo
motivo os dados do caso e da peça aparecem somente para leitura: a fonte
deles é o cadastro, e retificá-los é ato próprio, que deixa registro.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.caderno_service import modalidade_sugerida
from services.laudo_service import (
    perguntas_dos_protocolos,
    protocolo_exige_especificacao as exige_especificacao,
)
from .ajuste_de_tela import caber_na_tela
from services.idioma import traduzir

LAUDO = "laudo"
CADERNO = "caderno"

ROTULOS_DA_PECA = ("Equipamento", "Cor", "Estado", "Lacre")
ROTULOS_DE_CONTROLE = ("Tipo Projeto", "Fotos Anexas")


class CadernoFormDialog(QDialog):
    """
    Colhe as declarações do examinador. `finalidade` muda só o título, o
    botão e os campos que são próprios do laudo (número, objetivo e
    considerações).
    """

    def __init__(
        self,
        dados_caso: dict,
        dados_disp: dict,
        pasta_aquisicao=None,
        parent=None,
        finalidade: str = CADERNO,
    ):
        super().__init__(parent)
        self.dados_caso = dados_caso
        self.dados_disp = dados_disp
        self.pasta_aquisicao = pasta_aquisicao
        self.finalidade = finalidade

        self.setWindowTitle(
            traduzir("cf_titulo_laudo") if finalidade == LAUDO
            else traduzir("cf_titulo_caderno")
        )
        self.setModal(True)
        caber_na_tela(self, 680, 780)

        self._init_ui()

    def _init_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        form_layout = QVBoxLayout(content_widget)

        # --- SEÇÃO 1: IDENTIFICAÇÃO (somente leitura) ---
        grupo_id = QGroupBox(traduzir("cf_grupo_id"))
        layout_id = QFormLayout(grupo_id)
        for rotulo, valor in self.dados_caso.items():
            if rotulo in ROTULOS_DA_PECA or rotulo in ROTULOS_DE_CONTROLE:
                continue
            layout_id.addRow(f"{rotulo}:", QLabel(valor or traduzir("cf_nao_informado")))
        for rotulo in ROTULOS_DA_PECA:
            layout_id.addRow(f"{rotulo}:", QLabel(self.dados_disp.get(rotulo) or traduzir("cf_nao_informado")))
        form_layout.addWidget(grupo_id)

        # --- SEÇÃO 2: O QUE É PRÓPRIO DO LAUDO ---
        self.campo_numero = QLineEdit()
        self.campo_numero.setPlaceholderText(traduzir("cf_ph_numero"))
        self.campo_objetivo = QTextEdit()
        self.campo_objetivo.setPlaceholderText(traduzir("cf_ph_objetivo"))
        self.campo_objetivo.setMaximumHeight(90)
        if self.finalidade == LAUDO:
            grupo_laudo = QGroupBox(traduzir("cf_grupo_laudo"))
            layout_laudo = QFormLayout(grupo_laudo)
            layout_laudo.addRow(traduzir("cf_label_numero"), self.campo_numero)
            layout_laudo.addRow(traduzir("cf_label_objetivo"), self.campo_objetivo)
            form_layout.addWidget(grupo_laudo)

        # --- SEÇÃO 3: MODALIDADE DE ACESSO ---
        # A sugestão vem dos módulos que a aquisição registrou ter
        # executado. Um campo com constante fixa sob o rótulo
        # "pré-detectado" já fez um documento descrever imagem bit-a-bit
        # como backup lógico via ADB.
        grupo_metodo = QGroupBox(traduzir("cf_grupo_metodo"))
        layout_metodo = QFormLayout(grupo_metodo)

        sugestao = (
            modalidade_sugerida(self.pasta_aquisicao) if self.pasta_aquisicao else ""
        )
        self.campo_tipo_extracao = QLineEdit(sugestao)
        if sugestao:
            aviso_modalidade = traduzir("cf_aviso_modalidade_sugerido")
        else:
            # Sem registro, o campo fica VAZIO. Oferecer um palpite plausível
            # é o defeito que este bloco corrige.
            self.campo_tipo_extracao.setPlaceholderText(traduzir("cf_ph_modalidade"))
            aviso_modalidade = traduzir("cf_aviso_modalidade_vazio")
        layout_metodo.addRow(traduzir("cf_label_modalidade"), self.campo_tipo_extracao)
        rotulo_modalidade = QLabel(f"<i>{aviso_modalidade}</i>")
        rotulo_modalidade.setWordWrap(True)
        layout_metodo.addRow(rotulo_modalidade)
        form_layout.addWidget(grupo_metodo)

        # --- SEÇÃO 4: PROTOCOLOS ---
        grupo_check = QGroupBox(traduzir("cf_grupo_protocolos"))
        layout_check = QVBoxLayout(grupo_check)

        self.grupos_botoes = []
        self.campos_observacao = []
        # Só o que depende de quem periciou. O que a ferramenta comprova
        # sozinha — alterações registradas, relógio aferido, cadeia de
        # custódia, selo de integridade — ela responde no documento, com o
        # arquivo que sustenta cada resposta.
        self.perguntas_com_clausula = perguntas_dos_protocolos()
        self.perguntas = [pergunta for _, pergunta in self.perguntas_com_clausula]

        aviso = QLabel(traduzir("cf_aviso_protocolos"))
        aviso.setWordWrap(True)
        layout_check.addWidget(aviso)

        for clausula, p in self.perguntas_com_clausula:
            lbl = QLabel(traduzir("cf_item", clausula=clausula, pergunta=p))
            lbl.setWordWrap(True)
            layout_check.addWidget(lbl)

            linha_radio = QHBoxLayout()
            bg = QButtonGroup(self)

            # NENHUMA opção vem marcada. Pré-selecionar "Sim" fazia o
            # documento afirmar o que ninguém confirmou — e o examinador
            # que apenas clicasse em Gerar assinava tudo.
            for indice, texto in enumerate(
                    (traduzir("cf_sim"), traduzir("cf_nao"), traduzir("cf_nao_aplica"))):
                botao = QRadioButton(texto)
                bg.addButton(botao, indice)
                linha_radio.addWidget(botao)

            # Observação do próprio item, ao lado da resposta: a pergunta
            # que pede "Especificar" só fica completa aqui.
            campo_obs = QLineEdit()
            campo_obs.setPlaceholderText(
                traduzir("cf_ph_especificar") if exige_especificacao(p)
                else traduzir("cf_ph_observacao")
            )
            linha_radio.addWidget(campo_obs, 1)

            layout_check.addLayout(linha_radio)
            self.grupos_botoes.append(bg)
            self.campos_observacao.append(campo_obs)

        layout_check.addWidget(QLabel(traduzir("cf_label_observacoes")))
        self.campo_observacoes = QTextEdit()
        self.campo_observacoes.setMaximumHeight(70)
        layout_check.addWidget(self.campo_observacoes)
        form_layout.addWidget(grupo_check)

        # --- SEÇÃO 5: CONSIDERAÇÕES (laudo) ---
        self.campo_consideracoes = QTextEdit()
        self.campo_consideracoes.setMaximumHeight(110)
        self.campo_consideracoes.setPlaceholderText(traduzir("cf_ph_consideracoes"))
        if self.finalidade == LAUDO:
            grupo_conclusao = QGroupBox(traduzir("cf_grupo_consideracoes"))
            layout_conclusao = QVBoxLayout(grupo_conclusao)
            nota = QLabel(traduzir("cf_nota_consideracoes"))
            nota.setWordWrap(True)
            layout_conclusao.addWidget(nota)
            layout_conclusao.addWidget(self.campo_consideracoes)
            form_layout.addWidget(grupo_conclusao)

        # --- FOTOS E INTEGRIDADE: só informam ---
        grupo_fotos = QGroupBox(traduzir("cf_grupo_fotos"))
        layout_fotos = QVBoxLayout(grupo_fotos)
        fotos = self.dados_disp.get("fotos", [])
        texto_fotos = (
            ", ".join(Path(f).name for f in fotos) if fotos else traduzir("cf_sem_fotos")
        )
        rotulo_fotos = QLabel(traduzir("cf_rotulo_fotos", fotos=texto_fotos))
        rotulo_fotos.setWordWrap(True)
        layout_fotos.addWidget(rotulo_fotos)
        form_layout.addWidget(grupo_fotos)

        scroll.setWidget(content_widget)
        layout_principal.addWidget(scroll)

        linha_botoes = QHBoxLayout()
        linha_botoes.addStretch()

        btn_cancelar = QPushButton(traduzir("cf_btn_cancelar"))
        btn_cancelar.clicked.connect(self.reject)

        btn_gerar = QPushButton(
            traduzir("cf_btn_gerar_laudo") if self.finalidade == LAUDO
            else traduzir("cf_btn_gerar_caderno")
        )
        btn_gerar.setDefault(True)
        btn_gerar.clicked.connect(self.accept)

        linha_botoes.addWidget(btn_cancelar)
        linha_botoes.addWidget(btn_gerar)
        layout_principal.addLayout(linha_botoes)

    def obter_protocolos(self) -> list:
        """
        (cláusula, pergunta, resposta, observação) dos protocolos periciais.

        Item não respondido vira "Não respondido", e não "Sim". O documento
        precisa poder dizer que a diretriz não foi avaliada — presumir a
        resposta é a ferramenta afirmando o que ninguém verificou.
        """
        opcoes = ["Sim", "Não", "Não se aplica"]
        protocolos = []
        for (clausula, pergunta), grupo, campo in zip(
            self.perguntas_com_clausula, self.grupos_botoes, self.campos_observacao
        ):
            escolhido = grupo.checkedId()
            resposta = opcoes[escolhido] if escolhido != -1 else "Não respondido"
            protocolos.append((clausula, pergunta, resposta, campo.text().strip()))
        return protocolos

    def dados_atualizados_formulario(self) -> dict:
        return {
            "numero": self.campo_numero.text().strip(),
            "objetivo": self.campo_objetivo.toPlainText().strip(),
            "modelo": self.dados_disp.get("Equipamento", ""),
            "lacre": self.dados_disp.get("Lacre", ""),
            "tipo_extracao": self.campo_tipo_extracao.text().strip(),
            "protocolos": self.obter_protocolos(),
            "observacoes": self.campo_observacoes.toPlainText().strip(),
            "consideracoes": self.campo_consideracoes.toPlainText().strip(),
        }
