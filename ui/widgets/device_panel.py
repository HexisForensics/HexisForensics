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


class DevicePanel(QGroupBox):
    verificar_solicitado = Signal()

    def __init__(self, titulo: str = "Status do Dispositivo", parent=None):
        super().__init__(titulo, parent)
        layout = QVBoxLayout(self)

        self.label_status = QLabel("Status: desconhecido")
        self.label_status.setWordWrap(True)
        self.label_detalhe = QLabel("Clique em 'Verificar Conexão' para checar o dispositivo.")
        self.label_detalhe.setWordWrap(True)

        linha_botoes = QHBoxLayout()
        self.botao_verificar = QPushButton("🔎 Verificar Conexão")
        self.botao_verificar.clicked.connect(self.verificar_solicitado.emit)
        linha_botoes.addWidget(self.botao_verificar)
        linha_botoes.addStretch()

        layout.addWidget(self.label_status)
        layout.addWidget(self.label_detalhe)
        layout.addLayout(linha_botoes)

    def atualizar_status(self, conectado: bool, autorizado: bool, mensagem: str) -> None:
        if conectado and autorizado:
            cor, texto = COR_SUCESSO, "✔ Conectado e autorizado"
        elif conectado and not autorizado:
            cor, texto = COR_PARCIAL, "⚠ Detectado, aguardando autorização"
        else:
            cor, texto = COR_FALHA, "✖ Nenhum dispositivo detectado"

        self.label_status.setText(f"<b style='color:{cor};'>{texto}</b>")
        self.label_detalhe.setText(mensagem)
