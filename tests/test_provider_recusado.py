"""
Testes da recusa de Content Provider num aparelho SEM root.

Achado na primeira execucao da suite contra uma ROM DE FABRICANTE -- um
moto x4 de fabrica, Android 9, build `user`, bootloader travado -- em
04/10/2026. Ate entao o Android so fora exercitado contra o emulador AOSP,
onde o shell do ADB tem as permissoes e os providers respondem.

NUM APARELHO DE FABRICA ELES NAO RESPONDEM. Medido no aparelho:

    content://call_log/calls -> codigo 0, stdout vazio, stderr 1373 bytes
    content://sms            -> codigo 0, stdout vazio, stderr  954 bytes
    content://.../phones     -> codigo 0, stdout 3437 bytes, stderr vazio

Repare no codigo de saida: **ZERO mesmo recusando**. O stderr e o unico
sinal da recusa -- e `ADBClient.executar()` devolve so o stdout, por uma
razao que era boa ("nunca devolver mensagem de erro travestida de dado do
aparelho") e tinha um custo que ninguem tinha medido: a recusa sumia.

Com ela sumida, `saida_indica_acesso_negado("")` respondia False, e
`avaliar_consulta_a_provider(obteve_dado=False, acesso_negado=False)` caia
no ramo mais perigoso que existe nesta ferramenta:

    "Mensagens SMS/MMS: o provider respondeu a consulta e nao retornou
     nenhum registro."   -- com sucesso=True

RECUSA DE ACESSO virando AFIRMACAO DE AUSENCIA. Num laudo, "o aparelho nao
possui mensagens SMS". E a mesma familia do defeito do `dd`, onde erro de
leitura e fim de volume eram a mesma condicao de saida.

A logica de `avaliar_consulta_a_provider` sempre esteve certa. Ela estava
sendo alimentada com mentira.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando  # noqa: E402
from core.android.extractors.contacts_calls import ContatosChamadasExtractor  # noqa: E402
from core.android.extractors.sms import SMSExtractor  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def linha(argumentos):
    return " ".join(argumentos)


# Texto real devolvido pelo moto x4, encurtado.
RECUSA_CALL_LOG = (
    "Error while accessing provider:call_log\n"
    "java.lang.SecurityException: Permission Denial: opening provider "
    "com.android.providers.contacts.CallLogProvider from (null) (pid=13066, "
    "uid=2000) requires android.permission.READ_CALL_LOG or "
    "android.permission.WRITE_CALL_LOG\n"
    "\tat android.os.Parcel.createException(Parcel.java:1950)"
)
RECUSA_SMS = (
    "Error while accessing provider:sms\n"
    "java.lang.SecurityException: Permission Denial: reading "
    "com.android.providers.telephony.SmsProvider uri content://sms from "
    "pid=13078, uid=2000 requires android.permission.READ_SMS"
)
CONTATOS = (
    "Row: 0 phonetic_name=NULL, display_name=Fulano, data1=11999990000\n"
    "Row: 1 phonetic_name=NULL, display_name=Beltrano, data1=11988880000"
)


class ADBDeAparelhoDeFabrica:
    """
    Reproduz o moto x4: providers de SMS e chamadas recusam no stderr, com
    codigo de saida ZERO; o de contatos responde normalmente.
    """

    serial = "0030000000"

    def definir_serial(self, serial):
        self.serial = serial

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        comando = linha(argumentos)
        if "call_log" in comando:
            return ResultadoComando(0, "", RECUSA_CALL_LOG)
        if "content://sms" in comando or "content://mms" in comando:
            return ResultadoComando(0, "", RECUSA_SMS)
        if "contacts" in comando:
            return ResultadoComando(0, CONTATOS, "")
        if "ro.build.version.sdk" in comando:
            return ResultadoComando(0, "28", "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos, timeout, vincular_serial).stdout

    def pacote_instalado(self, pacote):
        # Nenhum candidato a `adb backup` instalado: a via alternativa nao
        # entra, e o teste mede a recusa do provider, nao o fallback.
        return False


def preparar(extrator):
    extrator.adb = ADBDeAparelhoDeFabrica()
    return extrator


# ---------------------------------------------------------------------------
print("\n[1] SMS inteiramente recusado NUNCA vira 'nao ha mensagens'")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    saida = Path(tmp) / "aquisicao"
    saida.mkdir()
    resultado = preparar(SMSExtractor()).executar(saida)

    checar("recusa total e FALHA, nunca sucesso", not resultado.sucesso)
    checar("a recusa e declarada no resultado",
           resultado.detalhes.get("acesso_negado") is True)
    checar("e nenhum dado e dado como obtido",
           resultado.detalhes.get("algum_dado_obtido") is False)
    checar("a mensagem NAO afirma que o provider respondeu",
           "respondeu à consulta" not in resultado.mensagem)
    checar("e proibe explicitamente a conclusao negativa",
           "NÃO se pode concluir" in resultado.mensagem)

    brutos = sorted((saida / "sms").glob("*.txt"))
    checar("os arquivos brutos foram gravados", len(brutos) >= 1)
    checar("e preservam a recusa, em vez de ficarem com zero byte",
           all("Permission Denial" in a.read_text(encoding="utf-8") for a in brutos))


# ---------------------------------------------------------------------------
print("\n[2] Recusa PARCIAL: o que veio e aproveitado, o que faltou e declarado")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    saida = Path(tmp) / "aquisicao"
    saida.mkdir()
    resultado = preparar(ContatosChamadasExtractor()).executar(saida)

    checar("contatos vieram, entao o modulo tem sucesso", resultado.sucesso)
    checar("mas a recusa das chamadas e declarada",
           resultado.detalhes.get("acesso_negado") is True)
    checar("e a mensagem carrega a ressalva",
           "Ressalva" in resultado.mensagem)

    bruto_chamadas = saida / "contacts_calls" / "registro_chamadas_bruto.txt"
    bruto_contatos = saida / "contacts_calls" / "agenda_contatos_bruta.txt"
    checar("o bruto das chamadas guarda a recusa",
           "Permission Denial" in bruto_chamadas.read_text(encoding="utf-8"))
    checar("o bruto dos contatos guarda os dados, nao a recusa",
           "Row: 0" in bruto_contatos.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
print("\n[3] O codigo de saida ZERO nao pode ser usado como sinal")
# ---------------------------------------------------------------------------
adb = ADBDeAparelhoDeFabrica()
for uri in ("content://call_log/calls", "content://sms"):
    r = adb.executar_detalhado(["shell", "content", "query", "--uri", uri])
    checar(f"{uri}: o Android recusa com codigo 0", r.codigo_saida == 0)
    checar(f"{uri}: stdout vazio -- sozinho, indistinguivel de 'sem dados'",
           r.stdout == "")
    checar(f"{uri}: e a recusa so existe no stderr",
           "Permission Denial" in r.stderr)

checar("executar() -- so stdout -- perde a recusa por completo",
       adb.executar(["shell", "content", "query", "--uri", "content://sms"]) == "")


# ---------------------------------------------------------------------------
print("\n[4] Pasta encontrada e VAZIA nao e aquisicao")
# ---------------------------------------------------------------------------
# Mesmo aparelho, mesmo dia: a arvore /sdcard/WhatsApp existia e rendeu 22
# arquivos somando ZERO byte -- todos `.nomedia`, marcadores que pedem ao
# Android para nao indexar a pasta. O modulo contava ARQUIVO em vez de
# CONTEUDO, dava a localizacao como 'com dados' e declarava sucesso com
# '0 byte(s)' escrito na propria mensagem. Estrutura de pastas do
# aplicativo passando por acervo coletado.
from core.android.extractors.whatsapp import WhatsAppExtractor  # noqa: E402


class ExtratorComCopiaVazia(WhatsAppExtractor):
    """Reproduz o resultado medido no moto x4: arquivos > 0, bytes == 0."""

    def copiar_caminho_reconciliado(self, *argumentos, **nomeados):
        raise NotImplementedError

    def consolidar_copias(self, copias):
        return {
            'arquivos_copiados': 22,
            'bytes_copiados': 0,
            'caminhos_com_dados': ['/sdcard/WhatsApp/Media'],
            'caminhos_negados': [],
        }

    def consolidar_reconciliacao(self, aquisicoes):
        return {}

    def adquirir_caminho(self, *argumentos, **nomeados):
        class _Vazia:
            copia = None
        return _Vazia()


with tempfile.TemporaryDirectory() as tmp:
    saida = Path(tmp) / 'aquisicao'
    saida.mkdir()
    extrator = ExtratorComCopiaVazia()
    extrator.adb = ADBDeAparelhoDeFabrica()
    resultado = extrator.executar(saida)

    checar('zero byte copiado NAO e sucesso', not resultado.sucesso)
    checar('a contagem de arquivos continua visivel',
           resultado.detalhes.get('arquivos_copiados') == 22)
    checar('e o total de bytes tambem', resultado.detalhes.get('bytes_copiados') == 0)
    checar('a mensagem diz que sao marcadores vazios',
           '.nomedia' in resultado.mensagem)
    checar('e proibe a leitura de que nao ha mensagens',
           'NAO SIGNIFICA AUSENCIA DE MENSAGENS'.replace('NAO','NÃO').replace('AUSENCIA','AUSÊNCIA')
           in resultado.mensagem)


print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
