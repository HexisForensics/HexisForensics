"""
Testes da decifragem do backup do WhatsApp com chave de 64 digitos.

A decifragem so vale pelo que a conferencia de autenticidade (AES-GCM)
sustenta. O que estes testes travam:

- chave errada, digito trocado ou arquivo alterado NUNCA devolvem banco;
- o banco em claro nunca e gravado dentro da aquisicao selada;
- o decifrado carrega a procedencia que o liga ao arquivo cifrado selado;
- a decifragem fica registrada no caso, com a chave, para ser repetivel.

O arquivo cifrado aqui e montado pelo proprio teste, com o formato que a
decifragem espera. Isso prova a conta e as recusas; NAO prova que o formato
e o que o WhatsApp grava -- isso so um backup real demonstra.
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import zlib
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import conferir_manifesto, gerar_manifesto  # noqa: E402
from core.whatsapp_crypt15 import (  # noqa: E402
    ErroDeDecifragem,
    decifrar,
    derivar_chave,
    normalizar_chave,
)
from services.decifragem_service import decifrar_whatsapp  # noqa: E402
from services.relatorio_service import levantar_artefatos  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def recusa(funcao):
    """A mensagem da recusa, ou vazio se a funcao NAO recusou."""
    try:
        funcao()
    except ErroDeDecifragem as erro:
        return str(erro)
    return ""


def campo(numero: int, dado: bytes) -> bytes:
    return bytes([(numero << 3) | 2, len(dado)]) + dado


def montar_crypt15(banco: bytes, chave_raiz: bytes, com_md5=True, com_recursos=True) -> bytes:
    vetor = os.urandom(16)
    # cabecalho protobuf: um inteiro, o vetor dentro de uma mensagem aninhada e um texto
    cabecalho = b"\x08\x01" + campo(3, campo(1, vetor)) + campo(4, b"2.26.39.79")
    cifrado = AESGCM(derivar_chave(chave_raiz)).encrypt(vetor, zlib.compress(banco), None)
    prefixo = bytes([len(cabecalho)]) + (b"\x01" if com_recursos else b"") + cabecalho
    corpo = prefixo + cifrado
    return corpo + (hashlib.md5(corpo).digest() if com_md5 else b"")


def montar_banco(caminho: Path) -> bytes:
    conexao = sqlite3.connect(caminho)
    conexao.executescript(
        "CREATE TABLE jid (_id INTEGER PRIMARY KEY, raw_string TEXT);"
        "CREATE TABLE chat (_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT);"
        "CREATE TABLE message (_id INTEGER PRIMARY KEY, chat_row_id INTEGER, from_me INTEGER,"
        " sender_jid_row_id INTEGER, timestamp INTEGER, message_type INTEGER, text_data TEXT);"
        "INSERT INTO jid VALUES (1, '5511911112222@s.whatsapp.net');"
        "INSERT INTO chat VALUES (1, 1, NULL);"
        "INSERT INTO message VALUES (1, 1, 0, 0, 1756000000000, 0, 'mensagem do backup cifrado');"
        "INSERT INTO message VALUES (2, 1, 1, 0, 1756000060000, 0, 'resposta enviada');"
    )
    conexao.commit()
    conexao.close()
    return caminho.read_bytes()


CHAVE_TEXTO = "0123 4567 89ab cdef 0123 4567 89ab cdef 0123 4567 89ab cdef 0123 4567 89ab cdef"
CHAVE = normalizar_chave(CHAVE_TEXTO)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    banco = montar_banco(tmp / "original.db")

    # -----------------------------------------------------------------------
    print("\n[1] A chave como o examinador a digita")
    # -----------------------------------------------------------------------
    checar("grupos de quatro com espacos sao aceitos", len(CHAVE) == 32)
    checar("hifens e quebras de linha tambem",
           normalizar_chave(CHAVE_TEXTO.replace(" ", "-\n")) == CHAVE)
    checar("um digito a menos e recusado DIZENDO quantos foram digitados",
           "63" in recusa(lambda: normalizar_chave(CHAVE_TEXTO[:-1])))
    checar("caractere fora de 0-9 a-f e recusado nomeando o caractere",
           "g" in recusa(lambda: normalizar_chave("g" + CHAVE_TEXTO[1:])))

    # -----------------------------------------------------------------------
    print("\n[2] Decifra o que foi cifrado com a chave -- e so isso")
    # -----------------------------------------------------------------------
    arquivo = tmp / "msgstore.db.crypt15"
    arquivo.write_bytes(montar_crypt15(banco, CHAVE))
    checar("devolve exatamente o banco original", decifrar(arquivo, CHAVE) == banco)

    for nome, opcoes in (("sem o MD5 final", {"com_md5": False}),
                         ("sem a tabela de recursos", {"com_recursos": False})):
        variante = tmp / f"variante_{len(nome)}.db.crypt15"
        variante.write_bytes(montar_crypt15(banco, CHAVE, **opcoes))
        checar(f"a disposicao {nome} tambem abre", decifrar(variante, CHAVE) == banco)

    trocada = bytearray(CHAVE)
    trocada[5] ^= 0x01  # um unico bit: o equivalente a um digito anotado errado
    motivo = recusa(lambda: decifrar(arquivo, bytes(trocada)))
    checar("um digito trocado na chave: NADA e devolvido", bool(motivo))
    checar("e a recusa fala em conferencia de autenticidade", "autenticidade" in motivo)

    adulterado = tmp / "adulterado.db.crypt15"
    bruto = bytearray(arquivo.read_bytes())
    bruto[len(bruto) // 2] ^= 0xFF
    adulterado.write_bytes(bytes(bruto))
    checar("arquivo alterado em um byte: NADA e devolvido, mesmo com a chave certa",
           bool(recusa(lambda: decifrar(adulterado, CHAVE))))

    crypt14 = tmp / "msgstore.db.crypt14"
    crypt14.write_bytes(arquivo.read_bytes())
    checar("backup .crypt14 e recusado explicando por que a chave nao serve",
           "área privada" in recusa(lambda: decifrar(crypt14, CHAVE)))

    lixo = tmp / "lixo.db.crypt15"
    lixo.write_bytes(os.urandom(4096))
    checar("arquivo que nao e crypt15 e recusado, sem excecao solta",
           bool(recusa(lambda: decifrar(lixo, CHAVE))))

    # -----------------------------------------------------------------------
    print("\n[3] Na aquisicao: o claro fica FORA do selo, com procedencia")
    # -----------------------------------------------------------------------
    raiz = tmp / "extracoes"
    aquisicao = criar_pasta_aquisicao(raiz, "CASO_400", "Android", datetime(2026, 10, 1, 9, 0, 0))
    pasta_bancos = aquisicao / "whatsapp" / "WhatsApp_Databases_legado" / "Databases"
    pasta_bancos.mkdir(parents=True)
    (pasta_bancos / "msgstore.db.crypt15").write_bytes(montar_crypt15(banco, CHAVE))
    # Um backup antigo, de antes de a chave ser ativada: cifrado com OUTRA chave.
    (pasta_bancos / "msgstore-2026-09-01.1.db.crypt15").write_bytes(
        montar_crypt15(banco, os.urandom(32))
    )
    gerar_manifesto(aquisicao)

    antes = [a for a in levantar_artefatos(aquisicao) if a.chave == "whatsapp"]
    checar("antes de decifrar, o WhatsApp consta como NAO coletado",
           len(antes) == 1 and not antes[0].presente)

    errada = decifrar_whatsapp(aquisicao, CHAVE_TEXTO.replace("0", "1", 1))
    checar("chave errada: erro, e nenhuma pasta de decifrados com banco",
           bool(errada.erro) and not list(raiz.rglob("msgstore.db")))

    resultado = decifrar_whatsapp(aquisicao, CHAVE_TEXTO)
    checar("com a chave certa, o backup principal e decifrado",
           not resultado.erro and resultado.banco_principal and len(resultado.decifrados) == 1)
    checar("o backup antigo, de outra chave, e LISTADO como nao decifrado",
           len(resultado.falhas) == 1 and "2026-09-01" in resultado.falhas[0])
    claro = raiz / "CASO_400" / "decifrados" / aquisicao.name / "com.whatsapp" / "databases" / "msgstore.db"
    checar("o banco em claro fica em <caso>/decifrados/<aquisicao>",
           claro.is_file() and claro.read_bytes() == banco)
    checar("NADA foi gravado dentro da aquisicao: ela continua integra",
           conferir_manifesto(aquisicao).integro)
    checar("a procedencia fica ao lado do banco",
           Path(str(claro) + ".procedencia.json").is_file())

    depois = [a for a in levantar_artefatos(aquisicao) if a.chave == "whatsapp"]
    checar("os leitores de conteudo passam a encontrar as mensagens",
           len(depois) == 1 and depois[0].total == 2)
    checar("o artefato se declara DECIFRADO, e aponta o arquivo cifrado de origem",
           "decifrado" in depois[0].titulo
           and "msgstore.db.crypt15" in depois[0].caminho_relativo)
    checar("o que se confere contra o selo e o arquivo CIFRADO",
           depois[0].confere_com_o_selo is True)

    complementos = [c for c in (raiz / "CASO_400" / "complementos").glob("*.txt")
                    if c.name != "INDICE.txt"]
    texto = complementos[0].read_text(encoding="utf-8") if complementos else ""
    checar("a decifragem vira complemento ao caso", len(complementos) == 1)
    checar("com a chave, para ser repetivel", CHAVE.hex() in texto)
    checar("com o hash do cifrado e do decifrado",
           hashlib.sha256(banco).hexdigest() in texto and "confere com o manifesto" in texto)
    checar("e com a alteracao que o procedimento causou no dispositivo",
           "ALTERAÇÃO NO DISPOSITIVO" in texto)

    sem_backup = criar_pasta_aquisicao(raiz, "CASO_400", "Android", datetime(2026, 10, 2, 9, 0, 0))
    (sem_backup / "whatsapp").mkdir()
    (sem_backup / "whatsapp" / "msgstore.db.crypt14").write_bytes(b"x" * 100)
    vazio = decifrar_whatsapp(sem_backup, CHAVE_TEXTO)
    checar("aquisicao so com crypt14: erro que explica o que falta fazer no aparelho",
           "ATIVADO" in vazio.erro and "crypt14" in vazio.erro)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
