"""
O material de uma aquisição, para ser examinado pela própria ferramenta —
SÓ LEITURA.

Abrir a pasta lacrada no Explorer do Windows não é inofensivo: ao navegar,
ele pode criar arquivos ocultos dentro dela (`Thumbs.db`, `desktop.ini`),
e a conferência passa a acusar "arquivo acrescentado". Aqui nada é gravado
dentro da aquisição: os arquivos são listados, lidos para a prévia e
conferidos contra o lacre. Banco de dados é aberto sobre CÓPIA, numa pasta
temporária (`core.sqlite_forense`), porque abrir o original pode alterá-lo.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.hashing import calcular_sha256, ler_manifesto, localizar_manifesto
from core.sqlite_forense import abrir as abrir_banco
from core.sqlite_forense import parece_sqlite

LIMITE_DE_BUSCA = 500
LIMITE_DE_TEXTO = 200_000  # bytes lidos para a prévia de texto
LIMITE_DE_LINHAS_CSV = 300
LIMITE_PARA_CONFERIR_SOZINHO = 50 * 1024 * 1024  # acima disso, só a pedido

IMAGENS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
TEXTOS = {".txt", ".log", ".json", ".xml", ".html", ".htm", ".ini", ".cfg", ".md", ".jsonl",
          ".vcf", ".plist", ".sha256"}
PLANILHAS = {".csv", ".tsv"}
DOCUMENTOS = {".pdf"}
BANCOS = {".db", ".sqlite", ".sqlite3", ".sqlitedb", ".storedata"}


@dataclass
class Entrada:
    nome: str
    relativo: str
    e_pasta: bool
    tamanho: int = 0
    modificado: Optional[datetime] = None


@dataclass
class Conferencia:
    sha256_agora: str
    sha256_no_lacre: str

    @property
    def situacao(self) -> str:
        if not self.sha256_no_lacre:
            return "não consta do lacre"
        return "confere" if self.sha256_agora == self.sha256_no_lacre else "DIVERGE"


class Material:
    """Acesso somente leitura ao material de uma aquisição."""

    def __init__(self, pasta_aquisicao: Path):
        self.pasta = Path(pasta_aquisicao).resolve()
        self._lacre: Optional[Dict[str, str]] = None

    # ------------------------------------------------------------------
    def _caminho(self, relativo: str) -> Path:
        caminho = (self.pasta / relativo).resolve()
        if caminho != self.pasta and self.pasta not in caminho.parents:
            raise ValueError("Caminho fora da aquisição.")
        return caminho

    def lacre(self) -> Dict[str, str]:
        if self._lacre is None:
            manifesto = localizar_manifesto(self.pasta)
            try:
                self._lacre = ler_manifesto(manifesto) if manifesto else {}
            except OSError:
                self._lacre = {}
        return self._lacre

    def listar(self, relativo: str = "") -> List[Entrada]:
        """O conteúdo de uma pasta: pastas primeiro, depois arquivos, por nome."""
        entradas = []
        try:
            itens = list(os.scandir(self._caminho(relativo)))
        except OSError:
            return []
        for item in itens:
            rel = (Path(relativo) / item.name).as_posix() if relativo else item.name
            try:
                info = item.stat()
            except OSError:
                info = None
            entradas.append(Entrada(
                item.name, rel, item.is_dir(),
                0 if item.is_dir() or info is None else info.st_size,
                datetime.fromtimestamp(info.st_mtime) if info else None,
            ))
        return sorted(entradas, key=lambda e: (not e.e_pasta, e.nome.lower()))

    def buscar(self, termo: str) -> Tuple[List[Entrada], bool]:
        """Arquivos cujo nome contém o termo. `(achados, cortado_no_limite)`."""
        termo = termo.strip().lower()
        achados = []
        for raiz, _pastas, arquivos in os.walk(self.pasta):
            for nome in arquivos:
                if termo in nome.lower():
                    caminho = Path(raiz) / nome
                    try:
                        info = caminho.stat()
                    except OSError:
                        continue
                    achados.append(Entrada(nome, caminho.relative_to(self.pasta).as_posix(), False,
                                           info.st_size, datetime.fromtimestamp(info.st_mtime)))
                    if len(achados) >= LIMITE_DE_BUSCA:
                        return achados, True
        return achados, False

    def conferir(self, relativo: str) -> Conferencia:
        """Recalcula o SHA-256 do arquivo e compara com o lacre."""
        return Conferencia(calcular_sha256(self._caminho(relativo)), self.lacre().get(relativo, ""))

    def tamanho(self, relativo: str) -> int:
        return self._caminho(relativo).stat().st_size

    # ------------------------------------------------------------------
    # Prévias
    # ------------------------------------------------------------------
    def tipo_de_previa(self, relativo: str) -> str:
        sufixo = Path(relativo).suffix.lower()
        if sufixo in IMAGENS:
            return "imagem"
        if sufixo in PLANILHAS:
            return "planilha"
        if sufixo in DOCUMENTOS:
            return "pdf"
        if sufixo in BANCOS or parece_sqlite(self._caminho(relativo)):
            return "banco"
        if sufixo in TEXTOS or not sufixo:
            return "texto"
        return "binario"

    def caminho_para_leitura(self, relativo: str) -> Path:
        """Para a interface abrir imagem/PDF em modo leitura."""
        return self._caminho(relativo)

    def previa_texto(self, relativo: str) -> Tuple[str, bool]:
        """`(texto, cortado)`. Conteúdo binário vira hexadecimal, dito como tal."""
        with open(self._caminho(relativo), "rb") as arquivo:
            dados = arquivo.read(LIMITE_DE_TEXTO + 1)
        cortado = len(dados) > LIMITE_DE_TEXTO
        dados = dados[:LIMITE_DE_TEXTO]
        if b"\x00" in dados[:4096]:
            return self.previa_hex(relativo), True
        return dados.decode("utf-8", errors="replace"), cortado

    def previa_hex(self, relativo: str, quantidade: int = 1024) -> str:
        with open(self._caminho(relativo), "rb") as arquivo:
            dados = arquivo.read(quantidade)
        linhas = ["Conteúdo binário — primeiros bytes em hexadecimal:", ""]
        for inicio in range(0, len(dados), 16):
            bloco = dados[inicio:inicio + 16]
            texto = "".join(chr(b) if 32 <= b < 127 else "." for b in bloco)
            linhas.append(f"{inicio:08x}  {bloco.hex(' '):<47}  {texto}")
        return "\n".join(linhas)

    def previa_planilha(self, relativo: str) -> Tuple[List[str], List[List[str]], bool]:
        """`(cabeçalho, linhas, cortado)`."""
        texto, _ = self.previa_texto(relativo)
        separador = "\t" if relativo.lower().endswith(".tsv") else ","
        leitor = csv.reader(io.StringIO(texto), delimiter=separador)
        todas = []
        for linha in leitor:
            todas.append(linha)
            if len(todas) > LIMITE_DE_LINHAS_CSV + 1:
                break
        if not todas:
            return [], [], False
        return todas[0], todas[1:LIMITE_DE_LINHAS_CSV + 1], len(todas) > LIMITE_DE_LINHAS_CSV + 1

    def previa_banco(self, relativo: str) -> Tuple[List[Tuple[str, int]], str]:
        """
        `([(tabela, quantidade de linhas)], motivo)`. Lido sobre CÓPIA em
        pasta temporária: o original não é aberto pelo SQLite.
        """
        with tempfile.TemporaryDirectory(prefix="forense_material_") as trabalho:
            with abrir_banco(self._caminho(relativo), Path(trabalho)) as banco:
                if not banco.legivel:
                    return [], banco.motivo
                tabelas = []
                for nome in banco.tabelas:
                    try:
                        quantidade = banco.consultar(f'SELECT COUNT(*) FROM "{nome}"')[0][0]
                    except Exception:
                        quantidade = -1
                    tabelas.append((nome, quantidade))
                motivo = "" if banco.integridade in ("", "ok") else f"integridade: {banco.integridade}"
                return tabelas, motivo
