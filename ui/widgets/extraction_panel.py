"""
Painel de seleção dos tipos de extração disponíveis para a plataforma
corrente. Construído dinamicamente a partir da lista de classes de
extratores fornecida por `services.extraction_service.listar_extratores()`,
então adicionar um novo tipo de extração no futuro (ex.: Telegram) não
exige tocar na UI — basta registrar a nova classe (`@registrar_extrator`)
em `core/android/extractors/` ou `core/ios/extractors/`.

Cada linha tem, além do checkbox, uma coluna de status (Pendente / Em
execução / Sucesso / Parcial / Falha) — atualizada pela `MainWindow` a
partir dos sinais `extrator_iniciado`/`extrator_concluido` de
`ExtractionService`. As cores (verde/âmbar/vermelho) são semânticas, não
de marca — mesmo padrão usado em `device_panel.py` — para continuarem
reconhecíveis em qualquer identidade visual.

Nota sobre a única importação de `core` neste arquivo: `BaseExtractor` é
usado apenas como *tipo* (contrato de dados: id, nome_exibicao, descricao,
ordem), nunca para executar lógica de negócio — é a exceção aceita à
regra "UI não importa core", pois duplicar esse contrato como um DTO à
parte só agregaria complexidade sem benefício real.
"""

from __future__ import annotations

from typing import Dict, List, Type

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.base_extractor import BaseExtractor

from services.extraction_service import indica_ressalva

from ..style import (
    COR_EM_EXECUCAO,
    COR_FALHA,
    COR_PARCIAL,
    COR_PENDENTE,
    COR_SUCESSO,
)

LARGURA_COLUNA_STATUS = 150

TEXTO_PENDENTE = "· Pendente"
TEXTO_EM_EXECUCAO = "⏳ Em execução..."


