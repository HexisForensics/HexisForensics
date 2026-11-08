"""
Testes dos modulos de completude acrescentados a extracao Android:
identificacao (IMEI e contas), artefatos de atividade do sistema,
mensageiros alem do WhatsApp e copia dos APKs instalados.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoPull, SituacaoPull
from core.android.extractors.apks import ApksExtractor
from core.android.extractors.artefatos_sistema import COLETAS, ArtefatosSistemaExtractor
from core.android.extractors.identificacao import (
    IdentificacaoExtractor,
    extrair_digitos_de_parcel,
    imei_valido_por_luhn,
)
from core.android.extractors.mensageiros import MensageirosExtractor

falhas = []


def linha_do_comando(argumentos):
    """Linha unica que o `adb shell` entrega ao shell do aparelho."""
    return " ".join(argumentos)


def alvo_do_comando(argumentos):
    """Caminho entre aspas dentro da linha do comando, sem a barra final."""
    linha = linha_do_comando(argumentos)
    return linha.split("'")[1].rstrip("/") if "'" in linha else ""




def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar(classe, adb):
    extrator = classe.__new__(classe)
    extrator._log_callback = lambda mensagem: None
    extrator._progress_callback = lambda percentual: None
    extrator._cancelado = False
    extrator.adb = adb
    return extrator


class ADBBase:
    """Base dos ADBs falsos: tudo vazio, salvo o que a subclasse programar."""

    instalados = ()

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(0, self.responder(argumentos), "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos, timeout).stdout

    def responder(self, argumentos):
        return ""

    def pacote_instalado(self, pacote):
        return pacote in self.instalados

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 0, "", "", 0, 0, SituacaoPull.INEXISTENTE
        )


# ---------------------------------------------------------------------------
print("\n[1] Validacao do IMEI pelo digito verificador (Luhn)")
# ---------------------------------------------------------------------------
checar("IMEI valido e aceito", imei_valido_por_luhn("490154203237518") is True)
checar("IMEI com digito verificador errado e recusado", imei_valido_por_luhn("490154203237519") is False)
checar("sequencia de 14 digitos e recusada", imei_valido_por_luhn("49015420323751") is False)
checar("sequencia com letra e recusada", imei_valido_por_luhn("49015420323751X") is False)
checar("string vazia e recusada", imei_valido_por_luhn("") is False)

# ---------------------------------------------------------------------------
print("\n[2] Leitura do IMEI a partir do Parcel do service call")
# ---------------------------------------------------------------------------
PARCEL = (
    "Result: Parcel(\n"
    "  0x00000000: 00000000 0000000f 00390034 00310030 "
    "'........4.9.0.1.5.4.2.0.3.2.3.7.5.1.8.')\n"
)
digitos = extrair_digitos_de_parcel(PARCEL)
checar("o IMEI e reconstruido do Parcel em UTF-16", "490154203237518" in digitos)
checar("Parcel sem trecho entre aspas nao produz numero", extrair_digitos_de_parcel("Result: Parcel()") == [])
checar("saida vazia nao produz numero", extrair_digitos_de_parcel("") == [])


class ADBComImei(ADBBase):
    def responder(self, argumentos):
        if "iphonesubinfo" in argumentos:
            return PARCEL
        if "account" in argumentos:
            return (
                "Accounts: 2\n"
                "  Account {name=fulano@gmail.com, type=com.google}\n"
                "  Account {name=+5511999999999, type=com.whatsapp}\n"
            )
        return ""


class ADBSemImei(ADBBase):
    def responder(self, argumentos):
        if "iphonesubinfo" in argumentos:
            return "Result: Parcel(00000000 'Permission Denial')"
        if "account" in argumentos:
            return "Account {name=fulano@gmail.com, type=com.google}"
        return ""


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(IdentificacaoExtractor, ADBComImei()).executar(pasta_caso)
    checar("IMEI lido e reportado no resultado", resultado.detalhes["imei"] == "490154203237518")
    checar("extracao com IMEI e sucesso", resultado.sucesso is True)
    checar("contas cadastradas sao contadas", resultado.detalhes["contas_encontradas"] == 2)
    resumo = (pasta_caso / "identificacao" / "resumo_identificacao.txt").read_text(encoding="utf-8")
    checar("resumo traz o IMEI", "490154203237518" in resumo)
    checar("resumo traz as contas", "fulano@gmail.com" in resumo)
    checar(
        "saida bruta de cada via e preservada como evidencia",
        (pasta_caso / "identificacao" / "leituras_brutas" / "dumpsys_iphonesubinfo.txt").exists(),
    )

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(IdentificacaoExtractor, ADBSemImei()).executar(pasta_caso)
    checar("IMEI nao obtido nao e inventado", resultado.detalhes["imei"] == "")
    checar("IMEI nao obtido vira ressalva, nao sucesso liso", resultado.detalhes.get("acesso_negado") is True)
    checar("contas continuam sendo coletadas", resultado.detalhes["contas_encontradas"] == 1)
    resumo = (pasta_caso / "identificacao" / "resumo_identificacao.txt").read_text(encoding="utf-8")
    checar("resumo explica que a ausencia e recusa do sistema", "NÃO OBTIDO" in resumo)
    checar("resumo indica vias alternativas ao examinador", "*#06#" in resumo)

# ---------------------------------------------------------------------------
print("\n[3] Artefatos de atividade do sistema")
# ---------------------------------------------------------------------------
class ADBComArtefatos(ADBBase):
    def responder(self, argumentos):
        if "usagestats" in argumentos:
            return "pkg=com.whatsapp lastTimeUsed=2026-08-22 23:40:11 totalTimeInForeground=1220000"
        if "wifi" in argumentos:
            return "Networks: SSID=CASA_2G bssid=aa:bb:cc:dd:ee:ff lastConnected=2026-08-22"
        return ""


class ADBQueRecusaTudo(ADBBase):
    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(1, "", "device offline")


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(ArtefatosSistemaExtractor, ADBComArtefatos()).executar(pasta_caso)
    checar("coleta parcial e sucesso", resultado.sucesso is True)
    checar("artefatos com conteudo sao contabilizados", len(resultado.detalhes["artefatos_obtidos"]) == 2)
    checar("coleta parcial vira ressalva", resultado.detalhes.get("copia_incompleta") is True)
    indice = (pasta_caso / "artefatos_sistema" / "INDICE.txt").read_text(encoding="utf-8")
    checar("indice descreve o conteudo de cada arquivo", "usagestats" in indice or "uso de cada" in indice)
    checar("indice adverte contra concluir ausencia de evento", "NÃO autoriza" in indice)

with tempfile.TemporaryDirectory() as td:
    resultado = montar(ArtefatosSistemaExtractor, ADBQueRecusaTudo()).executar(Path(td))
    checar("nenhum artefato obtido e FALHA", resultado.sucesso is False)
    # A contagem sai de COLETAS, e nao de um numero digitado aqui: comando
    # novo no modulo passava a falhar este teste sem que nada estivesse
    # errado, e a tentacao seria corrigir o numero sem olhar o motivo.
    checar(
        "as recusas ficam listadas",
        len(resultado.detalhes["artefatos_recusados"]) == len(COLETAS),
    )

# ---------------------------------------------------------------------------
print("\n[4] Mensageiros alem do WhatsApp")
# ---------------------------------------------------------------------------
class ADBSemMensageiros(ADBBase):
    instalados = ()


class ADBComTelegram(ADBBase):
    instalados = ("org.telegram.messenger",)

    def responder(self, argumentos):
        if "find" in linha_do_comando(argumentos):
            raiz = alvo_do_comando(argumentos)
            if raiz == "/sdcard/Telegram":
                return "/sdcard/Telegram/Telegram Images/foto.jpg"
        return ""

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        if caminho_remoto != "/sdcard/Telegram":
            return super().pull(caminho_remoto, caminho_local, preservar_timestamps)
        destino = Path(caminho_local) / "Telegram" / "Telegram Images"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "foto.jpg").write_text("imagem", encoding="utf-8")
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 0, "", "", 1, 6, SituacaoPull.OK
        )


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(MensageirosExtractor, ADBSemMensageiros()).executar(pasta_caso)
    checar("nenhum mensageiro instalado nao e falha", resultado.sucesso is True)
    checar("o resultado diz que nenhum estava instalado", "Nenhum" in resultado.mensagem)
    relatorio = (pasta_caso / "mensageiros" / "RELATORIO_MENSAGEIROS.txt").read_text(encoding="utf-8")
    checar("relatorio lista os nao instalados", "Telegram" in relatorio)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(MensageirosExtractor, ADBComTelegram()).executar(pasta_caso)
    checar("mensageiro instalado e detectado", resultado.detalhes["aplicativos_instalados"] == ["Telegram"])
    checar("midia externa adquirida e contabilizada", resultado.detalhes["aplicativos_com_dados"] == ["Telegram"])
    relatorio = (pasta_caso / "mensageiros" / "RELATORIO_MENSAGEIROS.txt").read_text(encoding="utf-8")
    checar(
        "relatorio adverte que ausencia aqui nao prova ausencia de conversa",
        "não sustenta conclusão" in relatorio,
    )

# ---------------------------------------------------------------------------
print("\n[5] Copia dos APKs instalados pelo usuario")
# ---------------------------------------------------------------------------
class ADBComApks(ADBBase):
    def responder(self, argumentos):
        if "packages" in argumentos:
            return (
                "package:/data/app/~~abc==/com.exemplo.app-1/base.apk=com.exemplo.app\n"
                "package:/data/app/~~def==/com.outro.app-2/base.apk=com.outro.app\n"
                "linha invalida que deve ser ignorada\n"
            )
        return ""

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        destino = Path(caminho_local)
        destino.mkdir(parents=True, exist_ok=True)
        if "com.exemplo.app" in caminho_remoto:
            (destino / "base.apk").write_text("conteudo do apk", encoding="utf-8")
            return ResultadoPull(caminho_remoto, destino, 0, "", "", 1, 15, SituacaoPull.OK)
        return ResultadoPull(caminho_remoto, destino, 1, "", "denied", 0, 0, SituacaoPull.ACESSO_NEGADO)


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(ApksExtractor, ADBComApks()).executar(pasta_caso)
    checar("linhas invalidas do pm list sao ignoradas", resultado.detalhes["aplicativos_de_usuario"] == 2)
    checar("APK copiado e contabilizado", resultado.detalhes["apks_copiados"] == 1)
    checar("pacote sem APK vira ressalva", resultado.detalhes.get("copia_incompleta") is True)
    checar("pacote sem APK e nomeado", resultado.detalhes["pacotes_sem_apk"] == ["com.outro.app"])
    inventario = (pasta_caso / "apks" / "INVENTARIO_APKS.txt").read_text(encoding="utf-8")
    checar("inventario traz o SHA-256 do APK copiado", "com.exemplo.app/base.apk" in inventario)
    checar("inventario nomeia o pacote sem APK", "com.outro.app" in inventario)

with tempfile.TemporaryDirectory() as td:
    resultado = montar(ApksExtractor, ADBQueRecusaTudo()).executar(Path(td))
    checar("nao conseguir listar pacotes e FALHA", resultado.sucesso is False)

# ---------------------------------------------------------------------------
print("\n[6] Deteccao de pacote instalado usa comparacao EXATA")
# ---------------------------------------------------------------------------
from core.android.adb_client import ADBClient


class ADBListaPacotes(ADBClient):
    """Reproduz a busca por substring que o `pm list packages` faz."""

    catalogo = [
        "com.whatsapp.w4b",
        "com.google.android.apps.docs",
        "com.google.android.apps.docs.editors.docs",
    ]

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        filtro = argumentos[-1]
        return "\n".join(f"package:{p}" for p in self.catalogo if filtro in p)


listador = ADBListaPacotes(caminho_binario=Path("adb"))

checar(
    "pacote realmente instalado e detectado",
    listador.pacote_instalado("com.whatsapp.w4b") is True,
)
checar(
    "WhatsApp NAO e dado como instalado quando so ha WhatsApp Business",
    listador.pacote_instalado("com.whatsapp") is False,
)
checar(
    "prefixo truncado de outro pacote NAO conta como instalado",
    listador.pacote_instalado("com.google.android.apps.doc") is False,
)
checar(
    "pacote exato convive com homonimo mais longo",
    listador.pacote_instalado("com.google.android.apps.docs") is True,
)
checar("pacote inexistente segue False", listador.pacote_instalado("nao.existe") is False)


class ADBListaComCaminho(ADBListaPacotes):
    """Variante `pm list packages -f`, que traz caminho=pacote."""

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        filtro = argumentos[-1]
        return "\n".join(
            f"package:/data/app/{p}-1/base.apk={p}" for p in self.catalogo if filtro in p
        )


com_caminho = ADBListaComCaminho(caminho_binario=Path("adb"))
checar(
    "formato com caminho tambem e comparado corretamente",
    com_caminho.pacote_instalado("com.whatsapp.w4b") is True,
)
checar(
    "e o falso positivo tambem nao ocorre nesse formato",
    com_caminho.pacote_instalado("com.whatsapp") is False,
)

# ---------------------------------------------------------------------------
print("\n[APKs] 'respondeu vazio' nao e 'nao respondeu'")
# ---------------------------------------------------------------------------
# Defeito encontrado na primeira execucao contra um Android 13 recem
# instalado, sem aplicativo de usuario nenhum. A listagem devolvia {} tanto
# quando o comando FALHAVA quanto quando ele RESPONDIA que nao ha aplicativo,
# e o modulo relatava "o aparelho nao respondeu a consulta" nos dois casos --
# falso no segundo, e com conclusao oposta para quem le o laudo.
import tempfile  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from core.android.extractors.apks import ApksExtractor  # noqa: E402


class ADBSemAppsDoUsuario(ADBBase):
    """`pm list packages -3` responde, e a lista vem vazia."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(0, "", "")


