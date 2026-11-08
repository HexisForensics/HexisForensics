"""
Painel de seleção de unidade de disco — equivalente ao `DevicePanel` do
Android/iOS, mas para a plataforma Computador: em vez de "conectado ou
não", aqui existe uma lista de unidades detectadas pelo Windows, das
quais o examinador escolhe uma para periciar.

O sinal `unidade_selecionada_mudou` é emitido sempre que a escolha muda —
inclusive para vazio, quando a lista é atualizada e nada fica selecionado
— para que a janela principal saiba se pode habilitar o botão de iniciar
extração.

As cores de status (verde/vermelho) são semânticas, não de marca — mesmo
padrão usado em `device_panel.py` — para continuarem reconhecíveis em
qualquer identidade visual (ver `ui.style`).
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal

from ..style import COR_FALHA, COR_SUCESSO
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from services.device_service import UnidadeInfo


def _formatar_espaco(bytes_valor: int) -> str:
    """Formata um valor em bytes como GB, com uma casa decimal, para exibição."""
    return f"{bytes_valor / (1024**3):.1f} GB"


class DiskPanel(QGroupBox):
    atualizar_solicitado = Signal()
    unidade_selecionada_mudou = Signal(
        str
    )  # caminho da unidade (ex. 'E:\\'), ou "" se nenhuma

    # O título carrega o alcance da plataforma ("computador, HD externo ou
    # pendrive") porque a barra lateral diz só "Computador": quem apreendeu
    # um pendrive precisa reconhecer a porta certa em algum lugar, e aqui é
    # onde a informação não desequilibra o layout.
    def __init__(
        self,
        titulo: str = "Unidade de Disco (computador, HD externo ou pendrive)",
        parent=None,
    ):
        super().__init__(titulo, parent)
        layout = QVBoxLayout(self)

        self.label_status = QLabel("Nenhuma unidade detectada ainda.")
        self.label_status.setWordWrap(True)

        self.combo_unidades = QComboBox()
        self.combo_unidades.currentIndexChanged.connect(self._ao_mudar_selecao)

        # Guarda quais caminhos são a estação do examinador, para responder
        # `unidade_selecionada_e_estacao()` sem consultar o serviço de novo.
        self._estacoes: set[str] = set()
        # caminho -> frase explicando por que o volume nao pode ser lido.
        self._bloqueios: dict[str, str] = {}

        self.label_aviso = QLabel()
        self.label_aviso.setWordWrap(True)
        self.label_aviso.setVisible(False)

        linha_botoes = QHBoxLayout()
        self.botao_atualizar = QPushButton("🔄 Atualizar Unidades")
        self.botao_atualizar.clicked.connect(self.atualizar_solicitado.emit)
        linha_botoes.addWidget(self.botao_atualizar)
        linha_botoes.addStretch()

        layout.addWidget(self.label_status)
        layout.addWidget(self.combo_unidades)
        layout.addWidget(self.label_aviso)
        layout.addLayout(linha_botoes)

    def atualizar_lista(self, unidades: List[UnidadeInfo]) -> None:
        """
        Repovoa o combo com as unidades detectadas. Chamado pela janela
        principal após consultar
        `DeviceService.listar_unidades_computador()`.
        """
        self.combo_unidades.blockSignals(True)
        self.combo_unidades.clear()
        self._estacoes = {u.caminho for u in unidades if u.e_estacao_do_examinador}
        self._bloqueios = {
            u.caminho: u.explicacao_bloqueio for u in unidades if u.bloqueio
        }

        if not unidades:
            self.label_status.setText(
                f"<b style='color:{COR_FALHA};'>✖ Nenhuma unidade detectada.</b> "
                "Conecte o disco do computador periciado (por dock/adaptador), "
                "um HD externo ou um pendrive, e clique em 'Atualizar Unidades'."
            )
            self.combo_unidades.blockSignals(False)
            self.unidade_selecionada_mudou.emit("")
            return

        for unidade in unidades:
            rotulo_exibicao = unidade.rotulo or "(sem rótulo)"
            texto = (
                f"{unidade.caminho}  —  {rotulo_exibicao}  [{unidade.tipo_descricao}]  "
                f"{_formatar_espaco(unidade.bytes_livres)} livres de "
                f"{_formatar_espaco(unidade.bytes_total)}"
            )
            # A estação do examinador continua na lista — esconder unidade
            # sem dizer que escondeu é a mesma doença de uma conclusão sem
            # lastro, só que em forma de tela. Ela vem NOMEADA, para ser
            # reconhecida e não escolhida por engano.
            if unidade.e_estacao_do_examinador:
                texto = f"⚠ ESTAÇÃO DO EXAMINADOR — {texto}"
            # Volume que o Windows nao conseguiu ler aparece dizendo isso na
            # propria linha. Sem essa marca, ele se apresenta como um disco
            # de 0 GB sem rotulo — e "o pendrive esta com defeito" vira a
            # leitura mais natural de uma tela que nao explicou nada.
            if unidade.bloqueio == "bitlocker":
                texto = f"🔒 BITLOCKER BLOQUEADO — {texto}"
            elif unidade.bloqueio:
                texto = f"⛔ NÃO LEGÍVEL — {texto}"
            self.combo_unidades.addItem(texto, userData=unidade.caminho)

        self.label_status.setText(
            f"<b style='color:{COR_SUCESSO};'>✔ {len(unidades)} unidade(s) detectada(s).</b>"
        )
        self.combo_unidades.blockSignals(False)
        self._ao_mudar_selecao(self.combo_unidades.currentIndex())

    def unidade_selecionada(self) -> Optional[str]:
        """Devolve o caminho da unidade escolhida (ex. 'E:\\'), ou `None` se nenhuma."""
        dados = self.combo_unidades.currentData()
        return dados if dados else None

    def unidade_selecionada_e_estacao(self) -> bool:
        """
        Diz se a unidade escolhida é aquela onde o próprio HexisForensics
        está instalado. Quem decide o que fazer com isso é a `MainWindow`,
        no momento de iniciar a extração — este widget só apresenta.
        """
        caminho = self.unidade_selecionada()
        return bool(caminho) and caminho in self._estacoes

    def explicacao_do_bloqueio_selecionado(self) -> str:
        """Frase sobre o volume escolhido, ou "" se ele responde normalmente."""
        return self._bloqueios.get(self.unidade_selecionada() or "", "")

    def _ao_mudar_selecao(self, _indice: int) -> None:
        caminho = self.unidade_selecionada() or ""

        # Os dois avisos podem valer ao mesmo tempo, e nenhum cala o outro:
        # cada um fala de um problema diferente com a mesma escolha.
        avisos = []
        if self.unidade_selecionada_e_estacao():
            avisos.append(
                f"<b style='color:{COR_FALHA};'>⚠ Esta é a estação do examinador</b> — "
                "a unidade onde o HexisForensics está instalado. Ela não é objeto "
                "de perícia, e periciá-la faz a coleta ler o disco em que a própria "
                "saída está sendo gravada."
            )
        explicacao = self.explicacao_do_bloqueio_selecionado()
        if explicacao:
            avisos.append(
                f"<b style='color:{COR_FALHA};'>⛔ Volume não legível</b> — {explicacao}"
            )

        self.label_aviso.setText("<br><br>".join(avisos))
        self.label_aviso.setVisible(bool(avisos))
        self.unidade_selecionada_mudou.emit(caminho)