class ExtractionPanel(QGroupBox):
    def __init__(
        self,
        extratores: List[Type[BaseExtractor]],
        titulo: str = "Tipos de Extração",
        parent=None,
    ):
        super().__init__(titulo, parent)
        self._extratores = extratores
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._status_labels: Dict[str, QLabel] = {}

        layout_externo = QVBoxLayout(self)

        area_rolagem = QScrollArea()
        area_rolagem.setWidgetResizable(True)
        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)

        for classe_extrator in extratores:
            rotulo = classe_extrator.nome_exibicao
            if getattr(classe_extrator, "requer_privilegio_root", False):
                rotulo += f"  [{getattr(classe_extrator, 'rotulo_privilegio', 'requer root')}]"

            expressa = getattr(classe_extrator, "selecao_expressa", False)
            if expressa:
                rotulo += "  [altera o dispositivo — seleção expressa]"

            checkbox = QCheckBox(rotulo)
            checkbox.setToolTip(classe_extrator.descricao)
            # Módulos que exigem root/jailbreak começam desmarcados, já que
            # tipicamente falham silenciosamente em aparelhos comuns. Os de
            # seleção expressa também: só rodam por escolha deliberada.
            checkbox.setChecked(
                not getattr(classe_extrator, "requer_privilegio_root", False) and not expressa
            )

            label_status = QLabel(TEXTO_PENDENTE)
            label_status.setFixedWidth(LARGURA_COLUNA_STATUS)
            label_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label_status.setStyleSheet(f"color: {COR_PENDENTE};")

            linha = QHBoxLayout()
            linha.addWidget(checkbox, stretch=1)
            linha.addWidget(label_status)
            layout_conteudo.addLayout(linha)

            self._checkboxes[classe_extrator.id] = checkbox
            self._status_labels[classe_extrator.id] = label_status
            checkbox.toggled.connect(self._atualizar_resumo)

        layout_conteudo.addStretch()
        conteudo.setLayout(layout_conteudo)
        area_rolagem.setWidget(conteudo)
        layout_externo.addWidget(area_rolagem)

        # A lista tem rolagem, e módulos marcados abaixo da área visível
        # passavam despercebidos: numa extração real, quatro deles (entre
        # eles o Dump do Sistema de Arquivos) rodaram sem que o examinador
        # soubesse que estavam marcados. O resumo fica sempre à vista.
        self.rotulo_resumo = QLabel()
        self.rotulo_resumo.setWordWrap(True)
        layout_externo.addWidget(self.rotulo_resumo)

        linha_acoes = QHBoxLayout()
        self.botao_marcar_todos = QPushButton("Marcar todos")
        self.botao_desmarcar_todos = QPushButton("Desmarcar todos")
        self.botao_marcar_todos.clicked.connect(lambda: self._marcar_todos(True))
        self.botao_desmarcar_todos.clicked.connect(lambda: self._marcar_todos(False))
        linha_acoes.addWidget(self.botao_marcar_todos)
        linha_acoes.addWidget(self.botao_desmarcar_todos)
        layout_externo.addLayout(linha_acoes)
        self._atualizar_resumo()

    def _atualizar_resumo(self, *_args) -> None:
        marcados = [
            classe.nome_exibicao for classe in self._extratores
            if self._checkboxes[classe.id].isChecked()
        ]
        if not marcados:
            self.rotulo_resumo.setText("<b>Nenhum módulo marcado.</b>")
            return
        self.rotulo_resumo.setText(
            f"<b>{len(marcados)} de {len(self._extratores)} módulos marcados:</b> "
            + " · ".join(marcados)
        )

    def _marcar_todos(self, marcado: bool) -> None:
        expressos = {
            classe.id for classe in self._extratores
            if getattr(classe, "selecao_expressa", False)
        }
        for identificador, checkbox in self._checkboxes.items():
            # "Marcar todos" não marca o que exige escolha expressa;
            # "Desmarcar todos" desmarca tudo, inclusive eles.
            if marcado and identificador in expressos:
                continue
            checkbox.setChecked(marcado)

    def extratores_selecionados(self) -> List[Type[BaseExtractor]]:
        return [
            classe
            for classe in self._extratores
            if self._checkboxes[classe.id].isChecked()
        ]

    # ------------------------------------------------------------------
    # Coluna de status — atualizada pela MainWindow durante a execução
    # ------------------------------------------------------------------
    def resetar_status(self) -> None:
        """Volta todas as linhas para 'Pendente' — chamado ao iniciar uma nova extração."""
        for label in self._status_labels.values():
            label.setText(TEXTO_PENDENTE)
            label.setStyleSheet(f"color: {COR_PENDENTE};")
            label.setToolTip("")

    def marcar_em_execucao(self, id_extrator: str) -> None:
        label = self._status_labels.get(id_extrator)
        if label is None:
            return
        label.setText(TEXTO_EM_EXECUCAO)
        label.setStyleSheet(f"color: {COR_EM_EXECUCAO}; font-weight: 600;")

    def marcar_concluido(
        self, id_extrator: str, sucesso: bool, mensagem: str, detalhes: dict
    ) -> None:
        """
        Reflete o resultado final de um módulo na coluna de status.

        Três estados possíveis, não só sucesso/falha: um módulo pode
        retornar `sucesso=True` e ainda assim ter tido uma ressalva real
        (ver `services.extraction_service.CHAVES_RESSALVA` — ex.:
        `acesso_negado` nos extratores de SMS/Call Log, que preservam a
        tentativa como evidência mesmo quando o provider nega acesso, ou
        `arquivos_pulados_nuvem` na Cópia Lógica de Computador) — esse
        caso aparece como "Parcial", não como sucesso pleno, para não
        esconder o problema do examinador.
        """
        label = self._status_labels.get(id_extrator)
        if label is None:
            return

        if not sucesso:
            cor, texto = COR_FALHA, "✖ Falha"
        elif indica_ressalva(detalhes):
            cor, texto = COR_PARCIAL, "⚠ Parcial"
        else:
            cor, texto = COR_SUCESSO, "✔ Sucesso"

        label.setText(texto)
        label.setStyleSheet(f"color: {cor}; font-weight: 600;")
        label.setToolTip(mensagem)
