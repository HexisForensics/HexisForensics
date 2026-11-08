"""
Diálogo do método: o que os módulos escolhidos não alcançam.

Aparece depois da seleção dos módulos e antes de qualquer coisa ser criada
em disco — o único momento em que a informação ainda serve para decidir.
Depois da coleta ela vira registro; antes, ela é escolha.

Existe porque o conhecimento sobre os limites de cada módulo vivia em
docstring, invisível para quem opera. O examinador que rodasse o módulo de
WhatsApp recebia mídias e backups criptografados sem que nada na tela
dissesse que as mensagens em si não vieram, e por quê. Quem vê "concluído"
e uma pasta cheia de arquivos conclui que examinou o aplicativo.

Duas seções, separadas de propósito:

- **O que não será alcançado** — limite do método, vale seja qual for o
  aparelho. É o que impede ler ausência de dado como ausência de fato.
- **O que pode ser alterado no aparelho** — vem sempre com a justificativa,
  porque declarar que a ferramenta mexe no alvo sem dizer por que é pior do
  que não declarar. E é "pode": a alteração que de fato ocorrer é anotada no
  registro do procedimento, no momento em que ocorrer.

Usa `services.extraction_service` para descrever os módulos — não importa
nada de `core`.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from .ajuste_de_tela import caber_na_tela


class MetodoDialog(QDialog):
    """Passo 1: o alcance declarado dos módulos escolhidos."""

    def __init__(self, modulos: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Método e Limitações da Coleta")
        self.setModal(True)
        caber_na_tela(self, 680, 560)

        self._modulos = modulos or []

        principal = QVBoxLayout(self)
        principal.addWidget(self._montar_cabecalho())

        conteudo = QWidget()
        layout = QVBoxLayout(conteudo)
        layout.addWidget(self._montar_limitacoes(), 1)

        alteracoes = self._montar_alteracoes()
        if alteracoes is not None:
            layout.addWidget(alteracoes)

        rolagem = QScrollArea()
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        principal.addWidget(rolagem, 1)

        principal.addLayout(self._montar_botoes())

    # ------------------------------------------------------------------
    def _montar_cabecalho(self) -> QLabel:
        nomes = ", ".join(modulo["nome"] for modulo in self._modulos) or "(nenhum)"
        perfis = []
        for modulo in self._modulos:
            if modulo.get("perfil") and modulo["perfil"] not in perfis:
                perfis.append(modulo["perfil"])

        texto = (
            f"<b>{len(self._modulos)} módulo(s) selecionado(s):</b> {nomes}"
        )
        if perfis:
            texto += f"<br><b>Competência exigida:</b> {'; '.join(perfis)}"

        rotulo = QLabel(texto)
        rotulo.setWordWrap(True)
        return rotulo

    def _montar_limitacoes(self) -> QWidget:
        caixa = QWidget()
        layout = QVBoxLayout(caixa)
        layout.setContentsMargins(0, 0, 0, 0)

        titulo = QLabel("<b>O que esta coleta NÃO vai alcançar</b>")
        layout.addWidget(titulo)

        linhas = []
        for modulo in self._modulos:
            limitacoes = modulo.get("limitacoes") or []
            if not limitacoes:
                continue
            linhas.append(modulo["nome"])
            linhas += [f"    • {limitacao}" for limitacao in limitacoes]
            linhas.append("")

        texto = QTextEdit()
        texto.setReadOnly(True)
        texto.setPlainText(
            "\n".join(linhas).strip()
            or "Nenhum dos módulos selecionados declarou limitações."
        )
        layout.addWidget(texto, 1)

        nota = QLabel(
            "<i>São limites do método, não deste aparelho. Servem para que a "
            "ausência de um dado no material coletado não seja lida como "
            "ausência do dado no aparelho.</i>"
        )
        nota.setWordWrap(True)
        layout.addWidget(nota)
        return caixa

    def _montar_alteracoes(self):
        """
        Só aparece quando há alteração declarada.

        Uma seção vazia dizendo "nenhuma alteração" a cada execução treinaria
        o olho a pular o bloco — e ele é justamente o que não pode passar
        despercebido quando existir.
        """
        pares = [
            (modulo["nome"], alteracao, justificativa)
            for modulo in self._modulos
            for alteracao, justificativa in (modulo.get("alteracoes") or [])
        ]
        if not pares:
            return None

        caixa = QWidget()
        layout = QVBoxLayout(caixa)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("<b>O que pode ser alterado no aparelho</b>"))

        linhas = []
        for nome, alteracao, justificativa in pares:
            linhas += [nome, f"    • {alteracao}", f"      Justificativa: {justificativa}", ""]

        texto = QTextEdit()
        texto.setReadOnly(True)
        texto.setPlainText("\n".join(linhas).strip())
        texto.setMaximumHeight(160)
        layout.addWidget(texto)

        nota = QLabel(
            "<i>É o que a execução pode provocar. A alteração que de fato "
            "ocorrer é anotada no registro do procedimento, no momento em que "
            "ocorrer.</i>"
        )
        nota.setWordWrap(True)
        layout.addWidget(nota)
        return caixa

    def _montar_botoes(self) -> QHBoxLayout:
        botoes = QHBoxLayout()
        botao_ok = QPushButton("Ciente — Prosseguir")
        botao_ok.setDefault(True)
        botao_ok.clicked.connect(self.accept)
        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)
        botoes.addStretch()
        botoes.addWidget(botao_ok)
        botoes.addWidget(botao_cancelar)
        return botoes
