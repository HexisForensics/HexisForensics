"""
Classificação dos arquivos adquiridos por categoria: imagens, vídeos,
áudios, PDF, documentos e assim por diante.

Os arquivos NÃO são movidos nem copiados para pastas por tipo: ficam onde
foram adquiridos, com o caminho que tinham no dispositivo. A classificação
é uma leitura sobre o material selado, impressa no Relatório de Extração e
no Laudo.

**A categoria vem da EXTENSÃO do nome do arquivo, não da análise do
conteúdo.** Um arquivo renomeado para `.txt` aparece como texto; um arquivo
sem extensão aparece em "Outros". Os documentos dizem isso ao lado da
tabela, porque "nenhum vídeo" aqui significa "nenhum arquivo com extensão
de vídeo" — e não que não haja vídeo no material.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

OUTROS = "Outros"

# Na ordem em que os documentos as mostram.
EXTENSOES = (
    ("Imagens", "jpg jpeg png gif bmp webp heic heif tif tiff svg ico raw dng"),
    ("Vídeos", "mp4 3gp mkv avi mov wmv webm m4v mpg mpeg ts"),
    ("Áudios", "mp3 opus ogg m4a aac wav amr flac wma"),
    ("PDF", "pdf"),
    ("Documentos de escritório", "doc docx xls xlsx ppt pptx odt ods odp rtf"),
    ("Texto e registros", "txt log csv json xml html htm ini cfg conf prop md yml yaml"),
    ("Bancos de dados e backups de aplicativo", "db sqlite sqlite3 ab pst ost"),
    ("Aplicativos", "apk apks xapk exe msi dll so jar"),
    ("Compactados", "zip rar 7z tar gz bz2"),
    ("Imagens de disco", "img dd e01 iso vhd vhdx"),
)
CATEGORIAS = tuple(nome for nome, _ in EXTENSOES) + (OUTROS,)
_POR_EXTENSAO = {
    extensao: categoria for categoria, lista in EXTENSOES for extensao in lista.split()
}
_COMPANHEIROS_DE_BANCO = ("db-wal", "db-shm", "db-journal")


def categoria_do_arquivo(nome: str) -> str:
    """Categoria pela extensão do nome. Sem extensão conhecida: "Outros"."""
    nome = nome.lower()
    if nome.endswith(_COMPANHEIROS_DE_BANCO):
        return "Bancos de dados e backups de aplicativo"
    extensao = nome.rsplit(".", 1)[-1] if "." in nome else ""
    # Backups do WhatsApp: msgstore.db.crypt12, .crypt14, .crypt15...
    if re.fullmatch(r"crypt\d+", extensao):
        return "Bancos de dados e backups de aplicativo"
    return _POR_EXTENSAO.get(extensao, OUTROS)


@dataclass
class Categoria:
    nome: str
    arquivos: List[Tuple[str, int]] = field(default_factory=list)  # (caminho, bytes)

    @property
    def quantidade(self) -> int:
        return len(self.arquivos)

    @property
    def volume(self) -> int:
        return sum(tamanho for _, tamanho in self.arquivos)


def classificar(arquivos: Iterable[Tuple[str, int]]) -> List[Categoria]:
    """
    Agrupa `(caminho, bytes)` por categoria, na ordem de `CATEGORIAS`.

    Devolve TODAS as categorias, inclusive as vazias: o documento precisa
    mostrar "Vídeos: 0" em vez de omitir a linha, para a ausência ser vista
    e não deduzida.
    """
    grupos = {nome: Categoria(nome) for nome in CATEGORIAS}
    for caminho, tamanho in arquivos:
        grupos[categoria_do_arquivo(caminho.rsplit("/", 1)[-1])].arquivos.append(
            (caminho, tamanho)
        )
    for categoria in grupos.values():
        categoria.arquivos.sort()
    return [grupos[nome] for nome in CATEGORIAS]
