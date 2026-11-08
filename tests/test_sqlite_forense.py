"""
Testes da abertura forense de banco SQLite.

O bloco [2] guarda a armadilha central, e ela e contraintuitiva. A leitura
segura de um banco parece pedir `immutable=1`, que promete nao tocar no
arquivo. O preco e que o WAL e inteiramente ignorado -- e o WAL e onde
estao os registros mais recentes, os da vespera da coleta. Neste teste,
o banco tem a propria TABELA criada dentro do WAL: aberto com
`immutable=1` ele responde "no such table". Nao e dado a menos, e o banco
inteiro invisivel.

A saida e ler sobre COPIA. O original nao e tocado, o hash e calculado
antes, e a copia pode ser aberta do jeito que o SQLite precisa.

O bloco [1] guarda a outra metade: o original tem de sair da leitura com o
mesmo hash com que entrou. Abrir um SQLite com WAL pendente faz o proprio
SQLite incorporar o WAL ao arquivo -- se a leitura tocasse o original, a
aquisicao deixaria de conferir por causa de um ato de exame.
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao
from core.hashing import calcular_sha256, gerar_manifesto
from core.sqlite_forense import abrir, dentro_de_aquisicao_selada, parece_sqlite

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar_banco(caminho: Path, com_wal_pendente=False):
    """
    Cria um banco. Com `com_wal_pendente`, a conexao fica ABERTA e o
    conteudo permanece no -wal, sem ser incorporado ao arquivo principal.
    Devolve a conexao (que o chamador precisa fechar) ou None.
    """
    conexao = sqlite3.connect(caminho)
    conexao.execute("PRAGMA journal_mode=WAL")
    conexao.execute("CREATE TABLE mensagem(id INTEGER, texto TEXT)")
    conexao.execute("INSERT INTO mensagem VALUES (1, 'consolidada')")
    conexao.commit()
    if com_wal_pendente:
        conexao.execute("INSERT INTO mensagem VALUES (2, 'somente no wal')")
        conexao.commit()
        return conexao
    conexao.close()
    return None


# ---------------------------------------------------------------------------
print("\n[1] O original sai da leitura como entrou")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    origem = Path(tmp) / "evidencia"
    origem.mkdir()
    banco = origem / "msgstore.db"
    conexao = montar_banco(banco, com_wal_pendente=True)

    antes = calcular_sha256(banco)
    trabalho = Path(tmp) / "trabalho"

    with abrir(banco, trabalho) as aberto:
        checar("o banco abre", aberto.legivel)
        checar("sem motivo de recusa", aberto.motivo == "")
        checar("o hash do original e registrado", aberto.sha256_original == antes)
        checar("a copia existe durante a leitura", aberto.copia.is_file())
        checar("o wal acompanhou", aberto.tem_wal)
        checar("e por isso nao ha ressalva de wal", aberto.ressalva_do_wal == "")
        linhas = aberto.consultar("SELECT texto FROM mensagem ORDER BY id")
        textos = [linha[0] for linha in linhas]

    # Medido ANTES de fechar a conexao de origem, e a ordem importa:
    # fechar uma conexao SQLite com WAL pendente dispara o checkpoint e
    # ALTERA o arquivo principal. Foi o proprio SQLite fazendo o que faz --
    # e e exatamente por isso que a leitura forense nunca abre o original.
    depois = calcular_sha256(banco)
    conexao.close()

    checar("o original NAO foi alterado pela leitura", depois == antes)
    checar("a copia de trabalho e apagada ao final", not aberto.copia.exists())
    checar("o registro consolidado e lido", "consolidada" in textos)
    checar("e o que estava so no wal TAMBEM", "somente no wal" in textos)

# ---------------------------------------------------------------------------
print("\n[2] O modo que 'nao toca no arquivo' esconde o banco inteiro")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    origem = Path(tmp) / "evidencia"
    origem.mkdir()
    banco = origem / "msgstore.db"
    # A TABELA e criada e fica no WAL: nada dela chegou ao arquivo principal.
    conexao = sqlite3.connect(banco)
    conexao.execute("PRAGMA journal_mode=WAL")
    conexao.execute("CREATE TABLE mensagem(id INTEGER, texto TEXT)")
    conexao.execute("INSERT INTO mensagem VALUES (1, 'no wal')")
    conexao.commit()

    copia = Path(tmp) / "copia.db"
    copia.write_bytes(banco.read_bytes())
    Path(str(copia) + "-wal").write_bytes(Path(str(banco) + "-wal").read_bytes())

    # Como o codigo NAO faz: immutable promete nao tocar, e cobra o WAL.
    imutavel = sqlite3.connect(f"file:{copia.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        imutavel.execute("SELECT count(*) FROM mensagem").fetchone()
        viu_a_tabela = True
    except sqlite3.Error:
        viu_a_tabela = False
    imutavel.close()
    checar("com immutable, a tabela some do banco", not viu_a_tabela)

    # Como o codigo faz: copia aberta em modo que le o WAL.
    with abrir(banco, Path(tmp) / "trabalho") as aberto:
        linhas = aberto.consultar("SELECT texto FROM mensagem")
    conexao.close()
    checar("sobre a copia, o registro do wal aparece", [l[0] for l in linhas] == ["no wal"])

# ---------------------------------------------------------------------------
print("\n[3] Ausencia do wal e declarada, nao suposta")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "sem_wal.db"
    montar_banco(banco)  # fecha limpo: o -wal e removido pelo proprio SQLite

    with abrir(banco, Path(tmp) / "trabalho") as aberto:
        checar("o banco abre normalmente", aberto.legivel)
        checar("o wal nao acompanhou", not aberto.tem_wal)
        checar("mas o banco USA wal, e por isso a falta importa", aberto.usa_wal)
        ressalva = aberto.ressalva_do_wal
    checar("e a ressalva existe", bool(ressalva))
    checar(
        "dizendo que NAO SE PODE determinar se havia registro pendente",
        "não é possível determinar" in ressalva,
    )

with tempfile.TemporaryDirectory() as tmp:
    # Banco em modo `delete`, o padrao do SQLite e o que o provedor de
    # telefonia do Android usa: NUNCA teve wal. Emitir a ressalva aqui
    # seria declarar limitacao que nao existe -- apareceu contra o banco
    # real do emulador, em 30/08/2026, e e o defeito de afirmar sem
    # verificar virado do avesso.
    banco = Path(tmp) / "modo_delete.db"
    conexao = sqlite3.connect(banco)
    conexao.execute("CREATE TABLE t(a)")
    conexao.commit()
    conexao.close()

    with abrir(banco, Path(tmp) / "trabalho") as aberto:
        checar("o modo de journal e lido do cabecalho", aberto.modo_journal == "delete")
        checar("banco em modo delete nao usa wal", not aberto.usa_wal)
        checar("e por isso NAO recebe a ressalva do wal", aberto.ressalva_do_wal == "")

# ---------------------------------------------------------------------------
print("\n[4] Cada recusa tem seu motivo, e nenhuma e silenciosa")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    trabalho = Path(tmp) / "trabalho"

    with abrir(Path(tmp) / "nao_existe.db", trabalho) as aberto:
        checar("arquivo inexistente nao e legivel", not aberto.legivel)
        checar("e o motivo diz que nao existe", "não existe" in aberto.motivo)

    outro = Path(tmp) / "disfarcado.db"
    outro.write_text("isto aqui e texto puro, nao um banco", encoding="utf-8")
    checar("a assinatura distingue banco de outra coisa", not parece_sqlite(outro))
    with abrir(outro, trabalho) as aberto:
        checar("arquivo que nao e SQLite nao e legivel", not aberto.legivel)
        checar(
            "e o motivo diz que o arquivo existe e e outra coisa",
            "é outra coisa" in aberto.motivo,
        )

    valido = Path(tmp) / "valido.db"
    montar_banco(valido)
    checar("e reconhece o banco de verdade", parece_sqlite(valido))

# ---------------------------------------------------------------------------
print("\n[5] A copia de trabalho nao nasce dentro do que foi selado")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_001", "Android")
    banco = aquisicao / "msgstore.db"
    montar_banco(banco)
    gerar_manifesto(aquisicao)

    checar("a aquisicao selada e reconhecida", dentro_de_aquisicao_selada(aquisicao))
    checar(
        "e uma subpasta dela tambem",
        dentro_de_aquisicao_selada(aquisicao / "qualquer" / "profunda"),
    )
    checar(
        "pasta fora do selo nao e confundida",
        not dentro_de_aquisicao_selada(Path(tmp) / "trabalho"),
    )

    antes = calcular_sha256(banco)
    # Tentar trabalhar DENTRO da aquisicao selada: a leitura tem de recusar.
    with abrir(banco, aquisicao / "trabalho") as aberto:
        checar("a leitura recusa trabalhar dentro do selo", not aberto.legivel)
        checar(
            "explicando que acusaria arquivo acrescentado",
            "arquivo acrescentado" in aberto.motivo,
        )
    checar("e nada foi gravado na aquisicao", not (aquisicao / "trabalho").exists())
    checar("o banco selado segue intacto", calcular_sha256(banco) == antes)

    # Fora do selo, o mesmo banco abre.
    with abrir(banco, Path(tmp) / "trabalho") as aberto:
        checar("fora do selo, a leitura acontece", aberto.legivel)

# ---------------------------------------------------------------------------
print("\n[6] Integridade e esquema chegam a quem monta o laudo")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "com_tabelas.db"
    conexao = sqlite3.connect(banco)
    conexao.execute("CREATE TABLE message(id INTEGER)")
    conexao.execute("CREATE TABLE chat(id INTEGER)")
    conexao.commit()
    conexao.close()

    with abrir(banco, Path(tmp) / "trabalho") as aberto:
        checar("a integridade e verificada", aberto.integra)
        checar("as tabelas sao listadas", set(aberto.tabelas) == {"message", "chat"})
        checar("o esquema esperado e reconhecido", aberto.tem_tabelas("message", "chat"))
        checar(
            "e o esquema de outra versao NAO e dado como presente",
            not aberto.tem_tabelas("messages"),
        )
        checar("consulta em tabela inexistente nao derruba o exame",
               aberto.consultar("SELECT name FROM sqlite_master") != [])

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
