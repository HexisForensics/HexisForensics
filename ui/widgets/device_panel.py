"""
Painel de status de conexão do dispositivo (Android ou iOS).

As cores de status (verde/âmbar/vermelho) são semânticas, não de marca —
comunicam "conectado/aguardando/erro" e propositalmente não vêm do
`BrandConfig`, para continuarem reconhecíveis em qualquer identidade
visual (ver `ui.style`).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..style import COR_FALHA, COR_PARCIAL, COR_SUCESSO
from services.idioma import traduzir


class DevicePanel(QGroupBox):
    verificar_solicitado = Signal()

    def __init__(self, titulo: str = None, parent=None):
        super().__init__(titulo if titulo is not None else traduzir("dp_titulo_padrao"), parent)
        layout = QVBoxLayout(self)

        self.label_status = QLabel(traduzir("dp_status_desconhecido"))
        self.label_status.setWordWrap(True)
        self.label_detalhe = QLabel(traduzir("dp_detalhe_inicial"))
        self.label_detalhe.setWordWrap(True)

        linha_botoes = QHBoxLayout()
        self.botao_verificar = QPushButton(traduzir("dp_btn_verificar"))
        self.botao_verificar.clicked.connect(self.verificar_solicitado.emit)
        linha_botoes.addWidget(self.botao_verificar)
        linha_botoes.addStretch()

        layout.addWidget(self.label_status)
        layout.addWidget(self.label_detalhe)
        layout.addLayout(linha_botoes)

    def atualizar_status(self, conectado: bool, autorizado: bool, mensagem: str) -> None:
        if conectado and autorizado:
            cor, texto = COR_SUCESSO, traduzir("dp_conectado")
        elif conectado and not autorizado:
            cor, texto = COR_PARCIAL, traduzir("dp_aguardando")
        else:
            cor, texto = COR_FALHA, traduzir("dp_nao_detectado")

        self.label_status.setText(f"<b style='color:{cor};'>{texto}</b>")
        self.label_detalhe.setText(mensagem)
