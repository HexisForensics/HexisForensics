"""
Abertura forense de banco SQLite: ler sem alterar, e sem perder o que
ainda não foi consolidado.

Todo dado de aplicativo que interessa a uma investigação mora num SQLite —
`msgstore.db` do WhatsApp, o banco do Gmail, o `History` dos navegadores,
o `places.sqlite` do Firefox. A suíte já adquire esses arquivos e não sabe
abrir nenhum. Este módulo é a fundação que falta, e existe para que abrir
um banco nunca seja um ato que altera evidência.

Quatro regras, e as duas primeiras se contradizem à primeira vista.

**1. Nunca se abre o original.** Trabalha-se sobre uma cópia, fora da
aquisição selada. Abrir um SQLite com WAL pendente faz o próprio SQLite
incorporar o WAL ao arquivo — o arquivo muda, o hash quebra, e a aquisição
deixa de conferir. O hash do original é calculado ANTES da cópia e viaja
junto do resultado.

**2. A cópia é aberta em modo que permite ao SQLite fazer o que precisa.**
Aqui mora a armadilha. A intuição manda usar `immutable=1`, que promete
não tocar no arquivo — e o preço é que **o WAL é inteiramente ignorado**.
Medido: um banco com a tabela criada dentro do WAL, aberto com
`immutable=1`, responde *"no such table"*. Não é dado a menos, é o banco
inteiro invisível. Por isso a cópia é aberta com `mode=ro` comum, que lê o
WAL; e é justamente por ser cópia que deixar o SQLite mexer nela não custa
nada.

**3. Os companheiros vão junto.** O `-wal` guarda o que ainda não entrou no
banco. Copiar só o `.db` perderia as mensagens mais recentes, e nada
avisaria — ver `core.companheiros`. Quando o `-wal` não veio na aquisição,
o resultado **diz isso**: não é "não havia mensagens recentes", é "não se
sabe".

**4. Registro ausente nunca vira silêncio.** Banco corrompido, arquivo que
não é SQLite, esquema diferente do esperado — cada um tem seu motivo
declarado. Um leitor que devolvesse zero linhas para os três produziria a
conclusão negativa falsa que esta ferramenta existe para impedir.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .companheiros import companheiros_de
from .hashing import calcular_sha256, localizar_manifesto

# Todo arquivo SQLite começa com estes 16 bytes. Conferir a assinatura
# evita a mensagem enganosa de "file is not a database" e permite dizer ao
# examinador o que o arquivo realmente é: outra coisa.
ASSINATURA = b"SQLite format 3\x00"

INTEGRIDADE_OK = "ok"


@dataclass
class BancoAberto:
    """
    O que se sabe sobre um banco depois de tentar abri-lo.

    `legivel` falso sempre vem com `motivo` preenchido — nenhuma recusa
    silenciosa.
    """

    caminho_original: Path
    legivel: bool = False
    motivo: str = ""
    conexao: object = None
    copia: Optional[Path] = None
    sha256_original: str = ""
    companheiros: List[str] = field(default_factory=list)
    integridade: str = ""
    modo_journal: str = ""
    tabelas: tuple = ()

    @property
    def tem_wal(self) -> bool:
        """`True` se o write-ahead log acompanhou o banco."""
        return any(nome.endswith("-wal") for nome in self.companheiros)

    @property
    def usa_wal(self) -> bool:
        """
        `True` se o banco opera em modo write-ahead log.

        O modo está gravado no cabeçalho do arquivo, e por isso é legível
        na cópia mesmo quando o `-wal` não veio junto. Banco em modo
        `delete` — o padrão do SQLite, e o que o provedor de telefonia do
        Android usa — nunca teve WAL algum.
        """
        return self.modo_journal.lower() == "wal"

    @property
    def ressalva_do_wal(self) -> str:
        """
        Por que a ausência do WAL importa — vazio quando não há o que dizer.

        Não é possível saber, olhando só o `.db`, se existia um WAL que
        ficou para trás. Por isso a ressalva é sobre o que NÃO se pode
        afirmar, e não sobre o que faltou.

        Mas ela só vale para banco que **usa** WAL. Emiti-la sobre um banco
        em modo `delete` seria declarar uma limitação que não existe: nunca
        houve `-wal` para acompanhar. Apareceu contra o banco de telefonia
        real do emulador, e é o mesmo defeito de afirmar sem verificar,
        virado do avesso — em vez de sucesso que não houve, limitação que
        não havia.
        """
        if self.tem_wal or not self.usa_wal:
            return ""
        return (
            "O write-ahead log (-wal) não acompanhou este banco. Se havia registros "
            "ainda não consolidados no arquivo principal, eles não estão aqui — e não "
            "é possível determinar, a partir do que se tem, se existiam."
        )

    @property
    def integra(self) -> bool:
        return self.integridade == INTEGRIDADE_OK

    def tem_tabelas(self, *nomes: str) -> bool:
        """`True` se todas as tabelas informadas existem no banco."""
        presentes = {t.lower() for t in self.tabelas}
        return all(nome.lower() in presentes for nome in nomes)

    def consultar(self, sql: str, parametros=()) -> list:
        """Executa uma consulta de leitura. Lista vazia se o banco não abriu."""
        if not self.legivel or self.conexao is None:
            return []
        return self.conexao.execute(sql, parametros).fetchall()


def parece_sqlite(caminho: Path) -> bool:
    """`True` se o arquivo começa com a assinatura de um banco SQLite."""
    try:
        with open(caminho, "rb") as arquivo:
            return arquivo.read(len(ASSINATURA)) == ASSINATURA
    except OSError:
        return False


def dentro_de_aquisicao_selada(pasta: Path) -> bool:
    """
    `True` se a pasta está dentro de algo que já tem manifesto.

    Serve de trava: a cópia de trabalho jamais pode nascer dentro de uma
    aquisição selada. Gravá-la ali faria a conferência de integridade
    acusar arquivo acrescentado, e a coleta deixaria de fechar íntegra por
    causa de um ato de leitura.
    """
    pasta = Path(pasta)
    for candidata in [pasta, *pasta.parents]:
        if localizar_manifesto(candidata) is not None:
            return True
    return False


@contextmanager
def abrir(caminho: Path, pasta_trabalho: Path):
    """
    Abre um banco para leitura, sobre cópia, e devolve um `BancoAberto`.

    Sempre entrega um objeto — nunca levanta por banco ilegível. Quem
    chama decide o que dizer no laudo, e o motivo vem escrito.

    A cópia fica em `pasta_trabalho` e é apagada na saída. O original não
    é tocado em momento algum.
    """
    caminho = Path(caminho)
    pasta_trabalho = Path(pasta_trabalho)
    banco = BancoAberto(caminho_original=caminho)

    try:
        if dentro_de_aquisicao_selada(pasta_trabalho):
            banco.motivo = (
                f"A pasta de trabalho '{pasta_trabalho}' está dentro de uma aquisição "
                "já selada. Copiar o banco para ali faria a conferência de integridade "
                "acusá-lo como arquivo acrescentado. Nenhuma leitura foi feita."
            )
            yield banco
            return

        try:
            caminho.stat()
        except FileNotFoundError:
            banco.motivo = f"O arquivo '{caminho.name}' não existe."
            yield banco
            return
        except OSError as erro:
            banco.motivo = f"Sem acesso a '{caminho.name}': {erro}"
            yield banco
            return

        if not parece_sqlite(caminho):
            banco.motivo = (
                f"'{caminho.name}' não é um banco SQLite: não começa com a assinatura "
                "do formato. O arquivo existe e foi lido — é outra coisa."
            )
            yield banco
            return

        # O hash sai ANTES da cópia, sobre o original intocado. É o que
        # prende o que se leu ao que foi selado no dia da coleta.
        banco.sha256_original = calcular_sha256(caminho)

        pasta_trabalho.mkdir(parents=True, exist_ok=True)
        copia = pasta_trabalho / caminho.name
        shutil.copy2(caminho, copia)
        banco.copia = copia

        for companheiro in companheiros_de(caminho):
            shutil.copy2(companheiro, pasta_trabalho / companheiro.name)
            banco.companheiros.append(companheiro.name)

        # `mode=ro` sobre a CÓPIA. Não se usa `immutable=1`: ele promete
        # não tocar no arquivo e cobra por isso o WAL inteiro, que é onde
        # estão os registros mais recentes.
        try:
            conexao = sqlite3.connect(f"file:{copia.as_posix()}?mode=ro", uri=True)
        except sqlite3.Error:
            # Alguns bancos com WAL pendente recusam abertura somente
            # leitura. Sobre a cópia, abrir para escrita não custa nada —
            # o original continua intocado, e é ele que o hash prende.
            try:
                conexao = sqlite3.connect(str(copia))
            except sqlite3.Error as erro:
                banco.motivo = f"O SQLite recusou abrir '{caminho.name}': {erro}"
                yield banco
                return

        conexao.row_factory = sqlite3.Row
        banco.conexao = conexao

        try:
            banco.integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error as erro:
            banco.integridade = f"não verificável: {erro}"

        try:
            banco.modo_journal = str(conexao.execute("PRAGMA journal_mode").fetchone()[0])
        except sqlite3.Error:
            # Sem o modo, a ressalva do WAL nao e emitida -- e a escolha
            # segura aqui e nao afirmar. Um "-wal ausente" sobre banco que
            # talvez nem use WAL confundiria quem le o laudo.
            banco.modo_journal = ""

        try:
            banco.tabelas = tuple(
                linha[0]
                for linha in conexao.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            )
        except sqlite3.Error as erro:
            banco.motivo = f"O banco abriu, mas o esquema não pôde ser lido: {erro}"
            yield banco
            return

        # Banco corrompido continua legível: dado parcial declarado vale
        # mais que recusa total. A corrupção vai em `integridade`, e quem
        # monta o laudo é obrigado a olhar para ela.
        banco.legivel = True
        yield banco

    finally:
        if banco.conexao is not None:
            try:
                banco.conexao.close()
            except sqlite3.Error:
                pass
        if banco.copia is not None:
            _apagar_copia(banco.copia)


def _apagar_copia(copia: Path) -> None:
    """
    Remove a cópia de trabalho e os companheiros que foram com ela.

    A cópia é material derivado e descartável; o que vale está na
    aquisição selada. Deixá-la para trás encheria o disco de bancos
    duplicados sem que nada os reunisse a caso algum.
    """
    for alvo in [copia, *companheiros_de(copia)]:
        try:
            alvo.unlink()
        except OSError:
            continue
