"""
Regressoes encontradas no exame de um Samsung SM-G360BT (Android 5.0.2,
API 21) -- o primeiro aparelho antigo e com uso real testado.

Todos os defeitos cobertos aqui sao da mesma familia, que e a mais grave
possivel nesta ferramenta: a suite AFIRMANDO COISA FALSA no registro do
caso. Um arquivo faltante que nunca existiu, uma causa tecnica presumida e
errada, um aparelho perdido atribuido a problema de cabo, e um "extraidos"
sobre modulo que nao obteve dado nenhum.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoPull, SituacaoPull
from core.android.device import AndroidDevice
from core.android.extractors.base import AndroidExtractor
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor
from core.android.extractors.identificacao import (
    IdentificacaoExtractor,
    motivo_de_recusa,
    texto_de_parcel,
)

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
    extrator._log_callback = lambda m: None
    extrator._progress_callback = lambda p: None
    extrator._cancelado = False
    extrator.adb = adb
    return extrator


# Saida real do aparelho: o shell do Android 5 nao tem o comando `find`.
SEM_FIND = "/system/bin/sh: find: not found"

# Formato real do `ls -R` do toolbox: um bloco por diretorio, e nenhuma
# indicacao de que uma entrada e arquivo ou pasta.
LS_RECURSIVO = """/sdcard/DCIM:
Camera
.thumbnails

/sdcard/DCIM/Camera:
20260822_161500.jpg
20260822_161512.jpg

/sdcard/DCIM/.thumbnails:
cache.db
"""

# Parcel real devolvido pelo SM-G360BT ao pedir o IMEI.
PARCEL_RECUSA = (
    "Result: Parcel(\n"
    "  0x00000000: ffffffff 00000069 00650052 00750071 '....i...R.e.q.u.'\n"
    "  0x00000010: 00720069 00730065 00520020 00410045 'i.r.e.s. .R.E.A.'\n"
    "  0x00000020: 005f0044 00480050 004e004f 005f0045 'D._.P.H.O.N.E._.'\n"
    "  0x00000030: 00540053 00540041 003a0045 004e0020 'S.T.A.T.E.:. .N.'\n"
)


class ADBSemFind:
    """Android antigo: shell sem `find`, porem com `ls -R` funcional."""

    serial = "51183d8f"
    saida_ls = LS_RECURSIVO

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(127, SEM_FIND, "")
        if "ls -R" in linha_do_comando(argumentos):
            return ResultadoComando(0, self.saida_ls, "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        if "whoami" in argumentos:
            return "shell"
        return self.executar_detalhado(argumentos, timeout).stdout

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        destino = Path(caminho_local)
        destino.mkdir(parents=True, exist_ok=True)
        return ResultadoPull(caminho_remoto, destino, 0, "", "", 0, 0, SituacaoPull.VAZIO)


class ADBSemFindNemLs(ADBSemFind):
    """Caso extremo: nenhuma das duas vias de inventario funciona."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(127, SEM_FIND, "")
        if "ls -R" in linha_do_comando(argumentos):
            return ResultadoComando(127, "/system/bin/sh: ls: not found", "")
        return ResultadoComando(0, "", "")


# ---------------------------------------------------------------------------
print("\n[1] Shell sem 'find': o inventario cai para 'ls -R'")
# ---------------------------------------------------------------------------
extrator = montar(FilesystemDumpExtractor, ADBSemFind())
inventario = extrator.inventariar_origem("/sdcard/DCIM")

checar("o inventario e obtido mesmo sem 'find'", inventario.disponivel is True)
checar("a via usada e registrada", inventario.metodo == "ls -R")
ESPERADOS = [
    ".thumbnails/cache.db",
    "Camera/20260822_161500.jpg",
    "Camera/20260822_161512.jpg",
]
checar("os arquivos sao inferidos corretamente", sorted(inventario.arquivos) == ESPERADOS)
checar(
    "diretorios NAO entram como arquivo",
    "Camera" not in inventario.arquivos and ".thumbnails" not in inventario.arquivos,
)
checar("a mensagem de erro do shell nao virou arquivo", not any("not found" in a for a in inventario.arquivos))

