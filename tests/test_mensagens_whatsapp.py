"""
Testes da leitura do msgstore.db do WhatsApp.

O bloco [3] guarda o defeito mais caro que este modulo poderia ter. O
WhatsApp trocou o modelo de dados por volta de 2021: antes, uma tabela
`messages` com o contato na propria linha; depois, `message` apontando
para `chat`, que aponta para `jid`. Um leitor que conheca so um dos dois e
encontre o outro NAO pode devolver zero mensagens -- zero mensagens num
aparelho com WhatsApp instalado e a conclusao negativa falsa mais cara que
esta ferramenta produziria. Ele tem de dizer qual esquema achou.

O bloco [4] guarda a segunda armadilha: mensagem de midia tem texto nulo,
porque o conteudo esta num arquivo e nao no banco. Descarta-la como
"mensagem vazia" apagaria da linha do tempo justamente o que costuma
interessar.

O bloco [5] cobre grupo: ali o interlocutor nao e a conversa, e quem
enviou. Confundir os dois atribuiria toda mensagem de grupo ao proprio
grupo, e ninguem saberia quem falou.
"""
import sqlite3
import sys
import tempfile
from datetime import timezone, timedelta
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.mensagens_whatsapp import COLUNAS, ler

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


EPOCH = 1787513890741  # 23/08/2026, em milissegundos


def banco_moderno(caminho: Path, mensagens):
    """
    Esquema pos-2021: message -> chat -> jid.

    `mensagens` e uma lista de dicionarios com de_mim, texto, tipo,
    jid_conversa, jid_remetente, assunto, momento.
    """
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE jid(_id INTEGER PRIMARY KEY, raw_string TEXT)")
    c.execute("CREATE TABLE chat(_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT)")
    c.execute(
        "CREATE TABLE message(_id INTEGER PRIMARY KEY, chat_row_id INTEGER, "
        "from_me INTEGER, text_data TEXT, message_type INTEGER, timestamp INTEGER, "
        "sender_jid_row_id INTEGER)"
    )
    jids = {}
    chats = {}
    for indice, m in enumerate(mensagens, 1):
        for jid in (m.get("jid_conversa"), m.get("jid_remetente")):
            if jid and jid not in jids:
                jids[jid] = len(jids) + 1
                c.execute("INSERT INTO jid VALUES (?, ?)", (jids[jid], jid))
        conversa = m.get("jid_conversa")
        if conversa not in chats:
            chats[conversa] = len(chats) + 1
            c.execute(
                "INSERT INTO chat VALUES (?, ?, ?)",
                (chats[conversa], jids.get(conversa), m.get("assunto")),
            )
        c.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                indice,
                chats[conversa],
                1 if m.get("de_mim") else 0,
                m.get("texto"),
                m.get("tipo", 0),
                m.get("momento", EPOCH + indice),
                jids.get(m.get("jid_remetente")),
            ),
        )
    c.commit()
    c.close()


def banco_legado(caminho: Path, mensagens):
    """Esquema pre-2021: uma tabela `messages`, com o contato na linha."""
    c = sqlite3.connect(caminho)
    c.execute(
        "CREATE TABLE messages(_id INTEGER PRIMARY KEY, key_remote_jid TEXT, "
        "key_from_me INTEGER, data TEXT, media_wa_type INTEGER, timestamp INTEGER, "
        "remote_resource TEXT)"
    )
    for indice, m in enumerate(mensagens, 1):
        c.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                indice,
                m.get("jid_conversa"),
                1 if m.get("de_mim") else 0,
                m.get("texto"),
                m.get("tipo", 0),
                m.get("momento", EPOCH + indice),
                m.get("jid_remetente"),
            ),
        )
    c.commit()
    c.close()


CONTATO = "5511988887777@s.whatsapp.net"
GRUPO = "120363000000000000@g.us"
MEMBRO = "5511911112222@s.whatsapp.net"


