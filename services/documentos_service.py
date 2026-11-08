"""
Os documentos de um caso, para serem abertos e entregues pela própria
ferramenta — sem o examinador precisar procurá-los no Explorer.

Os documentos moram fora das aquisições seladas: `<caso>/documentos/`
(relatório de extração, laudo, conversas) e `<caso>/relatorios/`
(relatório de conteúdo). Aqui eles são listados com o que são, de qual
aquisição vieram e quando foram gerados.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.hashing import calcular_sha256

PADRAO_AQUISICAO = re.compile(r"(android|ios|computador)_\d{8}_\d{6}", re.IGNORECASE)

TIPOS = (
    ("Laudo_Pericial", "Laudo Pericial"),
    ("Relatorio_de_Extracao", "Relatório de Extração"),
    ("Relatorio_de_Conteudo", "Relatório de Conteúdo"),
    ("Conversas_selecionadas", "Conversas selecionadas"),
)


@dataclass
class Documento:
    caminho: Path
    tipo: str
    aquisicao: str
    gerado_em: datetime

    @property
    def rotulo(self) -> str:
        return (f"{self.tipo} · {self.aquisicao or 'aquisição não identificada'} · "
                f"{self.gerado_em.strftime('%d/%m/%Y %H:%M')}")


def _tipo(nome: str) -> str:
    return next((rotulo for prefixo, rotulo in TIPOS if nome.startswith(prefixo)), "Documento")


def listar_documentos(pasta_caso: Path, aquisicao: str = "") -> List[Documento]:
    """
    PDFs gerados para o caso, do mais recente para o mais antigo. Com
    `aquisicao`, só os daquela aquisição.
    """
    pasta_caso = Path(pasta_caso)
    candidatos = list((pasta_caso / "documentos").glob("*.pdf"))
    candidatos += list((pasta_caso / "relatorios").glob("*/*.pdf"))
    documentos = []
    for caminho in candidatos:
        origem = PADRAO_AQUISICAO.search(caminho.name) or PADRAO_AQUISICAO.search(caminho.parent.name)
        nome_aquisicao = origem.group(0) if origem else ""
        if aquisicao and nome_aquisicao.lower() != aquisicao.lower():
            continue
        try:
            momento = datetime.fromtimestamp(caminho.stat().st_mtime)
        except OSError:
            continue
        documentos.append(Documento(caminho, _tipo(caminho.name), nome_aquisicao, momento))
    return sorted(documentos, key=lambda d: d.gerado_em, reverse=True)


def salvar_copia(origem: Path, destino: Path) -> str:
    """
    Copia um documento e confere a cópia pelo SHA-256. Devolve o hash;
    levanta `OSError` se a cópia não for idêntica ao original.
    """
    origem, destino = Path(origem), Path(destino)
    if destino.resolve() == origem.resolve():
        raise OSError("O destino é o próprio arquivo de origem.")
    shutil.copy2(origem, destino)
    original, copia = calcular_sha256(origem), calcular_sha256(destino)
    if original != copia:
        raise OSError(f"A cópia gravada NÃO é idêntica ao original (SHA-256 {copia} ≠ {original}).")
    return copia


def pasta_do_caso_de(pasta_aquisicao: Path) -> Optional[Path]:
    from core.case import pasta_do_caso

    caso = pasta_do_caso(Path(pasta_aquisicao))
    return caso if caso != Path(pasta_aquisicao).resolve() else None
