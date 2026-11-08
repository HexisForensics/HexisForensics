"""
Testes de dois modulos que afirmavam o que nao tinham verificado.

1. CARACTERISTICAS TECNICAS devolvia `sucesso=True` incondicionalmente. Com
   o aparelho desconectado no meio do exame, o `getprop` volta vazio e o
   modulo gravava um relatorio de campos em branco sob a mensagem
   "Relatorio tecnico gerado." -- caracterizacao de um aparelho do qual nada
   foi lido.

2. O modulo de SMS se chamava "Mensagens SMS/MMS" e nao consultava
   `content://mms` em lugar nenhum. O caderno de conteudo repetia o titulo.
   Quem lesse "SMS/MMS: 12 registros" concluiria que o aparelho nao tinha
   MMS, quando MMS nunca foi procurado.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoStream  # noqa: E402
from core.android.extractors.device_info import (  # noqa: E402
    DeviceInfoExtractor,
    interpretar_getprop,
)
from core.android.extractors.sms import SMSExtractor  # noqa: E402
from core.aparelho import ler_caracteristicas  # noqa: E402
from core.normalizacao import normalizar_mms, normalizar_sms  # noqa: E402
from services.extraction_service import indica_ressalva  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def linha(argumentos):
    return " ".join(argumentos)


GETPROP_COMPLETO = "\n".join([
    "[ro.product.manufacturer]: [motorola]",
    "[ro.product.model]: [moto x4]",
    "[ro.product.brand]: [motorola]",
    "[ro.serialno]: [0030000000]",
    "[ro.product.cpu.abi]: [arm64-v8a]",
    "[ro.build.version.release]: [9]",
    "[ro.build.version.sdk]: [28]",
    "[ro.build.version.security_patch]: [2020-08-01]",
    "[ro.build.fingerprint]: [motorola/payton/payton:9/PPWS29.69-39-6-13/abc:user/release-keys]",
    "[ro.build.type]: [user]",
    "[ro.crypto.state]: [encrypted]",
    "[ro.crypto.type]: [file]",
    "[ro.boot.verifiedbootstate]: [green]",
    "[ro.boot.flash.locked]: [1]",
    "[gsm.version.baseband]: [M660_7042.27.01.89R]",
    "[persist.sys.timezone]: [America/Sao_Paulo]",
])


class ADBDublado:
    serial = "0030000000"

    def __init__(self, getprop="", stderr_getprop="", codigo_getprop=0):
        self.getprop = getprop
        self.stderr_getprop = stderr_getprop
        self.codigo_getprop = codigo_getprop
        self.comandos = []

    def definir_serial(self, serial):
        self.serial = serial

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        comando = linha(argumentos)
        self.comandos.append(comando)
        if comando == "shell getprop":
            return ResultadoComando(self.codigo_getprop, self.getprop, self.stderr_getprop)
        if "uname" in comando:
            return ResultadoComando(0, "Linux localhost 4.4.153", "")
        if comando == "shell df":
            return ResultadoComando(0, "/data 52G 9G 43G", "")
        if "battery" in comando:
            return ResultadoComando(0, "level: 80", "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos, timeout, vincular_serial).stdout

    def obter_propriedade(self, propriedade):
        return self.executar(["shell", "getprop", propriedade])

    def listar_dispositivos(self):
        return [(self.serial, "device")]


def rodar_caracteristicas(adb):
    extrator = DeviceInfoExtractor()
    extrator.adb = adb
    extrator.device.adb = adb
    pasta = Path(tempfile.mkdtemp()) / "aquisicao"
    pasta.mkdir()
    return extrator.executar(pasta), pasta


# ---------------------------------------------------------------------------
print("\n[1] Aparelho que nao respondeu NUNCA rende 'relatorio gerado'")
# ---------------------------------------------------------------------------
resultado, pasta = rodar_caracteristicas(
    ADBDublado(getprop="", stderr_getprop="error: device offline", codigo_getprop=1)
)
checar("getprop vazio e FALHA", not resultado.sucesso)
checar("a mensagem diz que nada foi obtido", "NÃO obtidas" in resultado.mensagem)
checar("e carrega o motivo devolvido pelo ADB", "device offline" in resultado.mensagem)
checar("nenhum relatorio em prosa e gravado",
       not (pasta / "device_specs" / "caracteristicas_tecnicas.txt").exists())
checar("nenhuma ficha estruturada e gravada", ler_caracteristicas(pasta).vazio)
checar("mas a tentativa fica preservada (stderr)",
       "device offline" in (pasta / "device_specs" / "getprop_bruto_stderr.txt")
       .read_text(encoding="utf-8"))

# Codigo de saida zero com saida que nao e getprop: tambem nao e dado.
resultado, _ = rodar_caracteristicas(ADBDublado(getprop="algum texto qualquer"))
checar("saida sem nenhuma propriedade tambem e FALHA", not resultado.sucesso)


# ---------------------------------------------------------------------------
print("\n[2] Leitura completa: os campos saem do getprop, e o bruto fica")
# ---------------------------------------------------------------------------
resultado, pasta = rodar_caracteristicas(ADBDublado(getprop=GETPROP_COMPLETO))
ficha = ler_caracteristicas(pasta).valores
prosa = (pasta / "device_specs" / "caracteristicas_tecnicas.txt").read_text(encoding="utf-8")

checar("leitura completa e sucesso", resultado.sucesso)
checar("sem ressalva", not indica_ressalva(resultado.detalhes))
checar("modelo apurado", ficha.get("modelo") == "moto x4")
checar("estado da criptografia apurado", ficha.get("estado_criptografia") == "encrypted")
checar("boot verificado apurado", ficha.get("boot_verificado") == "green")
checar("bootloader apurado", ficha.get("bootloader_travado") == "1")
checar("o identificador de conexao e o serial do caso",
       ficha.get("id_conexao") == "0030000000")
checar("o getprop bruto e preservado inteiro",
       (pasta / "device_specs" / "getprop_bruto.txt").read_text(encoding="utf-8")
       == GETPROP_COMPLETO)
checar("a data da coleta declara o fuso",
       any(l.startswith("Data/Hora") and ("+" in l or "-0" in l) for l in prosa.splitlines()))
checar("campo que o aparelho nao declarou aparece como NAO APURADO",
       "NÃO APURADO" in prosa)  # operadora_sim e versao_bootloader nao vieram
checar("e nunca como linha em branco",
       not any(l.rstrip().endswith(":") for l in prosa.splitlines()[:30]))


# ---------------------------------------------------------------------------
print("\n[3] Nucleo incompleto: sucesso COM ressalva, nomeando o que faltou")
# ---------------------------------------------------------------------------
sem_serie = "\n".join(l for l in GETPROP_COMPLETO.splitlines() if "serialno" not in l)
resultado, _ = rodar_caracteristicas(ADBDublado(getprop=sem_serie))
checar("ainda e sucesso: o aparelho foi identificado", resultado.sucesso)
checar("mas com ressalva visivel ao examinador", indica_ressalva(resultado.detalhes))
checar("que nomeia o campo faltante",
       any("Série" in c for c in resultado.detalhes.get("campos_nao_apurados", [])))
checar("e a mensagem diz qual", "Série" in resultado.mensagem)

checar("interpretar_getprop ignora linha fora do formato",
       interpretar_getprop("lixo\n[a.b]: [c]\n[vazio]: []") == {"a.b": "c", "vazio": ""})


# ---------------------------------------------------------------------------
print("\n[4] O modulo de SMS passa a CONSULTAR o MMS que anunciava")
# ---------------------------------------------------------------------------
SMS = "Row: 0 _id=1, address=+5511911112222, date=1787513890000, read=1, type=1, body=Oi"
MMS_CABECALHOS = (
    "Row: 0 _id=7, thread_id=3, date=1787513900, msg_box=1, read=1, sub=NULL\n"
    "Row: 1 _id=8, thread_id=3, date=1787514000, msg_box=2, read=1, sub=Foto"
)
MMS_PARTES = (
    "Row: 0 _id=20, mid=7, ct=application/smil, name=NULL, text=<smil></smil>\n"
    "Row: 1 _id=21, mid=7, ct=text/plain, name=NULL, text=Olha, chegou a encomenda\n"
    "Row: 2 _id=22, mid=7, ct=image/jpeg, name=foto.jpg, text=NULL\n"
    "Row: 3 _id=23, mid=8, ct=image/png, name=recibo.png, text=NULL"
)
ENDERECOS = {
    "7": "Row: 0 _id=1, msg_id=7, address=+5511933334444, type=137\n"
         "Row: 1 _id=2, msg_id=7, address=insert-address-token, type=151",
    "8": "Row: 0 _id=3, msg_id=8, address=insert-address-token, type=137\n"
         "Row: 1 _id=4, msg_id=8, address=+5511955556666, type=151",
}
RECUSA = (
    "Error while accessing provider:mms\njava.lang.SecurityException: Permission "
    "Denial: reading com.android.providers.telephony.MmsProvider requires "
    "android.permission.READ_SMS"
)
JPEG = b"\xff\xd8\xff\xe0" + b"\r\n\x00\x1a" * 64  # bytes que `adb shell` corromperia


class ADBComMMS(ADBDublado):
    def __init__(self, recusar_mms=False):
        super().__init__(getprop="")
        self.recusar_mms = recusar_mms
        self.fluxos = []

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        comando = linha(argumentos)
        self.comandos.append(comando)
        if "getprop ro.build.version.sdk" in comando:
            return ResultadoComando(0, "33", "")
        if "content query" not in comando:
            return ResultadoComando(0, "", "")
        uri = argumentos[-1]
        if uri.startswith("content://mms"):
            if self.recusar_mms:
                return ResultadoComando(0, "", RECUSA)
            if uri == "content://mms":
                return ResultadoComando(0, MMS_CABECALHOS, "")
            if uri == "content://mms/part":
                return ResultadoComando(0, MMS_PARTES, "")
            if uri.endswith("/addr"):
                return ResultadoComando(0, ENDERECOS[uri.split("/")[-2]], "")
        if uri == "content://sms":
            return ResultadoComando(0, SMS, "")
        return ResultadoComando(0, "", "")

    def stream_binario(self, argumentos, ao_receber_bloco, tamanho_bloco=0, cancelado=None):
        self.fluxos.append(linha(argumentos))
        if argumentos[-1].endswith("/23"):
            return ResultadoStream(1, "java.io.FileNotFoundException: No entry", 0)
        ao_receber_bloco(JPEG)
        return ResultadoStream(0, "", len(JPEG))

    def pacote_instalado(self, pacote):
        return False


def rodar_sms(adb):
    extrator = SMSExtractor()
    extrator.adb = adb
    extrator.device.adb = adb
    pasta = Path(tempfile.mkdtemp()) / "aquisicao"
    pasta.mkdir()
    return extrator.executar(pasta), pasta / "sms"


adb = ADBComMMS()
resultado, pasta_sms = rodar_sms(adb)

checar("content://mms foi consultado",
       any(c.endswith("--uri content://mms") for c in adb.comandos))
checar("content://mms/part foi consultado",
       any(c.endswith("content://mms/part") for c in adb.comandos))
checar("os enderecos de CADA mensagem foram consultados",
       all(any(c.endswith(f"content://mms/{i}/addr") for c in adb.comandos) for i in "78"))
checar("so os anexos sao lidos em binario -- texto e SMIL nao",
       sorted(f.split("/")[-1] for f in adb.fluxos) == ["22", "23"])
checar("e pelo exec-out, nunca por adb shell",
       all(f.startswith("exec-out ") for f in adb.fluxos))

anexo = pasta_sms / "mms_anexos" / "parte_22.bin"
checar("o anexo chega byte a byte", anexo.read_bytes() == JPEG)
checar("com o hash gravado na aquisicao", anexo.with_name("parte_22.bin.sha256").is_file())

checar("anexo que falhou NAO deixa arquivo de anexo",
       not (pasta_sms / "mms_anexos" / "parte_23.bin").exists())
checar("deixa o registro da tentativa, com o erro do aparelho",
       "FileNotFoundException" in (pasta_sms / "mms_anexos" / "parte_23_NAO_OBTIDA.txt")
       .read_text(encoding="utf-8"))
checar("o modulo tem sucesso (ha dado)", resultado.sucesso)
checar("com ressalva de copia incompleta", resultado.detalhes.get("copia_incompleta") is True)
checar("que nomeia a parte nao lida", resultado.detalhes.get("anexos_mms_nao_obtidos") == ["23"])
checar("e aparece na mensagem", "23" in resultado.mensagem and "Ressalva" in resultado.mensagem)


# ---------------------------------------------------------------------------
print("\n[5] O normalizador junta cabecalho, partes e enderecos")
# ---------------------------------------------------------------------------
mms = normalizar_mms(
    (pasta_sms / "mms_cabecalhos.txt").read_text(encoding="utf-8"),
    "sms/mms_cabecalhos.txt", None, pasta_sms,
)
checar("duas mensagens MMS", mms.total == 2)
recebida, enviada = mms.registros
checar("recebida: o numero e o do REMETENTE", recebida.campos["numero"] == "+5511933334444")
checar("enviada: o numero e o do DESTINATARIO", enviada.campos["numero"] == "+5511955556666")
checar("o marcador do proprio aparelho nunca vira numero",
       "insert-address-token" not in recebida.campos["numero"] + enviada.campos["numero"])
checar("o texto vem da parte text/plain, com a virgula inteira",
       recebida.campos["conteudo"] == "Olha, chegou a encomenda")
checar("o SMIL nao e apresentado como conteudo", "smil" not in recebida.campos["conteudo"])
checar("o anexo e nomeado com tipo e parte",
       "foto.jpg" in recebida.campos["anexo"] and "parte 22" in recebida.campos["anexo"])
checar("sentido pelo msg_box",
       (recebida.campos["direcao"], enviada.campos["direcao"]) == ("Recebida", "Enviada"))
checar("a data do MMS, em SEGUNDOS, nao vai para 1970",
       recebida.momento is not None and recebida.momento.year == 2026)
checar("o SMS continua sendo lido a parte, sem contar MMS",
       normalizar_sms((pasta_sms / "sms_todas.txt").read_text(encoding="utf-8")).total == 1)

# Partes ausentes: o campo DIZ, em vez de sair em branco.
(pasta_sms / "mms_partes.txt").unlink()
sem_partes = normalizar_mms(MMS_CABECALHOS, "x", None, pasta_sms)
checar("sem as partes, o conteudo declara que nao foi coletado",
       "não coletadas" in sem_partes.registros[0].campos["conteudo"])


# ---------------------------------------------------------------------------
print("\n[6] MMS recusado e SMS obtido: ressalva, nunca 'nao ha MMS'")
# ---------------------------------------------------------------------------
resultado, pasta_sms = rodar_sms(ADBComMMS(recusar_mms=True))
checar("o SMS veio, entao ha sucesso", resultado.sucesso)
checar("com a recusa declarada", resultado.detalhes.get("acesso_negado") is True)
bruto = (pasta_sms / "mms_cabecalhos.txt").read_text(encoding="utf-8")
checar("o bruto do MMS guarda a recusa", "Permission Denial" in bruto)
recusado = normalizar_mms(bruto, "sms/mms_cabecalhos.txt", None, pasta_sms)
checar("e o normalizador a reconhece como recusa", recusado.acesso_negado)
checar("explicando o vazio como recusa, nao como ausencia",
       "RECUSOU" in recusado.explicacao_do_vazio)


print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
