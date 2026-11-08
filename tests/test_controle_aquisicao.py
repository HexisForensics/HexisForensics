"""
Testes do controle da aquisicao: espaco na estacao, interrupcao e progresso.

Sao os quatro pontos que impediam uso em campo: nao dava para cancelar uma
copia em andamento, nao havia teto para um ADB travado, nao se conferia
espaco em disco (produzindo aquisicao truncada sem dizer que a causa era da
estacao), e a barra de progresso nao refletia a transferencia.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoPull, SituacaoPull
from core.android.extractors.base import AndroidExtractor
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor
from core.armazenamento import espaco_livre, formatar_bytes, verificar_espaco

falhas = []


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


# ---------------------------------------------------------------------------
print("\n[1] Verificacao de espaco na estacao forense")
# ---------------------------------------------------------------------------
checar("bytes sao formatados de forma legivel", formatar_bytes(5 * 1024 ** 3).endswith("GB"))
checar("valor pequeno sai em bytes", formatar_bytes(512) == "512 B")

with tempfile.TemporaryDirectory() as td:
    destino = Path(td)
    checar("o espaco livre e apurado", isinstance(espaco_livre(destino), int))
    checar(
        "pasta ainda inexistente nao impede a apuracao",
        isinstance(espaco_livre(destino / "caso" / "aquisicao"), int),
    )

    ok, _ = verificar_espaco(destino, 1024)
    checar("cabendo, a aquisicao e liberada", ok is True)

    ok, motivo = verificar_espaco(destino, 10 ** 15)
    checar("nao cabendo, a aquisicao e barrada", ok is False)
    checar("o motivo informa o tamanho da origem", "909" in motivo or "TB" in motivo)
    checar("o motivo informa o espaco livre", "livres" in motivo)
    checar("o motivo diz que NADA foi iniciado", "NÃO foi iniciada" in motivo)
    checar("o motivo orienta a solucao", "Libere espaço" in motivo)

    ok, _ = verificar_espaco(destino, None)
    checar("sem estimativa, a aquisicao NAO e barrada", ok is True)


# ---------------------------------------------------------------------------
print("\n[2] Aquisicao nao comeca quando falta espaco")
# ---------------------------------------------------------------------------
class ADBOrigemGigante:
    """Aparelho cujo caminho ocupa mais do que cabe na estacao."""

    pull_chamado = False

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = " ".join(argumentos)
        if "du -sk" in linha:
            # `du -sk` responde em KB: 10^12 KB = ~1 PB
            return ResultadoComando(0, "1000000000000\t/sdcard", "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos).stdout

    def pull(self, *args, **kwargs):
        type(self).pull_chamado = True
        raise AssertionError("a copia nao deveria ter sido iniciada")


with tempfile.TemporaryDirectory() as td:
    extrator = montar(FilesystemDumpExtractor, ADBOrigemGigante())
    aquisicao = extrator.adquirir_caminho("/sdcard", Path(td) / "destino")

    checar("a copia NAO e iniciada", ADBOrigemGigante.pull_chamado is False)
    checar("o desfecho e erro", aquisicao.copia.situacao is SituacaoPull.ERRO)
    checar("o motivo fica no stderr do resultado", "Espaço insuficiente" in aquisicao.copia.stderr)
    checar(
        "a falta de espaco e atribuida a ESTACAO, nao ao aparelho",
        "estação forense" in aquisicao.copia.stderr,
    )
    checar("completude nao e afirmada", aquisicao.completa is None)


class ADBOrigemPequena(ADBOrigemGigante):
    pull_chamado = False

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = " ".join(argumentos)
        if "du -sk" in linha:
            return ResultadoComando(0, "8\t/sdcard/DCIM", "")
        if "find" in linha:
            return ResultadoComando(0, "/sdcard/DCIM/foto.jpg", "")
        return ResultadoComando(0, "", "")

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        type(self).pull_chamado = True
        destino = Path(caminho_local) / "DCIM"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "foto.jpg").write_text("conteudo", encoding="utf-8")
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 0, "", "", 1, 8, SituacaoPull.OK
        )


with tempfile.TemporaryDirectory() as td:
    extrator = montar(FilesystemDumpExtractor, ADBOrigemPequena())
    aquisicao = extrator.adquirir_caminho("/sdcard/DCIM", Path(td) / "destino")

    checar("cabendo, a copia e iniciada normalmente", ADBOrigemPequena.pull_chamado is True)
    checar("e a aquisicao conclui", aquisicao.copia.sucesso is True)
    checar("a completude e verificada", aquisicao.completa is True)


# ---------------------------------------------------------------------------
print("\n[3] Copia interrompida e incompleta por construcao")
# ---------------------------------------------------------------------------
cancelada = ResultadoPull(
    "/sdcard", Path("."), -9, "", "", 120, 5000, SituacaoPull.CANCELADO
)
expirada = ResultadoPull(
    "/sdcard", Path("."), -9, "", "", 40, 900, SituacaoPull.EXPIRADO
)
concluida = ResultadoPull("/sdcard", Path("."), 0, "", "", 300, 9000, SituacaoPull.OK)

checar("copia cancelada e interrompida", cancelada.interrompida is True)
checar("copia expirada e interrompida", expirada.interrompida is True)
checar("copia concluida NAO e interrompida", concluida.interrompida is False)
checar("interrompida nunca e sucesso", cancelada.sucesso is False and expirada.sucesso is False)
checar("o resumo da cancelada informa quantos arquivos vieram", "120" in cancelada.resumo())

consolidado = AndroidExtractor.consolidar_copias([cancelada, concluida])
checar(
    "a consolidacao lista o caminho interrompido",
    consolidado["caminhos_interrompidos"] == ["/sdcard"],
)
checar(
    "o que veio antes da interrupcao continua contabilizado",
    consolidado["arquivos_copiados"] == 420,
)


# ---------------------------------------------------------------------------
print("\n[4] Progresso e mapeado na faixa do caminho")
# ---------------------------------------------------------------------------
class ADBQueReportaProgresso(ADBOrigemPequena):
    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        ao_progredir = kwargs.get("ao_progredir")
        if ao_progredir:
            for percentual in (0, 50, 100):
                ao_progredir(percentual)
        Path(caminho_local).mkdir(parents=True, exist_ok=True)
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 0, "", "", 0, 0, SituacaoPull.VAZIO
        )


with tempfile.TemporaryDirectory() as td:
    registrados = []
    extrator = montar(FilesystemDumpExtractor, ADBQueReportaProgresso())
    extrator._progress_callback = registrados.append
    extrator.copiar_caminho("/sdcard/DCIM", Path(td) / "d", faixa_progresso=(20, 40))

    checar("o progresso comeca no inicio da faixa", registrados[0] == 20)
    checar("o meio da copia cai no meio da faixa", registrados[1] == 30)
    checar("o fim da copia atinge o fim da faixa", registrados[-1] == 40)
    checar("o progresso nunca sai da faixa", all(20 <= v <= 40 for v in registrados))

with tempfile.TemporaryDirectory() as td:
    registrados = []
    extrator = montar(FilesystemDumpExtractor, ADBQueReportaProgresso())
    extrator._progress_callback = registrados.append
    extrator.copiar_caminho("/sdcard/DCIM", Path(td) / "d")
    checar("sem faixa declarada, nenhum progresso e forjado", registrados == [])


# ---------------------------------------------------------------------------
print("\n[5] Cancelamento chega ao processo de copia")
# ---------------------------------------------------------------------------
class ADBQueObservaCancelamento:
    recebeu = {}

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return ""

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        type(self).recebeu = dict(kwargs)
        Path(caminho_local).mkdir(parents=True, exist_ok=True)
        return ResultadoPull(
            caminho_remoto, Path(caminho_local), 0, "", "", 0, 0, SituacaoPull.VAZIO
        )


with tempfile.TemporaryDirectory() as td:
    extrator = montar(FilesystemDumpExtractor, ADBQueObservaCancelamento())
    extrator.copiar_caminho("/sdcard", Path(td) / "d")

    consulta = ADBQueObservaCancelamento.recebeu.get("cancelado")
    checar("a copia recebe um verificador de cancelamento", callable(consulta))
    checar("antes do pedido, o verificador responde False", consulta() is False)

    extrator.cancelar()
    checar("apos o pedido, o verificador responde True", consulta() is True)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