# A via preferida continua sendo `find` quando o aparelho a possui.
class ADBComFind(ADBSemFind):
    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(0, "/sdcard/DCIM/foto.jpg", "")
        return ResultadoComando(0, self.saida_ls, "")


inventario = montar(FilesystemDumpExtractor, ADBComFind()).inventariar_origem("/sdcard/DCIM")
checar("com 'find' disponivel, e ele que e usado", inventario.metodo == "find")
checar("e o resultado do find e respeitado", inventario.arquivos == ["foto.jpg"])

# Nenhuma via disponivel: nao se inventa inventario.
inventario = montar(FilesystemDumpExtractor, ADBSemFindNemLs()).inventariar_origem("/sdcard/DCIM")
checar("sem nenhuma via, o inventario fica indisponivel", inventario.disponivel is False)
checar("o motivo cita as duas tentativas", "find" in inventario.motivo_indisponivel and "ls -R" in inventario.motivo_indisponivel)

extrator_sem_vias = montar(FilesystemDumpExtractor, ADBSemFindNemLs())
aquisicao = extrator_sem_vias.adquirir_caminho("/sdcard/DCIM", Path(tempfile.mkdtemp()) / "m")
checar("nenhum arquivo e reportado como faltante", aquisicao.faltantes == [])
checar("origem sem inventario nao recebe contagem", aquisicao.arquivos_na_origem is None)
checar("completude fica NAO VERIFICAVEL", aquisicao.completa is None)

consolidado = AndroidExtractor.consolidar_reconciliacao([aquisicao])
checar("consolidacao nao afirma completude verificavel", consolidado["completude_verificavel"] is False)
checar("consolidacao nao inventa faltantes", consolidado["arquivos_faltantes"] == 0)


class ADBComRuido(ADBSemFindNemLs):
    """Shell que responde ao find com texto irreconhecivel."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(0, "erro inesperado do shell\noutra linha qualquer", "")
        return ResultadoComando(127, "/system/bin/sh: ls: not found", "")


inventario = montar(FilesystemDumpExtractor, ADBComRuido()).inventariar_origem("/sdcard/DCIM")
checar("saida irreconhecivel tambem invalida o inventario", inventario.disponivel is False)
checar("o motivo explica que a saida nao foi reconhecida", "reconhecida" in inventario.motivo_indisponivel)

# Caso de borda observado no aparelho real: ao listar /sdcard (link
# simbolico), o toolbox imprime a propria raiz como se fosse uma entrada.
LS_COM_RAIZ_SOLTA = """/sdcard
/sdcard:
DCIM
Download

/sdcard/DCIM:

