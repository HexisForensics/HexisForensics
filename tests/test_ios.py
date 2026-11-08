"""
Testes do iPhone, sem aparelho: um backup local sintético, no formato do
iOS (arquivos com o SHA-1 de `dominio-caminho` como nome), e clientes
falsos no lugar do pymobiledevice3.

O que se cobra é a doutrina da suíte aplicada ao iPhone:

- o que está no backup é lido, com a procedência de cada registro;
- o que o backup NÃO contém é dito como tal, e não como "nenhum registro";
- backup cifrado sem a senha não afirma nada sobre o conteúdo;
- módulo sem dado nunca é sucesso;
- a senha temporária é sempre retirada, e a que fica é FALHA em voz alta.
"""

import plistlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import backup_ios  # noqa: E402
from core.backup_ios import ARQUIVOS_DE_INTERESSE, ArquivoIOS, caminho_no_backup  # noqa: E402
from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import conferir_manifesto, gerar_manifesto  # noqa: E402
from core.ios.client import ErroIOS  # noqa: E402
from core.ios.extractors.backup import BackupCompletoExtractorIOS  # noqa: E402
from core.ios.extractors.backup_cifrado import BackupCifradoExtractorIOS  # noqa: E402
from core.ios.extractors.identificacao import IdentificacaoExtractorIOS  # noqa: E402
from core.mensagens_ios import EPOCA_APPLE, momento_apple, texto_de_attributed_body  # noqa: E402
from services.conversas_service import listar_conversas  # noqa: E402
from services.relatorio_service import e_aquisicao_ios, levantar_artefatos  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


UDID = "00008030-001A2B3C4D5E6F70"
# 05/09/2026 10:00:00 UTC em segundos desde 2001.
APPLE_2026 = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc).timestamp() - EPOCA_APPLE


def attributed_body(texto: str) -> bytes:
    """Um typedstream mínimo, como o do iOS 16, com o texto depois do NSString."""
    corpo = texto.encode("utf-8")
    return (b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString"
            b"\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+"
            + bytes([len(corpo)]) + corpo + b"\x86\x84\x02iI\x01")


def banco(caminho: Path, comandos: str, linhas=()):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.executescript(comandos)
    for sql, valores in linhas:
        conexao.execute(sql, valores)
    conexao.commit()
    conexao.close()


