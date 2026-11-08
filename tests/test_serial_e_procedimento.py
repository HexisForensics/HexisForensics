"""
Testes da vinculacao ao aparelho do caso e do registro do procedimento.

Cobre tres exigencias da ISO/IEC 27037 que antes nao tinham nenhuma
sustentacao no codigo:

  - todo comando ADB fala com o aparelho do caso, e com nenhum outro;
  - mais de um aparelho conectado bloqueia a extracao em vez de o sistema
    escolher um por conta propria;
  - ambiente, relogio, decisoes e alteracoes ficam registrados no caso.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ADBClient
from core.android.device import AndroidDevice, RelogioDispositivo
from core.procedimento import NOME_ARQUIVO, RegistroProcedimento

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


class ADBFalso:
    """Substitui o binario do ADB, devolvendo saidas pre-programadas."""

    def __init__(self, dispositivos, epoch="1700000000", data="Sex Ago 22 12:00:00 BRT 2026"):
        self._dispositivos = dispositivos
        self._epoch = epoch
        self._data = data

    def verificar_binario(self):
        return True, ""

    def listar_dispositivos(self):
        return self._dispositivos

    def executar(self, argumentos, timeout=None):
        if "+%s" in argumentos:
            return self._epoch
        if "date" in argumentos:
            return self._data
        return ""

    def obter_propriedade(self, propriedade):
        return "America/Sao_Paulo"


# ---------------------------------------------------------------------------
print("\n[1] Vinculacao dos comandos ao serial do aparelho do caso")
# ---------------------------------------------------------------------------
cliente = ADBClient(caminho_binario=Path("adb"))

checar("sem serial definido, nenhum -s e acrescentado", "-s" not in cliente._montar_comando(["shell", "ls"]))

cliente.definir_serial("R58M12ABCDE")
comando = cliente._montar_comando(["shell", "ls"])
checar("com serial definido, o comando leva -s", "-s" in comando)
checar("o serial vinculado e o do caso", "R58M12ABCDE" in comando)
checar(
    "o -s vem antes do subcomando, como o ADB exige",
    comando.index("-s") < comando.index("shell"),
)
checar(
    "comandos globais (adb devices) nao levam -s",
    "-s" not in cliente._montar_comando(["devices"], vincular_serial=False),
)

# ---------------------------------------------------------------------------
print("\n[2] Mais de um aparelho conectado bloqueia a extracao")
# ---------------------------------------------------------------------------
um_aparelho = AndroidDevice(ADBFalso([("R58M12ABCDE", "device")]))
status = um_aparelho.verificar_conexao()
checar("um aparelho autorizado libera a extracao", status.autorizado is True)
checar("o serial detectado e devolvido", status.serial == "R58M12ABCDE")
checar("um aparelho nao dispara alerta de multiplos", status.multiplos_dispositivos is False)

dois_aparelhos = AndroidDevice(
    ADBFalso([("R58M12ABCDE", "device"), ("R58M99ZZZZZ", "device")])
)
status = dois_aparelhos.verificar_conexao()
checar("dois aparelhos NAO autorizam a extracao", status.autorizado is False)
checar("a condicao de multiplos aparelhos e sinalizada", status.multiplos_dispositivos is True)
checar("nenhum serial e escolhido automaticamente", status.serial is None)
checar("os dois seriais aparecem na mensagem ao examinador", "R58M99ZZZZZ" in status.mensagem)

nao_autorizado = AndroidDevice(ADBFalso([("R58M12ABCDE", "unauthorized")]))
checar(
    "aparelho nao autorizado continua bloqueando",
    nao_autorizado.verificar_conexao().autorizado is False,
)

# ---------------------------------------------------------------------------
print("\n[3] Afericao do relogio do aparelho")
# ---------------------------------------------------------------------------
relogio = AndroidDevice(ADBFalso([("A", "device")], epoch="1700000000")).obter_relogio()
checar("o epoch do aparelho e lido", relogio.epoch_dispositivo == 1700000000)
checar("o desvio em relacao a estacao e calculado", relogio.desvio_segundos is not None)
checar("o fuso do aparelho e registrado", "Sao_Paulo" in relogio.fuso_dispositivo)

ilegivel = AndroidDevice(ADBFalso([("A", "device")], epoch="nao-e-numero")).obter_relogio()
checar("relogio ilegivel nao inventa desvio", ilegivel.desvio_segundos is None)
checar("relogio ilegivel e dito explicitamente", "NAO FOI POSSIVEL" in ilegivel.resumo())

adiantado = RelogioDispositivo(1_000_300, 1_000_000, "x", "y")
atrasado = RelogioDispositivo(999_700, 1_000_000, "x", "y")
checar("aparelho adiantado e descrito como adiantado", "5 min adiantado (+300 s)" in adiantado.resumo())
checar("aparelho atrasado e descrito como atrasado", "5 min atrasado (-300 s)" in atrasado.resumo())
checar("sem desvio, o resumo diz 'nenhum'", "nenhum" in RelogioDispositivo(10, 10, "x", "y").resumo())

# ---------------------------------------------------------------------------
print("\n[4] Registro do procedimento no caso")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    registro = RegistroProcedimento(pasta)
    registro.abrir("CASO_007", "Android", "R58M12ABCDE")
    registro.registrar_ambiente(versao_adb="Android Debug Bridge version 1.0.41")
    registro.registrar_relogio("Desvio: 12s adiantado")
    registro.registrar_decisao("Extracao fisica nao realizada.", "Aparelho sem root.")
    registro.registrar_alteracao("Depuracao USB ativada.", "Exigencia do protocolo ADB.")
    registro.encerrar("7 modulos executados, 1 com ressalva.")

    conteudo = (pasta / NOME_ARQUIVO).read_text(encoding="utf-8")
    checar("o arquivo do registro e criado na pasta do caso", (pasta / NOME_ARQUIVO).exists())
    checar("identificacao do caso consta do cabecalho", "CASO_007" in conteudo)
    checar("versao da ferramenta e carimbada", "HexisForensics" in conteudo)
    checar("versao do ADB e carimbada", "1.0.41" in conteudo)
    checar("afericao de relogio consta", "AFERIÇÃO DE RELÓGIO" in conteudo)
    checar("decisao metodologica consta", "DECISÃO METODOLÓGICA" in conteudo)
    checar("alteracao no dispositivo consta", "ALTERAÇÃO NO DISPOSITIVO" in conteudo)
    checar("justificativa da alteracao consta", "protocolo ADB" in conteudo)
    checar("encerramento consta", "ENCERRAMENTO" in conteudo)

    linhas_datadas = [l for l in conteudo.splitlines() if l.startswith("[2")]
    checar("toda entrada tem carimbo de tempo", len(linhas_datadas) >= 5)
    checar("o carimbo traz o fuso explicito", any("+" in l or "-" in l[10:] for l in linhas_datadas))

    tamanho_antes = len(conteudo)
    registro.registrar_observacao("Entrada posterior.")
    conteudo_depois = (pasta / NOME_ARQUIVO).read_text(encoding="utf-8")
    checar("o registro e append-only: nada anterior e reescrito", conteudo_depois.startswith(conteudo))
    checar("a entrada posterior foi acrescentada", len(conteudo_depois) > tamanho_antes)

    # Falha de escrita nao pode derrubar uma aquisicao em andamento.
    inacessivel = RegistroProcedimento(Path(td) / "arquivo_comum" / "sub")
    (Path(td) / "arquivo_comum").write_text("nao sou pasta", encoding="utf-8")
    checar("falha ao gravar o diario nao lanca excecao", inacessivel.registrar_observacao("x") is False)


# ---------------------------------------------------------------------------
print("\n[5] Extratores registram suas decisoes metodologicas no caso")
# ---------------------------------------------------------------------------
from core.android.adb_client import ResultadoComando, ResultadoPull, SituacaoPull
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor
from core.android.extractors.identificacao import IdentificacaoExtractor


class ADBQueNegaTudo:
    """Aparelho sem root: recusa /data/data e nao expoe o IMEI."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "find" in linha_do_comando(argumentos):
            return ResultadoComando(1, "", "find: Permission denied")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        if "whoami" in argumentos:
            return "shell"
        return self.executar_detalhado(argumentos, timeout).stdout

    def obter_propriedade(self, propriedade):
        return ""

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 1, "", "Permission denied", 0, 0,
            SituacaoPull.ACESSO_NEGADO,
        )


