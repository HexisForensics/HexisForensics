"""
Testes do que a primeira leitura de um `msgstore.db` REAL revelou.

Em 09/10/2026 o leitor abriu, pela primeira vez, um banco produzido pelo
proprio WhatsApp (versao 2.26.40.72, emulador com root). Tres defeitos
apareceram na primeira consulta, e nenhum banco sintetico os mostraria,
porque o sintetico era escrito por quem escreveu o leitor:

1. MENSAGEM FANTASMA. A tabela `message` traz uma linha-marcador (`_id=1`,
   `chat_row_id=-1`, tudo nulo). O leitor a apresentava como "mensagem
   recebida, sem data, (tipo nao informado)".

2. O TELEFONE SUMIU. A conversa vinha como `35614506377338@lid`, um
   identificador opaco, e o leitor o recortava e exibia na coluna NUMERO.
   Nao e telefone de ninguem. A tabela `jid_map` do proprio banco e que o
   liga ao numero.

3. MENSAGEM DE SISTEMA saia como "(tipo 7)".

O esquema daqui reproduz o que o banco real tinha: `jid_map`,
`message_media`, `message_system` e o `wa.db` ao lado.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.mensagens_whatsapp import ler  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


EPOCH = 1791557379215  # 09/10/2026

LID_JOAO = "35614506377338@lid"
TEL_JOAO = "5511922223333@s.whatsapp.net"
LID_SEM_MAPA = "999999999999999@lid"
GRUPO = "120363000000000000@g.us"
LID_MARIA = "221216988225728@lid"
TEL_MARIA = "5511911112222@s.whatsapp.net"


def montar(pasta: Path, com_agenda=True, com_midia=True, com_mapa=True):
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "msgstore.db"
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE jid(_id INTEGER PRIMARY KEY, raw_string TEXT)")
    c.execute("CREATE TABLE chat(_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT)")
    c.execute(
        "CREATE TABLE message(_id INTEGER PRIMARY KEY, chat_row_id INTEGER, from_me INTEGER, "
        "sender_jid_row_id INTEGER, message_type INTEGER, timestamp INTEGER, text_data TEXT)"
    )
    c.execute("CREATE TABLE message_system(message_row_id INTEGER, action_type INTEGER)")
    jids = {1: LID_JOAO, 2: TEL_JOAO, 3: LID_SEM_MAPA, 4: GRUPO, 5: LID_MARIA, 6: TEL_MARIA}
    c.executemany("INSERT INTO jid VALUES (?, ?)", jids.items())
    c.executemany("INSERT INTO chat VALUES (?, ?, ?)",
                  [(1, 1, None), (2, 3, None), (3, 4, "Grupo da Família")])
    if com_mapa:
        c.execute("CREATE TABLE jid_map(lid_row_id INTEGER, jid_row_id INTEGER, sort_id INTEGER)")
        c.executemany("INSERT INTO jid_map VALUES (?, ?, 0)", [(1, 2), (5, 6)])
    mensagens = [
        (1, -1, 0, None, None, None, None),                # o marcador do WhatsApp
        (2, 1, 1, 0, 7, EPOCH, None),                      # mensagem de sistema
        (3, 1, 0, 0, 0, EPOCH + 1000, "Oi, tudo bem?"),    # recebida do Joao (via LID)
        (4, 1, 1, 0, 0, EPOCH + 2000, "Tudo, e você?"),    # enviada ao Joao
        (5, 1, 0, 0, 1, EPOCH + 3000, None),               # foto com legenda
        (6, 2, 0, 0, 0, EPOCH + 4000, "quem é?"),          # LID sem correspondência
        (7, 3, 0, 5, 0, EPOCH + 5000, "bom dia grupo"),    # Maria, no grupo
        (8, 3, 1, 0, 0, EPOCH + 6000, "bom dia"),          # eu, no grupo
        (9, 1, 0, 0, 2, EPOCH + 7000, None),               # áudio não baixado
    ]
    c.executemany("INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?)", mensagens)
    c.execute("INSERT INTO message_system VALUES (2, 67)")
    if com_midia:
        # `media_name` de proposito ausente: o esquema varia, e o leitor
        # precisa consultar so as colunas que existem.
        c.execute(
            "CREATE TABLE message_media(message_row_id INTEGER, file_path TEXT, "
            "media_caption TEXT, mime_type TEXT, file_size INTEGER, file_hash TEXT)"
        )
        # O hash como o banco real o guardava: SHA-256 em base64.
        c.execute(
            "INSERT INTO message_media VALUES (5, ?, 'olha a foto', 'image/jpeg', 21832, ?)",
            ("Media/WhatsApp Images/IMG-20261009-WA0001.jpg",
             "/qHzr7ImTS5u5rwDpGZSNL0uuVShj355R9PNezrdEoE="),
        )
        c.execute(
            "INSERT INTO message_media VALUES (9, NULL, NULL, 'audio/ogg; codecs=opus', 0, "
            "'isto-nao-e-um-hash')"
        )
    c.commit()
    c.close()

    if com_agenda:
        a = sqlite3.connect(pasta / "wa.db")
        a.execute("CREATE TABLE wa_contacts(jid TEXT, display_name TEXT, wa_name TEXT)")
        a.execute("INSERT INTO wa_contacts VALUES (?, 'Joao da Silva', NULL)", (TEL_JOAO,))
        a.execute("INSERT INTO wa_contacts VALUES (?, NULL, 'Maria ~apelido')", (TEL_MARIA,))
        a.commit()
        a.close()
    return caminho


def por_id(resultado):
    return {r.linha_de_origem: r for r in resultado.registros}


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    resultado = ler(montar(tmp / "a"), tmp / "trabalho_a")
    m = por_id(resultado)

    # -----------------------------------------------------------------------
    print("\n[1] O marcador interno nao vira mensagem")
    # -----------------------------------------------------------------------
    checar("a leitura nao e recusada", not resultado.acesso_negado)
    checar("o marcador NAO esta entre os registros", 1 not in m)
    checar("oito mensagens reais, nem uma a mais", resultado.total == 8)
    checar("e o marcador e contado como descarte, com o motivo",
           len(resultado.descartes) == 1 and "marcador interno" in resultado.descartes[0].motivo)

    # -----------------------------------------------------------------------
    print("\n[2] O identificador opaco e resolvido para o telefone")
    # -----------------------------------------------------------------------
    checar("recebida via @lid: a coluna NUMERO traz o telefone",
           m[3].campos["numero"] == "5511922223333")
    checar("nunca o identificador opaco", "35614506377338" not in m[3].campos["numero"])
    checar("o identificador continua integro na coluna da conversa",
           m[3].campos["conversa"] == LID_JOAO)
    checar("enviada: o numero e o do DESTINATARIO", m[4].campos["numero"] == "5511922223333")
    checar("@lid sem correspondencia NAO vira numero",
           "999999999999999" not in m[6].campos["numero"])
    checar("a coluna diz que o telefone nao consta",
           "não consta no banco" in m[6].campos["numero"])

    # -----------------------------------------------------------------------
    print("\n[3] O nome vem do wa.db que mora ao lado")
    # -----------------------------------------------------------------------
    checar("nome da agenda do aparelho", m[3].campos["contato"] == "Joao da Silva")
    checar("na falta dele, o nome que o contato usa no WhatsApp",
           m[7].campos["contato"] == "Maria ~apelido")
    checar("contato que nao esta na agenda fica sem nome, sem invencao",
           m[6].campos["contato"] == "")

    # -----------------------------------------------------------------------
    print("\n[4] Grupo: quem falou e o remetente, resolvido tambem")
    # -----------------------------------------------------------------------
    checar("o numero e o de quem enviou, nao o do grupo",
           m[7].campos["numero"] == "5511911112222")
    checar("a conversa e o nome do grupo", m[7].campos["conversa"] == "Grupo da Família")
    checar("mensagem MINHA no grupo nao recebe numero de ninguem",
           m[8].campos["numero"] == "" and m[8].campos["contato"] == "")

    # -----------------------------------------------------------------------
    print("\n[5] Midia: legenda, arquivo e o que nao foi baixado")
    # -----------------------------------------------------------------------
    checar("a legenda da foto e o conteudo", m[5].campos["conteudo"] == "olha a foto")
    checar("o caminho do arquivo no aparelho vai na coluna do anexo",
           "IMG-20261009-WA0001.jpg" in m[5].campos["anexo"])
    checar("com o tipo declarado", "image/jpeg" in m[5].campos["anexo"])
    checar("e o SHA-256 que o proprio WhatsApp registrou, em hexadecimal",
           "fea1f3afb2264d2e6ee6bc03a4665234bd2eb954a18f7e7947d3cd7b3add1281"
           in m[5].campos["anexo"])
    checar("valor que nao e um SHA-256 nao e exibido como hash",
           "SHA-256" not in m[9].campos["anexo"])
    checar("audio sem arquivo: o anexo DIZ que nao foi baixado",
           "não baixado" in m[9].campos["anexo"])
    checar("e o conteudo diz o que a mensagem era", m[9].campos["conteudo"] == "(áudio)")
    checar("mensagem de texto nao tem anexo", m[3].campos["anexo"] == "")

    # -----------------------------------------------------------------------
    print("\n[6] Mensagem de sistema e nomeada, com o codigo verificavel")
    # -----------------------------------------------------------------------
    checar("o tipo e nomeado", m[2].campos["tipo"] == "mensagem de sistema")
    checar("e o codigo da acao acompanha, sem significado inventado",
           m[2].campos["conteudo"] == "(mensagem de sistema, ação 67)")

    # -----------------------------------------------------------------------
    print("\n[7] O que falta no banco e DITO, e nao derruba a leitura")
    # -----------------------------------------------------------------------
    sem_agenda = por_id(ler(montar(tmp / "b", com_agenda=False), tmp / "trabalho_b"))
    checar("sem wa.db: as mensagens sao lidas do mesmo jeito", len(sem_agenda) == 8)
    checar("e a coluna do contato diz que a agenda nao foi coletada",
           "não coletada" in sem_agenda[3].campos["contato"])

    sem_midia = por_id(ler(montar(tmp / "c", com_midia=False), tmp / "trabalho_c"))
    checar("sem tabela de midia: as mensagens sao lidas", len(sem_midia) == 8)
    checar("e a foto continua na linha do tempo, pelo tipo",
           sem_midia[5].campos["conteudo"] == "(imagem)")

    sem_mapa = por_id(ler(montar(tmp / "d", com_mapa=False), tmp / "trabalho_d"))
    checar("sem jid_map: nenhum @lid e apresentado como telefone",
           "não consta no banco" in sem_mapa[3].campos["numero"])

    antes = (tmp / "a" / "msgstore.db").read_bytes()
    ler(tmp / "a" / "msgstore.db", tmp / "trabalho_e")
    checar("o banco adquirido nao e alterado pela leitura",
           (tmp / "a" / "msgstore.db").read_bytes() == antes)


print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
