"""
Testes da via de backup dos pacotes DO SISTEMA para SMS e chamadas.

Medido num moto x4 de fabrica (Android 9, sem root) em 09/10/2026:

- os providers de SMS e de chamadas recusam o shell do ADB;
- `pm grant com.android.shell android.permission.READ_SMS` tambem falha:
  "Package com.android.shell has not requested permission";
- `adb backup com.android.providers.telephony` entregou 33 SMS;
- `adb backup -keyvalue com.android.calllogbackup` entregou 17 chamadas.

A suite tentava o backup do APLICATIVO de mensagens e do discador -- que
nao entregam nada -- e nunca o dos dois pacotes que guardam o dado. E
guardava o `.ab` "para decodificacao posterior", sem abri-lo: um arquivo so
com o manifesto do pacote, maior que zero byte e vazio de dados, contava
como "backup obtido" e fazia o modulo declarar sucesso.

Os `.ab` daqui sao montados a mao, no formato que o aparelho devolveu.
"""

import io
import json
import struct
import sys
import tarfile
import tempfile
import zlib
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import backup_android  # noqa: E402
from core.android.adb_client import ResultadoComando  # noqa: E402
from core.android.extractors.contacts_calls import ContatosChamadasExtractor  # noqa: E402
from core.android.extractors.sms import SMSExtractor  # noqa: E402
from core.backup_android import PACOTE_CHAMADAS, PACOTE_TELEFONIA  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
# Montagem de um .ab como o Android o grava
# ---------------------------------------------------------------------------
def montar_ab(membros: dict, cifra: str = "none") -> bytes:
    fluxo = io.BytesIO()
    with tarfile.open(fileobj=fluxo, mode="w") as tar:
        for nome, dado in membros.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dado)
            tar.addfile(info, io.BytesIO(dado))
    return b"ANDROID BACKUP\n5\n1\n" + cifra.encode() + b"\n" + zlib.compress(fluxo.getvalue())


def texto_java(valor):
    if valor is None:
        return b"\x00"
    bruto = valor.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(bruto)) + bruto


def chamada(data_ms, duracao, numero, tipo, iccid, cauda=b"\x00" * 51):
    return (
        struct.pack(">iqq", 1005, data_ms, duracao)
        + texto_java(numero)
        + struct.pack(">ii", tipo, 1)
        + texto_java("com.android.phone/Servico")
        + texto_java(iccid)
        + cauda
    )


def entidade(chave: str, valor):
    bruto_chave = chave.encode() + b"\x00"
    cabecalho = b"Data" + struct.pack("<ii", len(chave), -1 if valor is None else len(valor))
    bloco = cabecalho + bruto_chave
    bloco += b"\xbc" * (-len(bloco) % 4)
    if valor is not None:
        bloco += valor + b"\xbc" * (-len(valor) % 4)
    return bloco


