"""
WhatsApp do iPhone, como o banco real se apresentou (iPhone 11, iOS 18.6.2,
31/10/2026): registros que o próprio WhatsApp gera, localização com
coordenadas na tabela de mídia e um tipo que a suíte não conhece.

No teste real, a criação de um grupo apareceu como bloco de JSON e com um
"remetente" sem sentido; a localização, só como "(localização)".
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.mensagens_ios import ler_whatsapp  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


APPLE = 815_000_000.0  # segundos desde 2001-01-01 (2026)

with tempfile.TemporaryDirectory() as temporario:
    pasta = Path(temporario)
    caminho = pasta / "ChatStorage.sqlite"
    banco = sqlite3.connect(caminho)
    banco.executescript("""
        CREATE TABLE ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY, ZCONTACTJID TEXT, ZPARTNERNAME TEXT);
        CREATE TABLE ZWAGROUPMEMBER (Z_PK INTEGER PRIMARY KEY, ZMEMBERJID TEXT, ZCONTACTNAME TEXT);
        CREATE TABLE ZWAMEDIAITEM (Z_PK INTEGER PRIMARY KEY, ZMEDIALOCALPATH TEXT, ZTITLE TEXT,
            ZLATITUDE REAL, ZLONGITUDE REAL);
        CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY, ZMESSAGEDATE REAL, ZISFROMME INTEGER,
            ZTEXT TEXT, ZMESSAGETYPE INTEGER, ZCHATSESSION INTEGER, ZGROUPMEMBER INTEGER,
            ZMEDIAITEM INTEGER, ZPUSHNAME TEXT, ZGROUPEVENTTYPE INTEGER);
        INSERT INTO ZWACHATSESSION VALUES (1, '100000000000001@lid', 'Fulano'),
            (2, '120363000000000000@g.us', 'Teste');
        INSERT INTO ZWAMEDIAITEM VALUES (1, NULL, NULL, -23.550520, -46.633308),
            (2, NULL, NULL, 0, 0), (3, NULL, NULL, NULL, NULL);
    """)
    linhas = [
        (1, APPLE, 0, None, 10, 1, None, None, None, 2),
        (2, APPLE + 1, 1, "Oi", 0, 1, None, None, None, 0),
        (3, APPLE + 2, 1, None, 5, 1, None, 1, None, 0),
        (4, APPLE + 3, 1, None, 5, 1, None, 2, None, 0),
        (5, APPLE + 4, 0, '{"is_open_group":true}', 6, 2, None, None, "CM3jl9cGIAA=", 12),
        (6, APPLE + 5, 1, None, 76, 2, None, 3, None, 0),
    ]
    banco.executemany("INSERT INTO ZWAMESSAGE VALUES (?,?,?,?,?,?,?,?,?,?)", linhas)
    banco.commit()
    banco.close()

    resultado = ler_whatsapp(caminho, pasta / "trabalho")
    registros = {r.linha_de_origem: r.campos for r in resultado.registros}

    print("\n[1] Registros que o próprio WhatsApp gera")
    aviso, grupo = registros[1], registros[5]
    checar("aviso do sistema não vira 'Recebida' nem mensagem digitada",
           aviso["direcao"] == "Sistema" and "não é mensagem digitada" in aviso["conteudo"])
    checar("criação de grupo: sem o JSON técnico e sem remetente inventado",
           "{" not in grupo["conteudo"] and grupo["contato"] == ""
           and "código de evento 12" in grupo["conteudo"] and grupo["conversa"] == "Teste")

    print("\n[2] Localização compartilhada")
    lugar = registros[3]
    checar("coordenadas no conteúdo, com sinal (sul e oeste negativos)",
           "-23.550520, -46.633308" in lugar["conteudo"])
    checar("e o link para o mapa", lugar.get("mapa", "").endswith("q=-23.550520,-46.633308"))
    checar("coordenada 0,0 não vira lugar", "mapa" not in registros[4]
           and registros[4]["conteudo"] == "(localização)")

    print("\n[3] Tipo desconhecido")
    checar("diz que não reconhece e que não há texto nem mídia, sem chutar o que é",
           registros[6]["conteudo"] == "(tipo 76 não reconhecido; sem texto nem mídia)")

    print("\n[4] Mensagem comum continua igual")
    checar("texto enviado", registros[2]["direcao"] == "Enviada" and registros[2]["conteudo"] == "Oi")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