class ADBConsultaFalhou(ADBBase):
    """O comando nao pode ser executado no aparelho."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(1, "", "device offline")


with tempfile.TemporaryDirectory() as td:
    r = montar(ApksExtractor, ADBSemAppsDoUsuario()).executar(_Path(td) / "a")
    checar("lista vazia com consulta OK e SUCESSO", r.sucesso is True)
    checar("a mensagem diz que o aparelho RESPONDEU", "respondeu à consulta" in r.mensagem)
    checar(
        "e distingue da impossibilidade de consultar",
        "diferente de não ter sido possível consultar" in r.mensagem,
    )
    checar("com contagem zero nos detalhes", r.detalhes.get("aplicativos_de_usuario") == 0)
    checar(
        "e o inventario e gravado mesmo sem APK",
        (_Path(td) / "a" / "apks" / "inventario_apks.txt").is_file(),
    )

    r = montar(ApksExtractor, ADBConsultaFalhou()).executar(_Path(td) / "b")
    checar("consulta que FALHOU e FALHA", r.sucesso is False)
    checar("e a mensagem diz que o comando falhou", "o comando falhou" in r.mensagem)
    checar(
        "sem afirmar nada sobre os aplicativos existentes",
        "Nada se pode afirmar" in r.mensagem,
    )

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
