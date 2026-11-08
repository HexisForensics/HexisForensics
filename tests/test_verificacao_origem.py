"""
Testes do nivel 2: fidelidade da copia, restricao do Android 11+,
sobreposicao entre modulos e conferencia do aparelho no encerramento.

O fio comum: a suite so pode afirmar o que verificou. Hashear apenas o
arquivo que chegou prova que ele nao mudou DESDE que chegou -- nao prova
que a transferencia foi fiel. Confrontar com o hash calculado dentro do
aparelho e o que fecha essa lacuna, e quando isso nao e possivel, a nao
verificacao precisa ficar declarada em vez de presumida.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoPull, SituacaoPull
from core.android.extractors.base import LIMITE_VERIFICACAO_ORIGEM, ResultadoAquisicao
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor
from services.extraction_service import detectar_sobreposicao, listar_extratores

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar(adb):
    extrator = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    extrator._log_callback = lambda m: None
    extrator._progress_callback = lambda p: None
    extrator._cancelado = False
    extrator.adb = adb
    return extrator


class ADBComHash:
    """Aparelho com sha256sum, devolvendo hashes programados."""

    def __init__(self, api="28", hashes=None, tem_sha256sum=True, root=False):
        self.api = api
        self.hashes = hashes or {}
        self.tem_sha256sum = tem_sha256sum
        self.root = root
        self.lotes = []

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = " ".join(argumentos)
        if "getprop" in linha:
            return ResultadoComando(0, self.api, "")
        if "whoami" in linha:
            return ResultadoComando(0, "root" if self.root else "shell", "")
        if "sha256sum" in linha:
            if not self.tem_sha256sum:
                return ResultadoComando(127, "/system/bin/sh: sha256sum: not found", "")
            alvos = [t for t in linha.split("'") if t.startswith("/")]
            self.lotes.append(len(alvos))
            saida = []
            for alvo in alvos:
                nome = alvo.rsplit("/", 1)[-1]
                if nome in self.hashes:
                    saida.append(f"{self.hashes[nome]}  {alvo}")
            return ResultadoComando(0, "\n".join(saida), "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos).stdout


# ---------------------------------------------------------------------------
print("\n[1] Restricao do Android 11+ e declarada, nao presumida")
# ---------------------------------------------------------------------------
antigo = montar(ADBComHash(api="28"))
moderno = montar(ADBComHash(api="30"))
recente = montar(ADBComHash(api="33"))

checar("API 28 nao dispara a ressalva", antigo.restricao_de_dados_de_app("/sdcard") == "")
checar("API 30 dispara a ressalva", moderno.restricao_de_dados_de_app("/sdcard") != "")
checar("API 33 tambem dispara", recente.restricao_de_dados_de_app("/sdcard") != "")

texto = recente.restricao_de_dados_de_app("/sdcard")
checar("a ressalva nomeia o caminho inacessivel", "/sdcard/Android/data" in texto)
checar("a ressalva informa a versao detectada", "33" in texto)
checar("a ressalva proibe a conclusao negativa", "nao autoriza concluir" in texto)

checar(
    "caminho que nao abrange os dados de app nao dispara ressalva",
    recente.restricao_de_dados_de_app("/sdcard/DCIM") == "",
)
checar(
    "o proprio caminho de dados de app dispara",
    recente.restricao_de_dados_de_app("/sdcard/Android/data") != "",
)

sem_versao = montar(ADBComHash(api="ilegivel"))
checar(
    "versao ilegivel nao inventa ressalva",
    sem_versao.restricao_de_dados_de_app("/sdcard") == "",
)

# Apareceu na primeira execucao contra o emulador com root, em 30/08/2026.
# A ressalva disparava so pelo nivel de API, sem perguntar se o shell era
# root -- e com adbd em root a copia FUNCIONOU, com fidelidade confirmada,
# enquanto o registro afirmava que os dados NAO tinham sido adquiridos.
#
# E o defeito de sempre virado do avesso: em vez de afirmar sucesso que
# nao houve, afirmava limitacao que nao havia. Custa caro do mesmo jeito --
# o examinador descarta como inexistente o que esta na pasta.
com_root = montar(ADBComHash(api="33", root=True))
checar(
    "com o shell em root, a ressalva nao dispara",
    com_root.restricao_de_dados_de_app("/sdcard") == "",
)
checar(
    "nem para o proprio caminho de dados de app",
    com_root.restricao_de_dados_de_app("/sdcard/Android/data") == "",
)
checar("e o extrator sabe dizer que esta em root", com_root.shell_e_root() is True)

sem_root = montar(ADBComHash(api="33", root=False))
checar("sem root, a ressalva continua disparando",
       sem_root.restricao_de_dados_de_app("/sdcard") != "")
checar("e o extrator sabe dizer que NAO esta em root",
       sem_root.shell_e_root() is False)

# ---------------------------------------------------------------------------
print("\n[2] Hash calculado DENTRO do aparelho")
# ---------------------------------------------------------------------------
HASH_A = "a" * 64
HASH_B = "b" * 64

adb = ADBComHash(hashes={"um.jpg": HASH_A, "dois.jpg": HASH_B})
hashes, motivo = montar(adb).hashear_na_origem("/sdcard/DCIM", ["um.jpg", "dois.jpg"])

checar("os hashes da origem sao lidos", hashes == {"um.jpg": HASH_A, "dois.jpg": HASH_B})
checar("sem motivo de indisponibilidade", motivo == "")

muitos = [f"arq_{i}.jpg" for i in range(95)]
adb_lote = ADBComHash(hashes={nome: HASH_A for nome in muitos})
montar(adb_lote).hashear_na_origem("/sdcard/DCIM", muitos)
checar("a consulta e feita em lotes, para nao estourar a linha de comando", len(adb_lote.lotes) == 3)
checar("nenhum lote excede o limite", all(n <= 40 for n in adb_lote.lotes))

sem_ferramenta = ADBComHash(tem_sha256sum=False)
hashes, motivo = montar(sem_ferramenta).hashear_na_origem("/sdcard/DCIM", ["um.jpg"])
checar("aparelho sem sha256sum devolve indisponivel", hashes is None)
checar("e o motivo diz qual comando falta", "sha256sum" in motivo)

vazio, motivo = montar(adb).hashear_na_origem("/sdcard/DCIM", [])
checar("lista vazia nao consulta o aparelho", vazio == {})

# ---------------------------------------------------------------------------
print("\n[3] Fidelidade: copia identica, divergente e nao verificavel")
# ---------------------------------------------------------------------------
def aquisicao_com(hashes_destino, bytes_copiados=1000):
    return ResultadoAquisicao(
        copia=ResultadoPull(
            "/sdcard/DCIM", Path("."), 0, "", "", len(hashes_destino),
            bytes_copiados, SituacaoPull.OK,
        ),
        hashes=dict(hashes_destino),
    )


identica = aquisicao_com({"DCIM/um.jpg": HASH_A, "DCIM/dois.jpg": HASH_B})
montar(ADBComHash(hashes={"um.jpg": HASH_A, "dois.jpg": HASH_B})).verificar_fidelidade(
    "/sdcard/DCIM", Path("."), identica
)
checar("copia identica e declarada integra", identica.integra is True)
checar("sem divergencias", identica.divergencias == [])
checar("a verificacao consta como realizada", identica.verificacao_na_origem.startswith("realizada"))

corrompida = aquisicao_com({"DCIM/um.jpg": HASH_A, "DCIM/dois.jpg": HASH_A})
montar(ADBComHash(hashes={"um.jpg": HASH_A, "dois.jpg": HASH_B})).verificar_fidelidade(
    "/sdcard/DCIM", Path("."), corrompida
)
checar("arquivo divergente e detectado", corrompida.divergencias == ["dois.jpg"])
checar("copia com divergencia NAO e integra", corrompida.integra is False)
checar("o arquivo intacto nao e acusado", "um.jpg" not in corrompida.divergencias)

sem_ferramenta_aq = aquisicao_com({"DCIM/um.jpg": HASH_A})
montar(ADBComHash(tem_sha256sum=False)).verificar_fidelidade(
    "/sdcard/DCIM", Path("."), sem_ferramenta_aq
)
checar("sem sha256sum, a integridade NAO e afirmada", sem_ferramenta_aq.integra is None)
checar(
    "e a nao verificacao fica declarada",
    sem_ferramenta_aq.verificacao_na_origem.startswith("NAO realizada"),
)

volumosa = aquisicao_com({"DCIM/um.jpg": HASH_A}, bytes_copiados=LIMITE_VERIFICACAO_ORIGEM + 1)
montar(ADBComHash(hashes={"um.jpg": HASH_A})).verificar_fidelidade(
    "/sdcard/DCIM", Path("."), volumosa
)
checar("acima do limite, a verificacao e dispensada", volumosa.integra is None)
checar("e o motivo cita o limite", "limite" in volumosa.verificacao_na_origem)

vazia = aquisicao_com({})
montar(ADBComHash()).verificar_fidelidade("/sdcard/DCIM", Path("."), vazia)
checar("sem arquivo adquirido, a verificacao e dispensada", "dispensada" in vazia.verificacao_na_origem)

# ---------------------------------------------------------------------------
print("\n[4] Sobreposicao entre modulos e declarada")
# ---------------------------------------------------------------------------
classes = {c.id: c for c in listar_extratores("Android")}

com_sobreposicao = [classes["android_backup_logico"](), classes["android_filesystem_dump"]()]
avisos = detectar_sobreposicao(com_sobreposicao)
checar("a sobreposicao e detectada", len(avisos) == 1)
checar("o aviso nomeia os dois modulos", "Backup" in avisos[0] and "Filesystem" in avisos[0] or "Sistema de Arquivos" in avisos[0])
checar("o aviso nomeia o caminho duplicado", "/sdcard/DCIM" in avisos[0])
checar("o aviso explica a consequencia", "duas vezes" in avisos[0])

sem_sobreposicao = [classes["android_device_info"](), classes["android_identificacao"]()]
checar("modulos sem caminho comum nao geram aviso", detectar_sobreposicao(sem_sobreposicao) == [])

sozinho = [classes["android_filesystem_dump"]()]
checar("um modulo sozinho nao gera aviso", detectar_sobreposicao(sozinho) == [])

# ---------------------------------------------------------------------------
print("\n[5] Conferencia do aparelho no encerramento")
# ---------------------------------------------------------------------------
from services.device_service import DeviceService


class AndroidFalso:
    def __init__(self, seriais, autorizado=True):
        self.seriais = seriais
        self.autorizado = autorizado

    def verificar_conexao(self):
        class Status:
            pass

        status = Status()
        status.seriais_detectados = self.seriais
        status.autorizado = self.autorizado
        return status


servico = DeviceService.__new__(DeviceService)

servico._android = AndroidFalso(["51183d8f"])
confirmado, mensagem = servico.conferir_aparelho_do_caso("51183d8f")
checar("mesmo aparelho ao final e confirmado", confirmado is True)
checar("a confirmacao nomeia o aparelho", "51183d8f" in mensagem)

servico._android = AndroidFalso([])
confirmado, mensagem = servico.conferir_aparelho_do_caso("51183d8f")
checar("aparelho ausente ao final NAO e confirmado", confirmado is False)
checar("e a mensagem diz que nao foi possivel confirmar", "NÃO foi possível confirmar" in mensagem)

servico._android = AndroidFalso(["OUTRO_APARELHO"])
confirmado, mensagem = servico.conferir_aparelho_do_caso("51183d8f")
checar("aparelho trocado e apontado como divergencia", confirmado is False)
checar("a mensagem nomeia os dois seriais", "51183d8f" in mensagem and "OUTRO_APARELHO" in mensagem)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
