"""
Serviço de integridade (cadeia de custódia).

Envolve `core.hashing` para a UI: listar as pastas de extração existentes
e gerar o manifesto SHA-256 de uma delas, em uma `QThread` para não
travar a interface durante o cálculo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from core.case import descrever_aquisicao, e_pasta_de_aquisicao
from core.hashing import (
    conferir_manifesto,
    gerar_manifesto,
    listar_pastas_extracao as _listar_pastas_extracao,
    localizar_manifesto,
)


def listar_pastas_extracao(raiz_extracoes: Path) -> List[Path]:
    return _listar_pastas_extracao(raiz_extracoes)


def tem_manifesto(pasta: Path) -> bool:
    """Se a pasta já está selada — a UI usa isso para orientar a ação."""
    return localizar_manifesto(Path(pasta)) is not None


@dataclass
class PastaDeCustodia:
    """
    Uma pasta que pode receber ou ter um manifesto, e o que ela é.

    Caso e aquisição aparecem na mesma lista porque são **escopos
    diferentes de selo**, e não a mesma coisa repetida: conferir a aquisição
    verifica uma coleta; conferir o caso verifica o projeto inteiro, útil
    quando ele reúne mais de um dispositivo. A UI precisa desses campos para
    deixar essa diferença visível.
    """

    caminho: Path
    e_aquisicao: bool
    nome: str
    selada: bool
    plataforma: str = ""
    momento: Optional[datetime] = None
    aquisicoes: int = 0


def listar_pastas_custodia(raiz_extracoes: Path) -> List[PastaDeCustodia]:
    """Casos e suas aquisições, na ordem em que devem ser exibidos."""
    itens: List[PastaDeCustodia] = []

    for pasta in _listar_pastas_extracao(raiz_extracoes):
        e_aquisicao = e_pasta_de_aquisicao(pasta.name)
        plataforma, momento = descrever_aquisicao(pasta.name) if e_aquisicao else ("", None)
        filhas = (
            0
            if e_aquisicao
            else sum(1 for sub in pasta.iterdir() if sub.is_dir() and e_pasta_de_aquisicao(sub.name))
        )
        itens.append(
            PastaDeCustodia(
                caminho=pasta,
                e_aquisicao=e_aquisicao,
                nome=pasta.name,
                selada=tem_manifesto(pasta),
                plataforma=plataforma,
                momento=momento,
                aquisicoes=filhas,
            )
        )
    return itens


class HashService(QThread):
    """Gera o manifesto de hashes (cadeia de custódia) de uma pasta de extração."""

    log_emitido = Signal(str)
    progresso_emitido = Signal(int)
    concluido = Signal(bool, str)

    def __init__(self, pasta_alvo: Path, parent=None):
        super().__init__(parent)
        self.pasta_alvo = Path(pasta_alvo)

    def run(self) -> None:
        try:
            caminho = gerar_manifesto(
                self.pasta_alvo,
                log_callback=self.log_emitido.emit,
                progress_callback=self.progresso_emitido.emit,
            )
            self.concluido.emit(True, str(caminho))
        except Exception as exc:
            self.concluido.emit(False, str(exc))


class ConferenciaService(QThread):
    """
    Confere o manifesto de uma pasta contra os arquivos em disco.

    É a operação que dá sentido ao manifesto: gerar o hash prova pouco, o
    que sustenta a cadeia de custódia é demonstrar depois que o material não
    mudou entre a coleta e o exame.

    O rastro de cada conferência é o relatório `conferencia_integridade_*.txt`,
    gravado por `conferir_manifesto` e deixado fora do manifesto por regra.

    A conferência NUNCA escreve em arquivo selado. Até 02/11/2026 ela anotava
    o resultado no `registro_procedimento.txt` da aquisição, que está dentro
    do lacre: a primeira conferência dava ÍNTEGRO e a segunda acusava esse
    arquivo como alterado — a ferramenta alterava a evidência ao conferi-la.
    """

    log_emitido = Signal(str)
    progresso_emitido = Signal(int)
    concluido = Signal(bool, str)

    def __init__(self, pasta_alvo: Path, parent=None):
        super().__init__(parent)
        self.pasta_alvo = Path(pasta_alvo)

    def run(self) -> None:
        try:
            resultado = conferir_manifesto(
                self.pasta_alvo,
                log_callback=self.log_emitido.emit,
                progress_callback=self.progresso_emitido.emit,
            )
            self.concluido.emit(resultado.integro, resultado.resumo)
        except Exception as exc:  # pragma: no cover - defesa contra falha de E/S
            self.concluido.emit(False, str(exc))