# ---------------------------------------------------------------------------
print("\n[1] O esquema moderno e lido")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_moderno(banco, [
        {"jid_conversa": CONTATO, "de_mim": False, "texto": "Oi, tudo bem?"},
        {"jid_conversa": CONTATO, "de_mim": True, "texto": "Tudo. Vamos combinar."},
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("as duas mensagens sao lidas", resultado.total == 2)
    checar("sem descarte", not resultado.descartes)
    checar("e sem recusa", not resultado.acesso_negado)

    recebida, enviada = resultado.registros
    checar("a recebida e marcada como recebida", recebida.campos["direcao"] == "Recebida")
    checar("com o numero do contato", recebida.campos["numero"] == "5511988887777")
    checar("e o conteudo intacto", recebida.campos["conteudo"] == "Oi, tudo bem?")
    checar("a enviada e marcada como enviada", enviada.campos["direcao"] == "Enviada")
    checar("a data e convertida do epoch em milissegundos",
           recebida.momento is not None and recebida.momento.year == 2026)
    checar("o registro carrega o identificador da linha de origem",
           recebida.linha_de_origem == 1)

# ---------------------------------------------------------------------------
print("\n[2] O esquema legado tambem")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_legado(banco, [
        {"jid_conversa": CONTATO, "de_mim": False, "texto": "Mensagem antiga"},
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("a mensagem do esquema antigo e lida", resultado.total == 1)
    checar("com o numero certo", resultado.registros[0].campos["numero"] == "5511988887777")
    checar("e o conteudo certo",
           resultado.registros[0].campos["conteudo"] == "Mensagem antiga")

# ---------------------------------------------------------------------------
print("\n[3] Esquema desconhecido NAO vira zero mensagens")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    c = sqlite3.connect(banco)
    c.execute("CREATE TABLE mensagens_de_uma_versao_futura(_id INTEGER, corpo TEXT)")
    c.execute("CREATE TABLE outra_coisa(_id INTEGER)")
    c.commit()
    c.close()

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("nao ha registro", resultado.total == 0)
    checar("mas o zero NAO passa por 'nao havia mensagens'", resultado.acesso_negado)

    explicacao = resultado.explicacao_do_vazio
    checar("a explicacao recusa a conclusao negativa",
           "diferente de não existir dado no aparelho" in explicacao)
    checar("e a recusa NOMEIA as tabelas encontradas",
           "mensagens_de_uma_versao_futura" in resultado.trecho_da_recusa)
    checar("dizendo que nada se pode afirmar",
           "Nada se pode afirmar" in resultado.trecho_da_recusa)

with tempfile.TemporaryDirectory() as tmp:
    # Arquivo que nem banco e: a recusa vem do leitor de SQLite, e chega
    # aqui como recusa, nao como ausencia.
    banco = Path(tmp) / "msgstore.db"
    banco.write_text("isto nao e um banco", encoding="utf-8")
    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("arquivo que nao e banco tambem e recusa", resultado.acesso_negado)
    checar("com o motivo do leitor de SQLite", "é outra coisa" in resultado.trecho_da_recusa)

# ---------------------------------------------------------------------------
print("\n[4] Midia nao e mensagem vazia")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_moderno(banco, [
        {"jid_conversa": CONTATO, "de_mim": False, "texto": None, "tipo": 1},
        {"jid_conversa": CONTATO, "de_mim": False, "texto": None, "tipo": 2},
        {"jid_conversa": CONTATO, "de_mim": True, "texto": None, "tipo": 77},
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("as tres entram, nenhuma e descartada", resultado.total == 3)
    conteudos = [r.campos["conteudo"] for r in resultado.registros]
    checar("a imagem aparece como imagem", "(imagem)" in conteudos)
    checar("o audio como audio", "(áudio)" in conteudos)
    checar("e o tipo desconhecido traz o CODIGO, nao um rotulo inventado",
           "(tipo 77)" in conteudos)

# ---------------------------------------------------------------------------
print("\n[5] Em grupo, o interlocutor e quem enviou")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_moderno(banco, [
        {
            "jid_conversa": GRUPO,
            "jid_remetente": MEMBRO,
            "de_mim": False,
            "texto": "Falei no grupo",
            "assunto": "Obra do galpao",
        },
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    registro = resultado.registros[0]
    checar("o numero e o do MEMBRO que enviou",
           registro.campos["numero"] == "5511911112222")
    checar("e nao o do grupo",
           registro.campos["numero"] != "120363000000000000")
    checar("a conversa e identificada pelo assunto do grupo",
           registro.campos["conversa"] == "Obra do galpao")

# ---------------------------------------------------------------------------
print("\n[6] Registro sem data e sem conteudo e descartado, nunca em silencio")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_moderno(banco, [
        {"jid_conversa": CONTATO, "de_mim": False, "texto": "vale", "momento": EPOCH},
        {"jid_conversa": CONTATO, "de_mim": False, "texto": None, "momento": 0, "tipo": 0},
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("a mensagem boa entra", resultado.total == 1)
    checar("a vazia vira descarte CONTADO", len(resultado.descartes) == 1)
    checar("com o motivo escrito",
           "sem data e sem conteúdo" in resultado.descartes[0].motivo)
    checar("e apontando o registro de origem",
           resultado.descartes[0].linha_de_origem == 2)

# ---------------------------------------------------------------------------
print("\n[7] O fuso declarado acompanha as datas")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_moderno(banco, [{"jid_conversa": CONTATO, "de_mim": False, "texto": "oi"}])

    brasilia = timezone(timedelta(hours=-3))
    resultado = ler(banco, Path(tmp) / "trabalho", fuso=brasilia)
    checar("o fuso e declarado no resultado", resultado.fuso_declarado != "")
    checar("a data vem no fuso pedido",
           resultado.registros[0].momento.utcoffset() == timedelta(hours=-3))

    checar("as colunas do artefato estao definidas", len(COLUNAS) == 8)
    checar("e o registro preenche todas",
           all(c in resultado.registros[0].campos or c == "momento" for c in COLUNAS))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