def montar_extrator(classe):
    extrator = classe.__new__(classe)
    extrator._log_callback = lambda m: None
    extrator._progress_callback = lambda p: None
    extrator._cancelado = False
    extrator.adb = ADBQueNegaTudo()
    return extrator


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    parcial_sdcard = montar_extrator(FilesystemDumpExtractor)

    def pull_seletivo(caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        # /sdcard vem; /data/data e recusado -- o cenario real sem root.
        if caminho_remoto == "/sdcard":
            destino = Path(caminho_local)
            destino.mkdir(parents=True, exist_ok=True)
            (destino / "arquivo.txt").write_text("dado", encoding="utf-8")
            return ResultadoPull(caminho_remoto, destino, 0, "", "", 1, 4, SituacaoPull.OK)
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 1, "", "Permission denied", 0, 0,
            SituacaoPull.ACESSO_NEGADO,
        )

    parcial_sdcard.adb.pull = pull_seletivo
    resultado = parcial_sdcard.executar(pasta_caso)

    checar("aquisicao parcial continua sendo sucesso com ressalva", resultado.sucesso is True)
    registro = (pasta_caso / NOME_ARQUIVO).read_text(encoding="utf-8")
    checar("a recusa de /data/data vira DECISAO registrada", "DECISÃO METODOLÓGICA" in registro)
    checar("a decisao nomeia o modulo que a tomou", "Dump do Sistema de Arquivos" in registro)
    checar("a decisao nomeia o caminho nao adquirido", "/data/data" in registro)
    checar("a decisao explica que exigiria root", "root" in registro)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    montar_extrator(IdentificacaoExtractor).executar(pasta_caso)

    registro = (pasta_caso / NOME_ARQUIVO).read_text(encoding="utf-8")
    checar("IMEI nao obtido tambem vira decisao fundamentada", "IMEI não obtido" in registro)
    checar("a decisao informa quantas vias foram percorridas", "vias distintas" in registro)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