def montar_backup(pasta_backup: Path, cifrado=False, com_chamadas=True, com_whatsapp=True):
    pasta_backup.mkdir(parents=True, exist_ok=True)
    (pasta_backup / "Manifest.plist").write_bytes(plistlib.dumps({
        "IsEncrypted": cifrado,
        "Lockdown": {"ProductVersion": "17.5", "ProductType": "iPhone12,3",
                     "SerialNumber": "F2LXXXXX", "UniqueDeviceID": UDID, "DeviceName": "iPhone"},
    }))
    (pasta_backup / "Info.plist").write_bytes(plistlib.dumps({"Target Identifier": UDID}))
    (pasta_backup / "Status.plist").write_bytes(plistlib.dumps({"Version": "3.3"}))

    def alvo(chave):
        return caminho_no_backup(pasta_backup, ARQUIVOS_DE_INTERESSE[chave][0])

    nanos = int(APPLE_2026 * 1e9)
    banco(alvo("sms"), """
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY, text TEXT, attributedBody BLOB,
            handle_id INTEGER, date INTEGER, is_from_me INTEGER, is_read INTEGER, service TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, display_name TEXT);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY, filename TEXT, mime_type TEXT,
            transfer_name TEXT);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
        INSERT INTO handle VALUES (1, '+5511911112222');
        INSERT INTO chat VALUES (1, '+5511911112222', '');
    """, [
        ("INSERT INTO message VALUES (1, 'Encontro na padaria', NULL, 1, ?, 0, 1, 'iMessage')",
         (nanos,)),
        ("INSERT INTO message VALUES (2, NULL, ?, 1, ?, 1, 0, 'SMS')",
         (attributed_body("Levo o documento"), nanos + 60_000_000_000)),
        ("INSERT INTO message VALUES (3, NULL, NULL, 1, ?, 0, 1, 'iMessage')",
         (nanos + 120_000_000_000,)),
        ("INSERT INTO chat_message_join VALUES (1, 1), (1, 2), (1, 3)", ()),
        ("INSERT INTO attachment VALUES (1, '~/Library/SMS/Attachments/a.jpg', 'image/jpeg', "
         "'foto.jpg')", ()),
        ("INSERT INTO message_attachment_join VALUES (3, 1)", ()),
    ])
    if com_chamadas:
        banco(alvo("chamadas"), """
            CREATE TABLE ZCALLRECORD (Z_PK INTEGER PRIMARY KEY, ZADDRESS TEXT, ZDATE REAL,
                ZDURATION REAL, ZORIGINATED INTEGER, ZANSWERED INTEGER, ZCALLTYPE INTEGER,
                ZSERVICE_PROVIDER TEXT, ZNAME TEXT);
        """, [
            ("INSERT INTO ZCALLRECORD VALUES (1, '+5511911112222', ?, 61.4, 1, 0, 1, "
             "'com.apple.Telephony', 'Fulano')", (APPLE_2026,)),
            ("INSERT INTO ZCALLRECORD VALUES (2, '+5511955556666', ?, 0, 0, 0, 1, "
             "'com.apple.Telephony', NULL)", (APPLE_2026 + 600,)),
        ])
    banco(alvo("contatos"), """
        CREATE TABLE ABPerson (ROWID INTEGER PRIMARY KEY, First TEXT, Last TEXT,
            Organization TEXT);
        CREATE TABLE ABMultiValue (UID INTEGER PRIMARY KEY, record_id INTEGER,
            property INTEGER, value TEXT);
        INSERT INTO ABPerson VALUES (1, 'Fulano', 'Padeiro', NULL), (2, NULL, NULL, 'Banco X');
        INSERT INTO ABMultiValue VALUES (1, 1, 3, '+5511911112222'), (2, 1, 3, '+5511977778888'),
            (3, 1, 4, 'fulano@exemplo.com'), (4, 2, 3, '4004-0000');
    """)
    if com_whatsapp:
        banco(alvo("whatsapp"), """
            CREATE TABLE ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY, ZCONTACTJID TEXT,
                ZPARTNERNAME TEXT);
            CREATE TABLE ZWAGROUPMEMBER (Z_PK INTEGER PRIMARY KEY, ZMEMBERJID TEXT,
                ZCONTACTNAME TEXT);
            CREATE TABLE ZWAMEDIAITEM (Z_PK INTEGER PRIMARY KEY, ZMEDIALOCALPATH TEXT,
                ZTITLE TEXT);
            CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY, ZMESSAGEDATE REAL,
                ZISFROMME INTEGER, ZTEXT TEXT, ZMESSAGETYPE INTEGER, ZCHATSESSION INTEGER,
                ZGROUPMEMBER INTEGER, ZMEDIAITEM INTEGER, ZPUSHNAME TEXT);
            INSERT INTO ZWACHATSESSION VALUES (1, '5511911112222@s.whatsapp.net', 'Fulano'),
                (2, '120363000000@g.us', 'Grupo da Obra');
            INSERT INTO ZWAGROUPMEMBER VALUES (1, '5511944443333@s.whatsapp.net', 'Beltrano');
            INSERT INTO ZWAMEDIAITEM VALUES (1, 'Media/foto.jpg', 'a obra');
        """, [
            ("INSERT INTO ZWAMESSAGE VALUES (1, ?, 0, 'Oi, tudo certo?', 0, 1, NULL, NULL, NULL)",
             (APPLE_2026,)),
            ("INSERT INTO ZWAMESSAGE VALUES (2, ?, 1, 'Tudo', 0, 1, NULL, NULL, NULL)",
             (APPLE_2026 + 30,)),
            ("INSERT INTO ZWAMESSAGE VALUES (3, ?, 0, NULL, 1, 2, 1, 1, NULL)",
             (APPLE_2026 + 90,)),
        ])


def nova_aquisicao(raiz: Path, caso: str, minuto: int) -> Path:
    return criar_pasta_aquisicao(raiz, caso, "iOS", datetime(2026, 10, 23, 10, minuto, 0))


def por_chave(artefatos):
    return {a.chave: a for a in artefatos}


