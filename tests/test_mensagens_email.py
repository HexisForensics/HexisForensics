"""
Testes da leitura do acervo local de correio do Android.

O bloco [2] guarda a razao de a deteccao ser por COLUNA e nao por nome de
tabela. Ha uma colisao concreta: a tabela de mensagens do Gmail costuma
chamar-se `messages`, exatamente como no msgstore.db do WhatsApp. Escolher
pelo nome faria o leitor de e-mail abrir um banco de WhatsApp e devolver
lixo. A assinatura exigida e endereco de remetente MAIS assunto ou corpo
-- o que distingue correio de mensageiro, que tem identificador de
conversa e nao endereco.

O bloco [3] cobre a variacao de esquema, que no Gmail e muito maior que no
WhatsApp: os mesmos campos ja tiveram nomes diferentes entre versoes, e o
leitor tem de achar o que existe em vez de exigir um nome so.

O bloco [5] guarda duas recusas de afirmar. O corpo comprimido EXISTE e
nao foi interpretado -- devolver vazio faria a mensagem parecer sem
conteudo, que e fato diferente. E o anexo entra como presenca, nao como
nome: o nome mora numa estrutura serializada propria, e aproxima-lo
produziria nomes plausiveis e possivelmente errados, o que e pior que nao
ter nome nenhum.
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.mensagens_email import (
    AVISO_CORPO_COMPRIMIDO,
    COLUNAS,
    ler,
    localizar_tabela_de_mensagens,
)
from core.sqlite_forense import abrir

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


EPOCH = 1787513890741


def banco_gmail(caminho: Path, mensagens, nomes=None):
    """
    Acervo no formato do Gmail. `nomes` permite trocar os nomes das colunas
    para simular outra versao do aplicativo.
    """
    n = {
        "remetente": "fromAddress",
        "destinatario": "toAddresses",
        "assunto": "subject",
        "corpo": "snippet",
        "momento": "dateReceivedMs",
        "anexo": "joinedAttachmentInfos",
    }
    n.update(nomes or {})

    c = sqlite3.connect(caminho)
    c.execute(
        f'CREATE TABLE messages(_id INTEGER PRIMARY KEY, "{n["remetente"]}" TEXT, '
        f'"{n["destinatario"]}" TEXT, "{n["assunto"]}" TEXT, "{n["corpo"]}" TEXT, '
        f'"{n["momento"]}" INTEGER, "{n["anexo"]}" TEXT)'
    )
    for indice, m in enumerate(mensagens, 1):
        c.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                indice,
                m.get("de"),
                m.get("para"),
                m.get("assunto"),
                m.get("corpo"),
                m.get("momento", EPOCH + indice),
                m.get("anexo"),
            ),
        )
    c.commit()
    c.close()


def banco_whatsapp(caminho: Path):
    """Um msgstore.db legado: tabela `messages`, mas sem nada de correio."""
    c = sqlite3.connect(caminho)
    c.execute(
        "CREATE TABLE messages(_id INTEGER PRIMARY KEY, key_remote_jid TEXT, "
        "key_from_me INTEGER, data TEXT, timestamp INTEGER)"
    )
    c.execute(
        "INSERT INTO messages VALUES (1, '5511988887777@s.whatsapp.net', 0, 'oi', ?)",
        (EPOCH,),
    )
    c.commit()
    c.close()


# ---------------------------------------------------------------------------
print("\n[1] O acervo de correio e lido")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "mailstore.fulano@gmail.com.db"
    banco_gmail(banco, [
        {
            "de": "remetente@exemplo.com",
            "para": "fulano@gmail.com",
            "assunto": "Proposta comercial",
            "corpo": "Segue em anexo o combinado.",
            "anexo": "PARTE|contrato.pdf|application/pdf",
        },
        {
            "de": "outro@exemplo.com",
            "para": "fulano@gmail.com",
            "assunto": "Sem anexo",
            "corpo": "Mensagem simples.",
        },
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("as duas mensagens sao lidas", resultado.total == 2)
    checar("sem descarte", not resultado.descartes)
    checar("e sem recusa", not resultado.acesso_negado)

    primeira = resultado.registros[0]
    checar("o remetente e apresentado", primeira.campos["de"] == "remetente@exemplo.com")
    checar("o destinatario tambem", primeira.campos["para"] == "fulano@gmail.com")
    checar("o assunto vem inteiro", primeira.campos["assunto"] == "Proposta comercial")
    checar("e a data e convertida", primeira.momento is not None)

# ---------------------------------------------------------------------------
print("\n[2] Um banco de WhatsApp NAO passa por acervo de correio")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "msgstore.db"
    banco_whatsapp(banco)

    # A tabela se chama `messages` nos dois. So a assinatura de colunas
    # distingue: correio tem endereco, mensageiro tem jid de conversa.
    with abrir(banco, Path(tmp) / "sonda") as aberto:
        checar("a tabela homonima existe", aberto.tem_tabelas("messages"))
        tabela, _mapa = localizar_tabela_de_mensagens(aberto)
    checar("mas nao e reconhecida como correio", tabela is None)

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("nao ha registro", resultado.total == 0)
    checar("e o zero NAO passa por 'nao havia correio'", resultado.acesso_negado)
    checar("a recusa nomeia as tabelas encontradas",
           "messages" in resultado.trecho_da_recusa)
    checar("dizendo que nada se pode afirmar",
           "Nada se pode afirmar" in resultado.trecho_da_recusa)

# ---------------------------------------------------------------------------
print("\n[3] Nomes de coluna de outra versao continuam sendo achados")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "mailstore.db"
    banco_gmail(
        banco,
        [{"de": "a@b.com", "para": "c@d.com", "assunto": "Assunto", "corpo": "Corpo"}],
        nomes={
            "remetente": "from_address",
            "destinatario": "to_addresses",
            "corpo": "body",
            "momento": "date",
        },
    )

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("a mensagem e lida com os nomes alternativos", resultado.total == 1)
    checar("com o remetente certo", resultado.registros[0].campos["de"] == "a@b.com")
    checar("e o corpo certo", resultado.registros[0].campos["conteudo"] == "Corpo")

with tempfile.TemporaryDirectory() as tmp:
    # Versao sem coluna de destinatario: o campo sai vazio, e o resto
    # continua sendo lido. Faltar coluna nao pode derrubar o exame.
    banco = Path(tmp) / "mailstore.db"
    c = sqlite3.connect(banco)
    c.execute("CREATE TABLE messages(_id INTEGER, fromAddress TEXT, subject TEXT)")
    c.execute("INSERT INTO messages VALUES (1, 'x@y.com', 'So assunto')")
    c.commit()
    c.close()

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("tabela sem destinatario ainda e lida", resultado.total == 1)
    checar("o campo ausente sai vazio, nao inventado",
           resultado.registros[0].campos["para"] == "")

# ---------------------------------------------------------------------------
print("\n[4] Registro sem data, sem assunto e sem corpo e descartado")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "mailstore.db"
    banco_gmail(banco, [
        {"de": "a@b.com", "assunto": "vale", "momento": EPOCH},
        {"de": "c@d.com", "assunto": None, "corpo": None, "momento": 0},
    ])

    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("a mensagem boa entra", resultado.total == 1)
    checar("a vazia vira descarte CONTADO", len(resultado.descartes) == 1)
    checar("com o motivo escrito",
           "sem data, sem assunto e sem corpo" in resultado.descartes[0].motivo)

# ---------------------------------------------------------------------------
print("\n[5] Duas recusas de afirmar: corpo comprimido e nome de anexo")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "mailstore.db"
    c = sqlite3.connect(banco)
    c.execute(
        "CREATE TABLE messages(_id INTEGER, fromAddress TEXT, subject TEXT, "
        "bodyCompressed BLOB, dateReceivedMs INTEGER, joinedAttachmentInfos TEXT)"
    )
    c.execute(
        "INSERT INTO messages VALUES (1, 'a@b.com', 'Com corpo comprimido', ?, ?, ?)",
        (b"\\x1f\\x8b dados comprimidos", EPOCH, "PARTE|contrato.pdf|application/pdf"),
    )
    c.commit()
    c.close()

    resultado = ler(banco, Path(tmp) / "trabalho")
    registro = resultado.registros[0]

    checar("o corpo comprimido NAO vira mensagem vazia",
           registro.campos["conteudo"] == AVISO_CORPO_COMPRIMIDO)
    checar("declarando que existe e nao foi interpretado",
           "não interpretado" in registro.campos["conteudo"])

    checar("a presenca do anexo e afirmada", registro.campos["anexo"] == "Sim")
    checar("mas o NOME do arquivo nao e extraido por aproximacao",
           "contrato.pdf" not in registro.campos["anexo"])

with tempfile.TemporaryDirectory() as tmp:
    banco = Path(tmp) / "mailstore.db"
    banco_gmail(banco, [{"de": "a@b.com", "assunto": "Sem anexo", "corpo": "texto"}])
    resultado = ler(banco, Path(tmp) / "trabalho")
    checar("mensagem sem anexo e marcada como sem anexo",
           resultado.registros[0].campos["anexo"] == "Não")

checar("as colunas do artefato estao definidas", len(COLUNAS) == 6)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
