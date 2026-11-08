"""
Diálogo de cadeia de custódia: conferir e gerar manifestos SHA-256.

Duas ações, com pesos diferentes de propósito:

**Conferir** é a ação principal. Recalcula os hashes e confronta com o
manifesto existente, apontando o que foi alterado, o que sumiu e o que
entrou depois do selo. É o que sustenta a cadeia de custódia — gerar um
hash prova pouco; o que vale é poder demonstrar, mais tarde, que o material
não mudou entre a coleta e o exame.

**Gerar** existe para selar o que ainda não foi selado: o caso inteiro
(quando reúne várias aquisições), pastas anteriores à geração automática, ou
material acrescentado depois. Nunca sobrescreve um manifesto existente.

A lista mostra dois níveis, **caso** e **aquisição**, indentados. Eles não
são a mesma coisa repetida: são escopos diferentes de selo. Conferir a
aquisição verifica uma coleta; conferir o caso verifica o projeto inteiro,
útil quando ele reúne mais de um dispositivo.

Usa `services.hash_service` — não importa nada de `core.hashing`
diretamente.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from services.hash_service import (
    ConferenciaService,
    HashService,
    PastaDeCustodia,
    listar_pastas_custodia,
    tem_manifesto,
)
from .ajuste_de_tela import caber_na_tela


class HashDialog(QDialog):
    def __init__(self, raiz_extracoes: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cadeia de Custódia — Conferir e Gerar Manifestos")
        caber_na_tela(self, 700, 560)

        self.raiz_extracoes = Path(raiz_extracoes)
        self._itens: List[PastaDeCustodia] = listar_pastas_custodia(self.raiz_extracoes)
        self._servico = None

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<b>Conferir</b> verifica se o material continua idêntico ao manifesto. "
                "<b>Gerar</b> sela uma pasta ainda sem manifesto.<br>"
                "Cada <b>caso</b> pode conter várias <b>aquisições</b>: selar a aquisição "
                "cobre aquela coleta; selar o caso cobre o projeto inteiro."
            )
        )

        self.lista_pastas = QListWidget()
        for item in self._itens:
            self.lista_pastas.addItem(self._rotulo(item))
        self.lista_pastas.currentRowChanged.connect(self._ao_selecionar)
        layout.addWidget(self.lista_pastas)

        if not self._itens:
            layout.addWidget(QLabel("Nenhuma pasta de extração encontrada em 'extracoes/'."))

        self.area_resultado = QTextEdit()
        self.area_resultado.setReadOnly(True)
        self.area_resultado.setPlaceholderText("O resultado da operação aparece aqui.")
        layout.addWidget(self.area_resultado)

        self.barra_progresso = QProgressBar()
        layout.addWidget(self.barra_progresso)

        linha_botoes = QHBoxLayout()
        self.botao_conferir = QPushButton("🔍 Conferir Integridade")
        self.botao_conferir.setDefault(True)
        self.botao_conferir.clicked.connect(self._conferir)
        self.botao_gerar = QPushButton("Gerar Manifesto")
        self.botao_gerar.clicked.connect(self._gerar)
        self.botao_fechar = QPushButton("Fechar")
        self.botao_fechar.clicked.connect(self.close)

        linha_botoes.addStretch()
        linha_botoes.addWidget(self.botao_conferir)
        linha_botoes.addWidget(self.botao_gerar)
        linha_botoes.addWidget(self.botao_fechar)
        layout.addLayout(linha_botoes)

        self._ao_selecionar(self.lista_pastas.currentRow())

    # ------------------------------------------------------------------
    # Apresentação
    # ------------------------------------------------------------------
    @staticmethod
    def _rotulo(item: PastaDeCustodia) -> str:
        """
        Monta a linha da lista deixando a hierarquia visível.

        Sem a indentação e o rótulo, caso e aquisição apareciam como dois
        nomes soltos — e a leitura natural era de que a mesma pasta estava
        repetida.
        """
        selo = "🔒 selada" if item.selada else "○ sem manifesto"

        if item.e_aquisicao:
            quando = item.momento.strftime("%d/%m/%Y %H:%M") if item.momento else item.nome
            plataforma = item.plataforma or "Aquisição"
            return f"        └─  {plataforma} · {quando}  ·  {selo}"

        if item.aquisicoes:
            plural = "aquisição" if item.aquisicoes == 1 else "aquisições"
            escopo = f"{item.aquisicoes} {plural}"
            selo = "🔒 caso selado" if item.selada else "○ caso ainda não selado"
        else:
            # Pasta única, sem subpastas de aquisição: são os casos criados
            # antes de a estrutura em dois níveis existir.
            escopo = "pasta única (formato antigo)"

        return f"📁  {item.nome}    —    {escopo}  ·  {selo}"

    def _item_selecionado(self) -> Optional[PastaDeCustodia]:
        indice = self.lista_pastas.currentRow()
        if indice < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um caso ou uma aquisição na lista.")
            return None
        return self._itens[indice]

    def _ao_selecionar(self, indice: int) -> None:
        """Conferir só faz sentido em pasta já selada."""
        self.botao_conferir.setEnabled(indice >= 0 and self._itens[indice].selada)

    def _atualizar_linha(self) -> None:
        """Reflete na lista que a pasta passou a estar selada."""
        indice = self.lista_pastas.currentRow()
        if indice < 0:
            return
        item = self._itens[indice]
        item.selada = tem_manifesto(item.caminho)
        self.lista_pastas.item(indice).setText(self._rotulo(item))
        self._ao_selecionar(indice)

    def _preparar(self) -> None:
        self.botao_conferir.setEnabled(False)
        self.botao_gerar.setEnabled(False)
        self.barra_progresso.setValue(0)
        self.area_resultado.clear()

    def _registrar(self, mensagem: str) -> None:
        self.area_resultado.append(mensagem)

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _conferir(self) -> None:
        item = self._item_selecionado()
        if item is None:
            return

        self._preparar()
        self._servico = ConferenciaService(item.caminho)
        self._servico.log_emitido.connect(self._registrar)
        self._servico.progresso_emitido.connect(self.barra_progresso.setValue)
        self._servico.concluido.connect(self._ao_conferir)
        self._servico.start()

    def _ao_conferir(self, integro: bool, resumo: str) -> None:
        self._atualizar_linha()
        self.botao_gerar.setEnabled(True)
        self._registrar("")
        self._registrar(resumo)

        if integro:
            QMessageBox.information(
                self,
                "Integridade confirmada",
                f"{resumo}\n\nO relatório da conferência foi gravado na pasta.",
            )
        else:
            # Divergência não é erro da ferramenta: é achado, e precisa de
            # destaque proporcional ao que significa para o exame.
            QMessageBox.warning(
                self,
                "DIVERGÊNCIA DE INTEGRIDADE",
                f"{resumo}\n\nO material NÃO está idêntico ao manifesto. "
                "Consulte o relatório de conferência gravado na pasta para ver "
                "exatamente quais arquivos divergem.",
            )

    def _gerar(self) -> None:
        item = self._item_selecionado()
        if item is None:
            return

        if item.selada:
            resposta = QMessageBox.question(
                self,
                "Esta pasta já está selada",
                "Já existe um manifesto nesta pasta.\n\n"
                "Para saber se o material continua íntegro, use CONFERIR — gerar de novo "
                "não verifica nada.\n\n"
                "Se prosseguir, o manifesto original será PRESERVADO e um novo será "
                "gravado ao lado, com data e hora no nome.\n\nDeseja gerar assim mesmo?",
            )
            if resposta != QMessageBox.Yes:
                return

        self._preparar()
        self._servico = HashService(item.caminho)
        self._servico.log_emitido.connect(self._registrar)
        self._servico.progresso_emitido.connect(self.barra_progresso.setValue)
        self._servico.concluido.connect(self._ao_gerar)
        self._servico.start()

    def _ao_gerar(self, sucesso: bool, mensagem: str) -> None:
        self._atualizar_linha()
        self.botao_gerar.setEnabled(True)

        if sucesso:
            QMessageBox.information(self, "Concluído", f"Manifesto gerado em:\n{mensagem}")
        else:
            QMessageBox.critical(self, "Erro", f"Falha ao gerar manifesto:\n{mensagem}")