with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)

    # -----------------------------------------------------------------------
    print("\n[1] Conversões do formato da Apple")
    # -----------------------------------------------------------------------
    checar("segundos desde 2001 viram a data certa",
           momento_apple(APPLE_2026) == datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc))
    checar("nanossegundos (sms.db do iOS 11 em diante) também",
           momento_apple(int(APPLE_2026 * 1e9)) == datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc))
    checar("zero não vira 01/01/2001", momento_apple(0) is None)
    checar("o texto do attributedBody é recuperado",
           texto_de_attributed_body(attributed_body("Levo o documento")) == "Levo o documento")
    longo = "x" * 300
    checar("inclusive texto longo (comprimento em dois bytes)",
           texto_de_attributed_body(attributed_body("")[:-6].rsplit(b"+", 1)[0] + b"+\x81"
                                    + (300).to_bytes(2, "little") + longo.encode()) == longo)
    checar("o nome no backup é o SHA-1 de dominio-caminho",
           ArquivoIOS("HomeDomain", "Library/SMS/sms.db").identificador
           == "3d0d7e5fb2ce288813306e4d4636395e047a3d28")

    # -----------------------------------------------------------------------
    print("\n[2] Backup sem criptografia: lido, com procedência")
    # -----------------------------------------------------------------------
    aquisicao = nova_aquisicao(raiz, "CASO_IOS", 0)
    montar_backup(aquisicao / backup_ios.PASTA / UDID)
    gerar_manifesto(aquisicao)
    checar("a aquisição é reconhecida como de iPhone", e_aquisicao_ios(aquisicao))

    artefatos = por_chave(levantar_artefatos(aquisicao))
    checar("os quatro artefatos do iPhone, os locais das fotos, e nenhum do Android",
           set(artefatos) == {"sms_ios", "chamada_ios", "contato_ios", "whatsapp_ios",
                              "locais_fotos"})
    sms = artefatos["sms_ios"]
    checar("as três mensagens do sms.db", sms.total == 3)
    textos = [r.campos["conteudo"] for r in sms.resultado.registros]
    checar("o texto que só existe no attributedBody aparece", "Levo o documento" in textos)
    checar("o anexo é identificado", any("foto.jpg" in r.campos["anexo"]
                                          for r in sms.resultado.registros))
    checar("o serviço (iMessage/SMS) é dito",
           {r.campos["servico"] for r in sms.resultado.registros} == {"iMessage", "SMS"})
    checar("a origem confere com o selo", sms.confere_com_o_selo is True)
    checar("a origem aponta o arquivo no aparelho", "HomeDomain/Library/SMS/sms.db"
           in sms.caminho_relativo)

    chamadas = artefatos["chamada_ios"]
    checar("as duas chamadas", chamadas.total == 2)
    checar("efetuada e não atendida distinguidas",
           [r.campos["direcao"] for r in chamadas.resultado.registros]
           == ["Efetuada", "Recebida, não atendida"])
    checar("duração em segundos inteiros",
           chamadas.resultado.registros[0].campos["duracao_segundos"] == "61")

    contatos = artefatos["contato_ios"]
    checar("um registro por telefone (3), com o e-mail junto",
           contatos.total == 3 and contatos.resultado.registros[0].campos["email"]
           == "fulano@exemplo.com")
    checar("contato só com empresa usa o nome da empresa",
           contatos.resultado.registros[-1].campos["contato"] == "Banco X")

    whatsapp = artefatos["whatsapp_ios"]
    checar("as três mensagens do WhatsApp", whatsapp.total == 3)
    grupo = whatsapp.resultado.registros[2]
    checar("no grupo, o interlocutor é quem enviou, não o grupo",
           grupo.campos["numero"] == "5511944443333" and grupo.campos["contato"] == "Beltrano"
           and grupo.campos["conversa"] == "Grupo da Obra")
    checar("mídia com legenda e caminho", grupo.campos["conteudo"] == "a obra"
           and grupo.campos["anexo"] == "Media/foto.jpg")

    conversas, _ = listar_conversas(aquisicao)
    checar("as conversas do iPhone entram no PDF de conversas selecionadas",
           {c.artefato for c in conversas} == {"sms_ios", "whatsapp_ios"})
    checar("ler não altera a aquisição selada", conferir_manifesto(aquisicao).integro)

    # -----------------------------------------------------------------------
    print("\n[3] O que o backup não contém é dito como tal")
    # -----------------------------------------------------------------------
    sem = nova_aquisicao(raiz, "CASO_IOS", 1)
    montar_backup(sem / backup_ios.PASTA / UDID, com_chamadas=False, com_whatsapp=False)
    artefatos = por_chave(levantar_artefatos(sem))
    explicacao = artefatos["chamada_ios"].explicacao
    checar("chamadas ausentes: 'NÃO contém', com o motivo, e não 'nenhum registro'",
           "NÃO contém" in explicacao and "backup cifrado" in explicacao)
    checar("e não se diz que o sistema recusou",
           "RECUSOU" not in explicacao and not artefatos["chamada_ios"].resultado.acesso_negado)
    checar("o WhatsApp Business não aparece quando não está no backup",
           not any(c.startswith("whatsapp_ios_") for c in artefatos))

    # -----------------------------------------------------------------------
    print("\n[4] Backup cifrado sem a senha: nada se afirma")
    # -----------------------------------------------------------------------
    cifrada = nova_aquisicao(raiz, "CASO_IOS", 2)
    montar_backup(cifrada / backup_ios.PASTA / UDID, cifrado=True)
    artefatos = por_chave(levantar_artefatos(cifrada))
    checar("nenhum registro é lido do backup cifrado",
           all(a.total == 0 for a in artefatos.values()))
    locais = artefatos.pop("locais_fotos")
    checar("e cada artefato diz que está CIFRADO e o que fazer",
           all("CIFRADO" in a.explicacao and "Decifrar backup" in a.explicacao
               for a in artefatos.values()))
    checar("os locais das fotos dizem que nada foi lido, e não 'sem GPS'",
           "cifrado" in locais.explicacao and "GPS" not in locais.explicacao)

    sem_backup = nova_aquisicao(raiz, "CASO_IOS", 3)
    artefatos = levantar_artefatos(sem_backup)
    checar("aquisição de iPhone sem backup: tudo NÃO COLETADO, nada omitido",
           len(artefatos) == 5 and not any(a.presente for a in artefatos))

    # -----------------------------------------------------------------------
    print("\n[5] Módulos: sucesso só com dado obtido")
    # -----------------------------------------------------------------------
    class ClienteFalso:
        udid = UDID

        def __init__(self, falhar_backup=False, cifrando=False, recusa_retirada=False):
            self.falhar_backup = falhar_backup
            self.cifrando = cifrando
            self.recusa_retirada = recusa_retirada
            self.chamadas = []

        def definir_udid(self, udid):
            self.udid = udid

        def verificar_disponibilidade(self):
            return True, ""

        def informacoes(self):
            return {"ProductType": "iPhone12,3", "ProductVersion": "17.5",
                    "SerialNumber": "F2LXXXXX", "UniqueDeviceID": UDID,
                    "InternationalMobileEquipmentIdentity": "356789012345678",
                    "WillEncrypt": "False"}

        def fazer_backup(self, destino, progresso=None):
            if self.falhar_backup:
                raise ErroIOS("o iPhone encerrou a conexão")
            montar_backup(Path(destino) / UDID, cifrado=self.cifrando)
            if progresso:
                progresso(100)
            return Path(destino) / UDID

        def cifragem_ativa(self):
            return self.cifrando

        def alterar_senha_de_backup(self, antiga="", nova=""):
            self.chamadas.append(("antiga" if antiga else "nova", antiga or nova))
            if nova:
                self.cifrando = True
            elif not self.recusa_retirada:
                self.cifrando = False

    pasta = nova_aquisicao(raiz, "CASO_MOD", 0)
    resultado = IdentificacaoExtractorIOS(client=ClienteFalso()).executar(pasta)
    checar("identificação: sucesso com modelo, versão e IMEI",
           resultado.sucesso and "iPhone12,3" in resultado.mensagem)
    from core.aparelho import ler_caracteristicas  # noqa: E402
    pares = dict(ler_caracteristicas(pasta).em_pares())
    checar("e o laudo recebe IMEI e versão do iOS",
           pares.get("IMEI") == "356789012345678" and pares.get("Versão do iOS") == "17.5")

    resultado = BackupCompletoExtractorIOS(client=ClienteFalso(falhar_backup=True)).executar(
        nova_aquisicao(raiz, "CASO_MOD", 1))
    checar("backup que falhou NUNCA é sucesso, e diz que não é ausência de dado",
           not resultado.sucesso and "NÃO significa ausência" in resultado.mensagem)

    pasta = nova_aquisicao(raiz, "CASO_MOD", 2)
    resultado = BackupCompletoExtractorIOS(client=ClienteFalso()).executar(pasta)
    checar("backup comum: sucesso, com a ressalva do que o backup sem cifra não traz",
           resultado.sucesso and "registro de chamadas" in resultado.mensagem
           and resultado.detalhes.get("itens_fora_do_alcance"))
    hashes = (pasta / backup_ios.PASTA / "hashes_na_aquisicao.txt").read_text(encoding="utf-8")
    checar("o SHA-256 de cada arquivo é gravado na aquisição", "Manifest.plist" in hashes)

    cliente = ClienteFalso(cifrando=True)
    resultado = BackupCifradoExtractorIOS(client=cliente).executar(
        nova_aquisicao(raiz, "CASO_MOD", 3))
    checar("senha temporária: com senha do dono, não executa e não altera nada",
           not resultado.sucesso and not cliente.chamadas and "NÃO foi" in resultado.mensagem)

    cliente = ClienteFalso()
    pasta = nova_aquisicao(raiz, "CASO_MOD", 4)
    resultado = BackupCifradoExtractorIOS(client=cliente).executar(pasta)
    senha = cliente.chamadas[0][1] if cliente.chamadas else ""
    checar("senha temporária: define, faz o backup e RETIRA a mesma senha",
           resultado.sucesso and cliente.chamadas == [("nova", senha), ("antiga", senha)]
           and not cliente.cifrando)
    checar("a senha fica registrada para a decifragem ser repetível",
           senha in (pasta / backup_ios.PASTA_CIFRADO / "senha_do_backup.txt").read_text(encoding="utf-8")
           and senha in resultado.mensagem)

    # iPhone 11 real, 31/10/2026: com os dois módulos marcados, o cifrado era
    # gravado POR CIMA do comum, e o desfecho dizia que os dois existiam.
    pasta = nova_aquisicao(raiz, "CASO_MOD", 7)
    comum = BackupCompletoExtractorIOS(client=ClienteFalso()).executar(pasta)
    cifrado = BackupCifradoExtractorIOS(client=ClienteFalso()).executar(pasta)
    backups = backup_ios.backups_da_aquisicao(pasta)
    checar("os dois backups na mesma aquisição: cada um na sua pasta, nenhum por cima do outro",
           comum.sucesso and cifrado.sucesso and len(backups) == 2
           and [backup_ios.esta_cifrado(b) for b in backups] == [False, True]
           and (pasta / backup_ios.PASTA / "hashes_na_aquisicao.txt").is_file()
           and (pasta / backup_ios.PASTA_CIFRADO / "hashes_na_aquisicao.txt").is_file())
    titulos = [a.titulo for a in levantar_artefatos(pasta)]
    checar("com os dois backups, nenhum título repetido: 'comum' e 'cifrado' no nome",
           len(titulos) == len(set(titulos))
           and any("backup comum do iPhone" in t for t in titulos)
           and any("backup cifrado do iPhone" in t for t in titulos))
    from services.relatorio_service import RelatorioService  # noqa: E402
    from core.normalizacao import Registro  # noqa: E402
    foto = Registro(tipo="whatsapp", campos={"anexo": "Media/1118@lid/2/b/2b2b977a.jpg"},
                    momento=None, arquivo_de_origem="x", linha_de_origem=1)
    checar("no PDF, o anexo mostra só o nome do arquivo",
           RelatorioService._celula_do_pdf(foto, "anexo") == "2b2b977a.jpg")

    cliente = ClienteFalso(falhar_backup=True)
    resultado = BackupCifradoExtractorIOS(client=cliente).executar(
        nova_aquisicao(raiz, "CASO_MOD", 5))
    checar("backup falhou: a senha é retirada mesmo assim",
           not resultado.sucesso and cliente.chamadas[-1][0] == "antiga" and not cliente.cifrando)

    cliente = ClienteFalso(recusa_retirada=True)
    resultado = BackupCifradoExtractorIOS(client=cliente).executar(
        nova_aquisicao(raiz, "CASO_MOD", 6))
    checar("senha que ficou no aparelho é FALHA em voz alta, com pendência",
           not resultado.sucesso and "CONTINUA DEFINIDA" in resultado.mensagem
           and resultado.detalhes.get("restauracao_pendente"))

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
