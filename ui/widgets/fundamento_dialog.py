"""
Diálogo da autorização de acesso aos dados.

A tela faz uma coisa só: anexar ao caso o documento que ampara a extração —
a decisão judicial, o termo em que o titular consente com o exame, ou a
requisição do serviço.

Ela não pergunta a qualificação de ninguém, nem a data do documento, nem em
que peça o consentimento consta. Nada disso a ferramenta verifica, e tudo
isso já está no documento original. Redigitar aqui produziria uma segunda
via de dados que deveriam ser idênticos — e duas vias divergem.

A autorização pertence ao **caso**: um mesmo documento costuma cobrir todos
os dispositivos do exame. Por isso a tela mostra o que o caso já tem e, da
segunda aquisição em diante, normalmente não há nada a anexar.

Anexar não é obrigatório para prosseguir — a autorização existe
independentemente de o PDF estar aqui. Mas prosseguir sem anexar avisa uma
vez, e o caso passa a declarar a ausência por extenso.

Usa `services.case_service` para as opções — não importa nada de `core`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.case_service import opcoes_tipo_documento
from .ajuste_de_tela import caber_na_tela


class AutorizacaoDialog(QDialog):
    """Passo 2: qual documento ampara o acesso aos dados deste aparelho."""

    def __init__(self, documentos_do_caso: Optional[list] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Autorização de Acesso aos Dados")
        self.setModal(True)
        caber_na_tela(self, 640, 520)

        self._documentos_do_caso = documentos_do_caso or []
        self._pendentes: list = []

        principal = QVBoxLayout(self)
        if self._documentos_do_caso:
            principal.addWidget(self._montar_ja_anexados())
        principal.addWidget(self._montar_anexar(), 1)
        principal.addWidget(self._montar_alcance())
        principal.addLayout(self._montar_botoes())

    # ------------------------------------------------------------------
    def _montar_ja_anexados(self) -> QGroupBox:
        """
        O que o caso já tem. Só aparece da segunda aquisição em diante.

        Existe para o examinador não reanexar o mesmo PDF: o documento já
        anexado cobre este dispositivo tanto quanto cobria o anterior.
        """
        caixa = QGroupBox("Já anexado a este caso — vale também para este dispositivo")
        layout = QVBoxLayout(caixa)

        lista = QListWidget()
        lista.setMaximumHeight(90)
        for documento in self._documentos_do_caso:
            lista.addItem(f"{documento['rotulo']}  —  {documento['nome']}")
        lista.setEnabled(False)
        layout.addWidget(lista)
        return caixa

    def _montar_anexar(self) -> QGroupBox:
        caixa = QGroupBox("Anexar documento de autorização")
        layout = QVBoxLayout(caixa)

        linha = QHBoxLayout()
        self.combo_tipo = QComboBox()
        for chave, rotulo in opcoes_tipo_documento():
            self.combo_tipo.addItem(rotulo, chave)

        self.campo_descricao = QLineEdit()
        self.campo_descricao.setPlaceholderText("Descrição (opcional) — ex.: aditamento")

        botao_anexar = QPushButton("Escolher arquivo...")
        botao_anexar.clicked.connect(self._escolher_arquivo)

        linha.addWidget(QLabel("Tipo:"))
        linha.addWidget(self.combo_tipo)
        linha.addWidget(self.campo_descricao, 1)
        linha.addWidget(botao_anexar)
        layout.addLayout(linha)

        self.lista_pendentes = QListWidget()
        layout.addWidget(self.lista_pendentes, 1)

        botao_remover = QPushButton("Remover selecionado")
        botao_remover.clicked.connect(self._remover_selecionado)
        layout.addWidget(botao_remover)

        layout.addWidget(
            QLabel(
                "<i>Pode-se anexar mais de um documento — a autorização e um aditamento, "
                "por exemplo. Cada um recebe seu próprio SHA-256.</i>"
            )
        )
        return caixa

    def _montar_alcance(self) -> QLabel:
        """
        O que a ferramenta afirma sobre o que foi anexado — e o que não.

        Fica na tela, e não só no arquivo gravado, porque é aqui que o
        examinador forma a expectativa do que o sistema está atestando.
        """
        rotulo = QLabel(
            "<b>O que este anexo registra:</b> que o arquivo, com o hash calculado "
            "aqui, estava anexado ao caso no momento desta aquisição.<br>"
            "<b>O que ele não registra:</b> autenticidade, assinatura, competência "
            "ou as datas constantes do documento — isso se apura na origem do documento, onde o "
            "original tramita."
        )
        rotulo.setWordWrap(True)
        return rotulo

    def _montar_botoes(self) -> QHBoxLayout:
        botoes = QHBoxLayout()
        self.botao_ok = QPushButton("Confirmar e Prosseguir")
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)
        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)
        botoes.addStretch()
        botoes.addWidget(self.botao_ok)
        botoes.addWidget(botao_cancelar)
        return botoes

    # ------------------------------------------------------------------
    def _escolher_arquivo(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o documento de autorização",
            "",
            "Documentos (*.pdf *.jpg *.jpeg *.png);;Todos os arquivos (*)",
        )
        if not caminho:
            return

        arquivo = Path(caminho)
        if any(Path(item["arquivo"]) == arquivo for item in self._pendentes):
            QMessageBox.information(
                self, "Já na lista", "Este arquivo já foi escolhido para anexar."
            )
            return

        documento = {
            "tipo": self.combo_tipo.currentData(),
            "arquivo": str(arquivo),
            "descricao": self.campo_descricao.text().strip(),
        }
        self._pendentes.append(documento)

        rotulo = self.combo_tipo.currentText()
        if documento["descricao"]:
            rotulo = f"{rotulo} — {documento['descricao']}"
        self.lista_pendentes.addItem(f"{rotulo}  —  {arquivo.name}")
        self.campo_descricao.clear()

    def _remover_selecionado(self) -> None:
        linha = self.lista_pendentes.currentRow()
        if linha < 0:
            return
        self.lista_pendentes.takeItem(linha)
        del self._pendentes[linha]

    # ------------------------------------------------------------------
    def _confirmar(self) -> None:
        """
        Prosseguir sem anexar é permitido, mas nunca silencioso.

        A autorização existe independentemente de o PDF estar
        aqui — bloquear a extração por isso seria a ferramenta arbitrando o
        que não lhe cabe. Mas seguir sem aviso deixaria o examinador supor
        que anexou quando não anexou.
        """
        if not self._pendentes and not self._documentos_do_caso:
            resposta = QMessageBox.question(
                self,
                "Prosseguir sem documento anexado?",
                "Nenhum documento de autorização foi anexado a este caso.\n\n"
                "A extração pode prosseguir — a autorização existe independentemente "
                "de o documento estar aqui —, mas o caso vai registrar por "
                "extenso que nada foi anexado, e o documento poderá ser juntado "
                "depois pelo gerenciador de casos.\n\n"
                "Prosseguir assim mesmo?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resposta != QMessageBox.Yes:
                return
        self.accept()

    def documentos(self) -> list:
        """Documentos escolhidos agora, em campos simples, para o serviço."""
        return list(self._pendentes)
