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
from services.idioma import traduzir
from .ajuste_de_tela import caber_na_tela


class HashDialog(QDialog):
    def __init__(self, raiz_extracoes: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(traduzir("hd_titulo"))
        caber_na_tela(self, 700, 560)

        self.raiz_extracoes = Path(raiz_extracoes)
        self._itens: List[PastaDeCustodia] = listar_pastas_custodia(self.raiz_extracoes)
        self._servico = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(traduzir("hd_intro")))

        self.lista_pastas = QListWidget()
        for item in self._itens:
            self.lista_pastas.addItem(self._rotulo(item))
        self.lista_pastas.currentRowChanged.connect(self._ao_selecionar)
        layout.addWidget(self.lista_pastas)

        if not self._itens:
            layout.addWidget(QLabel(traduzir("hd_nenhuma_pasta")))

        self.area_resultado = QTextEdit()
        self.area_resultado.setReadOnly(True)
        self.area_resultado.setPlaceholderText(traduzir("hd_ph_resultado"))
        layout.addWidget(self.area_resultado)

        self.barra_progresso = QProgressBar()
        layout.addWidget(self.barra_progresso)

        linha_botoes = QHBoxLayout()
        self.botao_conferir = QPushButton(traduzir("hd_btn_conferir"))
        self.botao_conferir.setDefault(True)
        self.botao_conferir.clicked.connect(self._conferir)
        self.botao_gerar = QPushButton(traduzir("hd_btn_gerar"))
        self.botao_gerar.clicked.connect(self._gerar)
        self.botao_fechar = QPushButton(traduzir("hd_btn_fechar"))
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
        selo = traduzir("hd_selada") if item.selada else traduzir("hd_sem_manifesto")

        if item.e_aquisicao:
            quando = item.momento.strftime("%d/%m/%Y %H:%M") if item.momento else item.nome
            plataforma = item.plataforma or traduzir("hd_aquisicao_fallback")
            return traduzir("hd_rotulo_aquisicao", plataforma=plataforma, quando=quando, selo=selo)

        if item.aquisicoes:
            plural = (traduzir("hd_aquisicao_sing") if item.aquisicoes == 1
                      else traduzir("hd_aquisicao_plur"))
            escopo = traduzir("hd_escopo", n=item.aquisicoes, plural=plural)
            selo = traduzir("hd_caso_selado") if item.selada else traduzir("hd_caso_nao_selado")
        else:
            # Pasta única, sem subpastas de aquisição: são os casos criados
            # antes de a estrutura em dois níveis existir.
            escopo = traduzir("hd_pasta_unica")

        return traduzir("hd_rotulo_caso", nome=item.nome, escopo=escopo, selo=selo)

    def _item_selecionado(self) -> Optional[PastaDeCustodia]:
        indice = self.lista_pastas.currentRow()
        if indice < 0:
            QMessageBox.warning(self, traduzir("hd_aviso"), traduzir("hd_selecione"))
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
                traduzir("hd_integro_titulo"),
                traduzir("hd_integro_corpo", resumo=resumo),
            )
        else:
            # Divergência não é erro da ferramenta: é achado, e precisa de
            # destaque proporcional ao que significa para o exame.
            QMessageBox.warning(
                self,
                traduzir("hd_divergencia_titulo"),
                traduzir("hd_divergencia_corpo", resumo=resumo),
            )

    def _gerar(self) -> None:
        item = self._item_selecionado()
        if item is None:
            return

        if item.selada:
            resposta = QMessageBox.question(
                self,
                traduzir("hd_selada_titulo"),
                traduzir("hd_selada_corpo"),
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
            QMessageBox.information(
                self, traduzir("hd_concluido_titulo"),
                traduzir("hd_concluido_corpo", valor=mensagem))
        else:
            QMessageBox.critical(
                self, traduzir("hd_erro_titulo"),
                traduzir("hd_erro_corpo", valor=mensagem))