/sdcard/Download:
arquivo.pdf
"""


class ADBQueListaRaizSolta(ADBSemFind):
    saida_ls = LS_COM_RAIZ_SOLTA


inventario = montar(FilesystemDumpExtractor, ADBQueListaRaizSolta()).inventariar_origem("/sdcard")
checar("a propria raiz NAO vira arquivo no inventario", inventario.arquivos == ["Download/arquivo.pdf"])
checar("pastas vazias nao produzem entrada", "DCIM" not in inventario.arquivos)

# A via do inventario precisa constar do relatorio de reconciliacao.
with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    montar(FilesystemDumpExtractor, ADBSemFind()).adquirir_caminho(
        "/sdcard/DCIM", pasta_caso / "media", pasta_caso, rotulo="midia_Camera"
    )
    relatorio = (pasta_caso / "aquisicao" / "midia_Camera_reconciliacao.txt").read_text(
        encoding="utf-8"
    )
    checar("o relatorio informa por qual via a origem foi inventariada", "ls -R" in relatorio)

# ---------------------------------------------------------------------------
print("\n[2] O motivo da recusa do IMEI vem do aparelho, nao de presuncao")
# ---------------------------------------------------------------------------
texto = texto_de_parcel(PARCEL_RECUSA)
checar("o Parcel e decodificado", "READ_PHONE_STATE" in texto)
checar("o cabecalho do Parcel e descartado", texto.startswith("Requires"))
checar("a recusa e reconhecida como tal", "READ_PHONE_STATE" in motivo_de_recusa(PARCEL_RECUSA))
checar("Parcel sem recusa nao produz motivo", motivo_de_recusa("Result: Parcel('....359552080000000')") == "")


class ADBAndroid5(ADBSemFind):
    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "iphonesubinfo" in argumentos:
            return ResultadoComando(0, PARCEL_RECUSA, "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        if "ro.build.version.sdk" in argumentos:
            return "21"
        return self.executar_detalhado(argumentos).stdout


class ADBAndroid13(ADBAndroid5):
    def executar(self, argumentos, timeout=None, vincular_serial=True):
        if "ro.build.version.sdk" in argumentos:
            return "33"
        return self.executar_detalhado(argumentos).stdout


with tempfile.TemporaryDirectory() as td:
    antigo = montar(IdentificacaoExtractor, ADBAndroid5())
    antigo.executar(Path(td))
    justificativa = antigo._justificar_ausencia_do_imei(["via_1", "via_2"])

    checar("a justificativa cita o motivo real do aparelho", "READ_PHONE_STATE" in justificativa)
    checar("API 21 detectada", antigo._sdk_detectado == 21)
    checar(
        "NAO afirma a restricao do Android 10 num aparelho anterior a ela",
        "a partir do Android 10 (API 29) o sistema" not in justificativa,
    )
    checar(
        "explica que a recusa decorre da permissao, nao da versao",
        "anterior ao Android 10" in justificativa,
    )

with tempfile.TemporaryDirectory() as td:
    moderno = montar(IdentificacaoExtractor, ADBAndroid13())
    moderno.executar(Path(td))
    justificativa = moderno._justificar_ausencia_do_imei(["via_1"])
    checar("em API 33 a restricao do Android 10 E citada", "API 29" in justificativa)

# ---------------------------------------------------------------------------
print("\n[3] Aparelho que some no meio nao e problema de cabo")
# ---------------------------------------------------------------------------
class ADBVinculadoQueSumiu:
    serial = "51183d8f"

    def verificar_binario(self):
        return True, ""

    def listar_dispositivos(self):
        return []

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return ""


class ADBVinculadoPresente(ADBVinculadoQueSumiu):
    def listar_dispositivos(self):
        return [("51183d8f", "device")]


class ADBOutroAparelho(ADBVinculadoQueSumiu):
    def listar_dispositivos(self):
        return [("OUTRO_SERIAL", "device")]


def montar_com_device(adb):
    extrator = montar(FilesystemDumpExtractor, adb)
    extrator.device = AndroidDevice(adb)
    return extrator


disponivel, motivo = montar_com_device(ADBVinculadoQueSumiu()).disponivel()
checar("aparelho vinculado ausente bloqueia o modulo", disponivel is False)
checar("a mensagem nomeia o aparelho do caso", "51183d8f" in motivo)
checar("a mensagem diz que ocorreu DURANTE a aquisicao", "DURANTE" in motivo)
checar("a mensagem descarta cabo e Depuracao USB", "não são a causa" in motivo)
checar("a mensagem orienta a abrir nova aquisicao", "NOVA" in motivo)

disponivel, _ = montar_com_device(ADBVinculadoPresente()).disponivel()
checar("aparelho vinculado presente libera o modulo", disponivel is True)

disponivel, motivo = montar_com_device(ADBOutroAparelho()).disponivel()
checar("outro aparelho no lugar do vinculado tambem bloqueia", disponivel is False)
checar("e a mensagem continua nomeando o aparelho do caso", "51183d8f" in motivo)

# ---------------------------------------------------------------------------
print("\n[4] Provider consultado sem retorno nao e 'extraido'")
# ---------------------------------------------------------------------------
avaliar = AndroidExtractor.avaliar_consulta_a_provider

sucesso, mensagem = avaliar("Mensagens SMS/MMS", False, True, [])
checar("nada obtido COM recusa e FALHA", sucesso is False)
checar("a mensagem nao diz que houve extracao", "extraíd" not in mensagem.lower())
checar("a mensagem proibe a conclusao negativa", "NÃO se pode concluir" in mensagem)

sucesso, mensagem = avaliar("Mensagens SMS/MMS", False, False, [])
checar("nada obtido SEM recusa continua sendo sucesso", sucesso is True)
checar("e o texto diz que o provider respondeu vazio", "não retornou nenhum registro" in mensagem)

sucesso, mensagem = avaliar("Contatos", True, False, [])
checar("dado obtido e sucesso", sucesso is True)
checar("o texto afirma que houve dado", "dados obtidos" in mensagem)

sucesso, mensagem = avaliar("Contatos", True, True, [Path("backup.ab")])
checar("dado obtido com recusa parcial segue sucesso", sucesso is True)
checar("a recusa parcial vira ressalva explicita", "Ressalva" in mensagem)
checar("o backup alternativo e mencionado", "backup" in mensagem)

# ---------------------------------------------------------------------------
print("\n[5] Backup .ab vazio nao permanece no caso")
# ---------------------------------------------------------------------------
from core.android.adb_client import ADBClient
from core.android import adb_client as modulo_adb

with tempfile.TemporaryDirectory() as td:
    destino = Path(td) / "backup_com.android.phone.ab"

    run_original = modulo_adb.subprocess.run

    def run_que_cria_vazio(argumentos, **kwargs):
        destino.write_bytes(b"")

        class P:
            returncode = 0

        return P()

    modulo_adb.subprocess.run = run_que_cria_vazio
    try:
        obtido = ADBClient(caminho_binario=Path("adb")).backup_pacote("com.android.phone", destino)
    finally:
        modulo_adb.subprocess.run = run_original

    checar("backup de 0 byte e reportado como nao obtido", obtido is False)
    checar("e o arquivo vazio NAO fica na pasta do caso", not destino.exists())

# ---------------------------------------------------------------------------
print("\n[6] Link simbolico: 'ls -R' sem barra final nao recursa")
# ---------------------------------------------------------------------------
# Saida real do aparelho para `ls -R /sdcard` (sem barra): o toolbox imprime
# apenas o nome do link e nao lista nada. Foi assim que uma pasta com 273
# arquivos foi inventariada como VAZIA.
class ADBLinkSimbolico(ADBSemFind):
    comando_ls = ""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = linha_do_comando(argumentos)
        if "find" in linha:
            return ResultadoComando(127, SEM_FIND, "")
        if "ls -R" in linha:
            type(self).comando_ls = linha
            # Sem a barra final, o toolbox devolve apenas o nome do link.
            if "/sdcard/" not in linha:
                return ResultadoComando(0, "/sdcard", "")
            return ResultadoComando(
                0,
                "/sdcard/:\nDCIM\n\n/sdcard/DCIM:\nfoto.jpg\n",
                "",
            )
        return ResultadoComando(0, "", "")


inventario = montar(FilesystemDumpExtractor, ADBLinkSimbolico()).inventariar_origem("/sdcard")
checar(
    "o caminho vai com barra final, entre aspas",
    "'/sdcard/'" in ADBLinkSimbolico.comando_ls,
)
checar("com a barra, o link e recursado", inventario.disponivel is True)
checar("e os arquivos aparecem", inventario.arquivos == ["DCIM/foto.jpg"])


class ADBSemRecursao(ADBSemFind):
    """Aparelho onde o `ls -R` nao lista nada, mesmo com barra."""

    saida_ls = "/sdcard"


inventario = montar(FilesystemDumpExtractor, ADBSemRecursao()).inventariar_origem("/sdcard")
checar("saida sem cabecalho NAO vira origem vazia", inventario.disponivel is False)
checar("o motivo diz que nao houve recursao", "não recursou" in inventario.motivo_indisponivel)

# Pasta genuinamente vazia continua sendo inventario valido de zero arquivo.
class ADBPastaVazia(ADBSemFind):
    saida_ls = "/sdcard/Music:\n"


inventario = montar(FilesystemDumpExtractor, ADBPastaVazia()).inventariar_origem("/sdcard/Music")
checar("pasta vazia com cabecalho continua valida", inventario.disponivel is True)
checar("e reporta zero arquivo", inventario.arquivos == [])

# ---------------------------------------------------------------------------
print("\n[7] Inventario menor que o adquirido e contradicao, nao 'origem vazia'")
# ---------------------------------------------------------------------------
from core.android.extractors.base import ResultadoAquisicao

copia_com_273 = ResultadoPull(
    "/sdcard", Path("."), 0, "", "", 273, 21584910, SituacaoPull.OK
)
contraditoria = ResultadoAquisicao(
    copia=copia_com_273, arquivos_na_origem=0, metodo_inventario="ls -R"
)

checar("a contradicao e detectada", contraditoria.inconsistente is True)
checar("completude NAO e afirmada", contraditoria.completa is None)

descricao = FilesystemDumpExtractor._descrever_completude(contraditoria)
checar("a descricao NAO diz 'ORIGEM VAZIA'", "ORIGEM VAZIA" not in descricao)
checar("a descricao expoe os dois numeros", "273" in descricao and "0" in descricao)
checar("a descricao diz que o inventario nao e confiavel", "não é confiável" in descricao)

consolidado = AndroidExtractor.consolidar_reconciliacao([contraditoria])
checar(
    "consolidacao nao trata a contradicao como verificavel",
    consolidado["completude_verificavel"] is False,
)
checar(
    "o caminho contraditorio e listado",
    consolidado["inventarios_inconsistentes"] == ["/sdcard"],
)

coerente = ResultadoAquisicao(
    copia=ResultadoPull("/sdcard/DCIM", Path("."), 0, "", "", 6, 5017790, SituacaoPull.OK),
    arquivos_na_origem=6,
    metodo_inventario="ls -R",
)
checar("aquisicao coerente nao e marcada como contraditoria", coerente.inconsistente is False)
checar("e continua sendo declarada completa", coerente.completa is True)

# ---------------------------------------------------------------------------
print("\n[8] Caminho com espaco precisa ir entre aspas para o shell do aparelho")
# ---------------------------------------------------------------------------
# `adb shell` nao recebe lista de argumentos: junta tudo numa linha e entrega
# ao shell do dispositivo, que separa por espaco. Sem aspas, o caminho
# "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media" chegava
# como DOIS argumentos, e o `find` inventariava caminhos inexistentes --
# devolvendo ZERO arquivo para uma pasta cheia. Observado no aparelho real.
CAMINHO_COM_ESPACO = "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media"

protegido = AndroidExtractor.aspas_para_shell(CAMINHO_COM_ESPACO)
checar("o caminho e envolvido em aspas", protegido.startswith("'") and protegido.endswith("'"))
checar("o caminho permanece integro dentro das aspas", CAMINHO_COM_ESPACO in protegido)
checar(
    "apostrofo no nome nao quebra a protecao",
    AndroidExtractor.aspas_para_shell("/sdcard/Ba'nana") != "'/sdcard/Ba'nana'",
)


class ADBQueRegistraComando:
    """Captura a linha exata que seria entregue ao shell do aparelho."""

    comandos = []

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        type(self).comandos.append(" ".join(argumentos))
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(127, SEM_FIND, "")
        return ResultadoComando(0, "/sdcard/x:\n", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos, timeout).stdout


espiao = ADBQueRegistraComando()
montar(FilesystemDumpExtractor, espiao).inventariar_origem(CAMINHO_COM_ESPACO)

comando_find = next(c for c in espiao.comandos if "find" in c)
comando_ls = next(c for c in espiao.comandos if "ls -R" in c)

checar(
    "o find recebe o caminho entre aspas",
    f"'{CAMINHO_COM_ESPACO}'" in comando_find,
)
checar(
    "o ls -R tambem recebe o caminho entre aspas",
    f"'{CAMINHO_COM_ESPACO}/'" in comando_ls,
)
checar(
    "o caminho NAO viaja solto, sujeito a quebra por espaco",
    f"find {CAMINHO_COM_ESPACO} " not in comando_find,
)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