MANIFESTO = b"1\npacote\n28\n28\n\n0\n1\nassinatura\n"
SMS = [
    {"address": "11911112222", "body": "Oi, tudo bem?", "date": "1791031697475",
     "type": "1", "read": "1"},
    {"address": "11933334444", "body": "Chego\nem 5 min", "date": "1791031700000",
     "type": "2", "read": "0"},
]
AB_SMS = montar_ab({
    f"apps/{PACOTE_TELEFONIA}/_manifest": MANIFESTO,
    f"apps/{PACOTE_TELEFONIA}/d_f/000000_sms_backup":
        zlib.compress(json.dumps(SMS).encode("utf-8")),
    f"apps/{PACOTE_TELEFONIA}/d_f/000000_mms_backup":
        zlib.compress(json.dumps([{
            "date": "1791031800", "msg_box": "1", "read": "1", "sub": "Foto",
            "mms_body": "olha isso",
            "mms_addresses": [{"type": 137, "address": "+5511955556666"},
                              {"type": 151, "address": "insert-address-token"}],
        }]).encode("utf-8")),
})
DADOS_CHAMADAS = (
    entidade("1", chamada(1791031697475, 112, "01511982649514", 2, "8955000000000000001"))
    + entidade("2", chamada(1791031800000, 0, None, 3, "8955000000000000001"))
    + entidade("3", None)
)
AB_CHAMADAS = montar_ab({
    f"apps/{PACOTE_CHAMADAS}/k/_manifest": MANIFESTO,
    f"apps/{PACOTE_CHAMADAS}/k/{PACOTE_CHAMADAS}.data": DADOS_CHAMADAS,
})
AB_SO_MANIFESTO = montar_ab({"apps/com.google.android.dialer/_manifest": MANIFESTO})

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # -----------------------------------------------------------------------
    print("\n[1] O .ab e ABERTO, e o que ha dentro e lido")
    # -----------------------------------------------------------------------
    (tmp / "sms.ab").write_bytes(AB_SMS)
    antes = (tmp / "sms.ab").read_bytes()
    sms = backup_android.ler_sms(tmp / "sms.ab", "sms/backup.ab")
    checar("as duas mensagens sao lidas", sms.total == 2)
    checar("numero, sentido e conteudo",
           (sms.registros[0].campos["numero"], sms.registros[0].campos["direcao"],
            sms.registros[0].campos["conteudo"]) == ("11911112222", "Recebida", "Oi, tudo bem?"))
    checar("quebra de linha no corpo nao parte a mensagem",
           sms.registros[1].campos["conteudo"] == "Chego\nem 5 min")
    checar("a data em milissegundos nao vai para 1970", sms.registros[0].momento.year == 2026)
    checar("a procedencia aponta o lote dentro do backup",
           "000000_sms_backup" in sms.registros[0].arquivo_de_origem)
    checar("o arquivo selado nao e alterado pela leitura",
           (tmp / "sms.ab").read_bytes() == antes)
    checar("e nada e gravado ao lado dele", [p.name for p in tmp.iterdir()] == ["sms.ab"])

    mms = backup_android.ler_mms(tmp / "sms.ab", "sms/backup.ab")
    checar("o MMS do mesmo backup e lido a parte", mms.total == 1)
    checar("recebida: o numero e o do remetente, nunca o marcador do proprio aparelho",
           mms.registros[0].campos["numero"] == "+5511955556666")
    checar("a data do MMS, em segundos, tambem cai em 2026", mms.registros[0].momento.year == 2026)
    checar("a coluna de anexo DIZ que o backup nao os traz",
           "não inclui anexos" in mms.registros[0].campos["anexo"])

    # -----------------------------------------------------------------------
    print("\n[2] Chamadas: o formato chave/valor binario")
    # -----------------------------------------------------------------------
    (tmp / "ch.ab").write_bytes(AB_CHAMADAS)
    chamadas = backup_android.ler_chamadas(tmp / "ch.ab", "contacts_calls/backup.ab")
    checar("as duas chamadas sao lidas", chamadas.total == 2)
    primeira, segunda = chamadas.registros
    checar("numero, sentido e duracao",
           (primeira.campos["numero"], primeira.campos["direcao"],
            primeira.campos["duracao_segundos"]) == ("01511982649514", "Efetuada", "112"))
    checar("a linha utilizada (ICCID) acompanha a chamada",
           primeira.campos["linha_utilizada"] == "8955000000000000001")
    checar("numero ausente vira '(sem numero)', nao quebra a leitura",
           segunda.campos["numero"] == "(sem número)" and segunda.campos["direcao"] == "Perdida")
    checar("o nome do contato NAO e inventado",
           "não traz o nome" in primeira.campos["contato"])
    checar("o marcador de exclusao e contado como descarte, nao some",
           len(chamadas.descartes) == 1 and "exclusão" in chamadas.descartes[0].motivo)
    checar("a cauda do registro, nao interpretada, e contada",
           backup_android.interpretar_chamada(bytes.fromhex(primeira.bruto))["bytes_nao_lidos"] == 51)

    # Estrutura que se perde no meio: o que veio antes vale, e o resto e DITO.
    (tmp / "quebrado.ab").write_bytes(montar_ab({
        f"apps/{PACOTE_CHAMADAS}/k/x.data":
            entidade("1", chamada(1791031697475, 5, "119", 1, "8955")) + b"LIXO" * 8,
    }))
    quebrado = backup_android.ler_chamadas(tmp / "quebrado.ab")
    checar("arquivo corrompido no meio: a chamada integra e aproveitada", quebrado.total == 1)
    checar("e a interrupcao avisa que pode haver mais",
           any("pode haver chamadas além" in d.motivo for d in quebrado.descartes))

    truncada = backup_android.ler_chamadas  # registro cortado antes do numero
    (tmp / "curto.ab").write_bytes(montar_ab({
        f"apps/{PACOTE_CHAMADAS}/k/x.data": entidade("9", struct.pack(">iq", 1005, 1)),
    }))
    curto = truncada(tmp / "curto.ab")
    checar("registro truncado e descarte, nunca chamada com campos vazios",
           curto.total == 0 and len(curto.descartes) == 1)

    # -----------------------------------------------------------------------
    print("\n[3] O que nao pode ser lido e RECUSADO com o motivo")
    # -----------------------------------------------------------------------
    (tmp / "cifrado.ab").write_bytes(montar_ab({"a": b"x"}, cifra="AES-256"))
    cifrado = backup_android.ler_sms(tmp / "cifrado.ab")
    checar("backup cifrado nao vira 'nenhuma mensagem'", cifrado.acesso_negado)
    checar("e o motivo diz que esta cifrado", "cifrado" in cifrado.trecho_da_recusa)
    (tmp / "lixo.ab").write_bytes(b"isto nao e um backup")
    checar("arquivo sem a assinatura e recusado",
           backup_android.ler_chamadas(tmp / "lixo.ab").acesso_negado)
    (tmp / "cortado.ab").write_bytes(AB_SMS[: len(AB_SMS) // 2])
    checar("backup truncado e recusado, nao lido pela metade",
           backup_android.ler_sms(tmp / "cortado.ab").acesso_negado)

    # Achado na primeira execucao real: o moto x4 nao tinha MMS, e o caderno
    # explicaria o vazio como "o provider respondeu a consulta e nao retornou
    # nenhum registro" -- sobre um backup, que nao e consulta nem prova ausencia.
    (tmp / "ch_sem_mms.ab").write_bytes(AB_CHAMADAS)
    sem_mms = backup_android.ler_mms(tmp / "ch_sem_mms.ab")
    checar("backup sem MMS: zero registro, sem recusa",
           sem_mms.total == 0 and not sem_mms.acesso_negado)
    checar("o vazio NAO e explicado como resposta de provider",
           "provider respondeu" not in sem_mms.explicacao_do_vazio)
    checar("e proibe a conclusao de ausencia",
           "NÃO se pode concluir" in sem_mms.explicacao_do_vazio)

    (tmp / "vazio.ab").write_bytes(AB_SO_MANIFESTO)
    checar("backup so com o manifesto NAO tem arquivo de dados",
           backup_android.abrir(tmp / "vazio.ab").arquivos_de_dados == [])


# ---------------------------------------------------------------------------
print("\n[4] Os modulos tentam os pacotes do SISTEMA, e abrem o que veio")
# ---------------------------------------------------------------------------
RECUSA = "java.lang.SecurityException: Permission Denial: requires android.permission.READ_SMS"


class ADBDeFabricaComBackup:
    """Providers recusam; o backup dos pacotes do sistema responde."""

    serial = "0030000000"

    def __init__(self, respostas):
        self.respostas = respostas
        self.backups_pedidos = []

    def definir_serial(self, serial):
        self.serial = serial

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        comando = " ".join(argumentos)
        if "content query" in comando:
            return ResultadoComando(0, "", RECUSA)
        if "ro.build.version.sdk" in comando:
            return ResultadoComando(0, "28", "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos, timeout, vincular_serial).stdout

    def obter_propriedade(self, propriedade):
        return self.executar(["shell", "getprop", propriedade])

    def pacote_instalado(self, pacote):
        return pacote in self.respostas

    def backup_pacote(self, pacote, caminho_saida, timeout=90, chave_valor=False):
        self.backups_pedidos.append((pacote, chave_valor))
        conteudo = self.respostas[pacote]
        if conteudo is None:
            return False
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        caminho_saida.write_bytes(conteudo)
        return True


def rodar(classe, respostas):
    extrator = classe()
    adb = ADBDeFabricaComBackup(respostas)
    extrator.adb = adb
    extrator.device.adb = adb
    pasta = Path(tempfile.mkdtemp()) / "aquisicao"
    pasta.mkdir()
    return extrator.executar(pasta), pasta, adb


resultado, pasta, adb = rodar(SMSExtractor, {
    PACOTE_TELEFONIA: AB_SMS,
    "com.google.android.apps.messaging": AB_SO_MANIFESTO,
})
checar("o pacote do sistema e o PRIMEIRO a ser tentado",
       adb.backups_pedidos[0] == (PACOTE_TELEFONIA, False))
checar("provider recusado + backup com dados: sucesso", resultado.sucesso)
checar("com a recusa do provider ainda declarada como ressalva",
       resultado.detalhes.get("acesso_negado") is True)
checar("o backup com dados fica na aquisicao",
       (pasta / "sms" / f"backup_{PACOTE_TELEFONIA}.ab").is_file())
checar("o backup SO COM MANIFESTO e descartado, nao conta como obtido",
       not (pasta / "sms" / "backup_com.google.android.apps.messaging.ab").exists())
checar("e apenas um backup e contado", len(resultado.detalhes["arquivos_backup"]) == 1)

# O defeito que isto fecha: so backups vazios, e o modulo dizia "dados obtidos".
resultado, pasta, _ = rodar(SMSExtractor, {"com.google.android.apps.messaging": AB_SO_MANIFESTO})
checar("so backup vazio: FALHA, nunca 'dados obtidos'", not resultado.sucesso)
checar("e a mensagem proibe a conclusao negativa", "NÃO se pode concluir" in resultado.mensagem)

resultado, pasta, adb = rodar(ContatosChamadasExtractor, {PACOTE_CHAMADAS: AB_CHAMADAS})
checar("o pacote de chamadas e pedido em modo chave/valor",
       (PACOTE_CHAMADAS, True) in adb.backups_pedidos)
checar("e as chamadas sao lidas do que ficou na aquisicao",
       backup_android.ler_chamadas(
           pasta / "contacts_calls" / f"backup_{PACOTE_CHAMADAS}.ab").total == 2)

resultado, pasta, _ = rodar(SMSExtractor, {PACOTE_TELEFONIA: None})
checar("confirmacao nao feita na tela: FALHA, e nenhum .ab fica",
       not resultado.sucesso and not list((pasta / "sms").glob("*.ab")))


# ---------------------------------------------------------------------------
print("\n[5] O caderno apresenta o que veio pelo backup, ao lado da recusa")
# ---------------------------------------------------------------------------
from services.relatorio_service import RelatorioService  # noqa: E402

resultado, pasta, _ = rodar(SMSExtractor, {PACOTE_TELEFONIA: AB_SMS})
rodar_chamadas = ContatosChamadasExtractor()
adb = ADBDeFabricaComBackup({PACOTE_CHAMADAS: AB_CHAMADAS})
rodar_chamadas.adb = adb
rodar_chamadas.device.adb = adb
rodar_chamadas.executar(pasta)

artefatos = {a.chave: a for a in RelatorioService._levantar(pasta, None)}
checar("SMS pelo provider: presente e RECUSADO", artefatos["sms"].resultado.acesso_negado)
checar("SMS pelo backup: 2 registros", artefatos["sms_backup"].resultado.total == 2)
checar("MMS pelo backup: 1 registro", artefatos["mms_backup"].resultado.total == 1)
checar("chamadas pelo backup: 2 registros", artefatos["chamada_backup"].resultado.total == 2)
checar("o titulo diz por qual via o dado veio",
       "via backup do sistema" in artefatos["chamada_backup"].titulo)

sem_backup = Path(tempfile.mkdtemp())
checar("sem .ab na aquisicao, o caderno nao cria artefato de backup",
       not any(a.chave.endswith("_backup") for a in RelatorioService._levantar(sem_backup, None)))


print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
