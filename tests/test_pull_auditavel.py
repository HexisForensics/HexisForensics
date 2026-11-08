"""
Testes da auditabilidade do `adb pull` e dos extratores que dependem dele.

O defeito que estes testes travam: antes, `ADBClient.pull` descartava
stdout/stderr e devolvia um booleano que nenhum extrator conferia. Um
`/data/data` recusado pelo Android (comportamento normal sem root)
terminava como "sucesso" na interface, induzindo a conclusao negativa
falsa de que os bancos dos aplicativos foram examinados e estavam vazios.
"""
import sys
import tempfile
import time
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android import adb_client as modulo_adb
from core.android.adb_client import ADBClient, ResultadoComando, ResultadoPull, SituacaoPull
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor
from core.android.extractors.logical_backup import PASTAS_MIDIA, BackupLogicoExtractor

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


def montar_pull(caminho, situacao, arquivos=0, bytes_copiados=0, stderr=""):
    return ResultadoPull(
        caminho_remoto=caminho,
        caminho_local=Path("."),
        codigo_saida=0 if situacao is not SituacaoPull.ERRO else 1,
        stdout="",
        stderr=stderr,
        arquivos_copiados=arquivos,
        bytes_copiados=bytes_copiados,
        situacao=situacao,
    )


class FakeADB:
    """ADB falso: devolve um desfecho de copia pre-programado por caminho."""

    def __init__(self, por_caminho, usuario_shell="shell", saida_texto="conteudo", inventario=None):
        self._por_caminho = por_caminho
        self._usuario_shell = usuario_shell
        self._saida_texto = saida_texto
        # caminho remoto -> lista de arquivos existentes no aparelho
        self._inventario = inventario or {}

    def executar(self, argumentos, timeout=None):
        if "whoami" in argumentos:
            return self._usuario_shell
        if "find" in linha_do_comando(argumentos):
            raiz = alvo_do_comando(argumentos)
            return "\n".join(f"{raiz}/{nome}" for nome in self._inventario.get(raiz, []))
        return self._saida_texto

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(0, self.executar(argumentos, timeout), "")

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        return self._por_caminho[caminho_remoto]


class ADBQueGrava(FakeADB):
    """
    ADB falso que **materializa** no destino os arquivos que diz ter copiado.

    Necessario para exercitar a reconciliacao: ela confronta o inventario da
    origem com o que existe em disco no destino, entao um falso que so
    devolve numeros nao serviria.
    """

    def __init__(self, inventario, copiados_por_caminho):
        super().__init__({}, inventario=inventario)
        self._copiados = copiados_por_caminho

    def stream_binario(self, argumentos, ao_receber_bloco, tamanho_bloco=0, cancelado=None):
        # A leitura individual tambem falha: os cenarios daqui medem o que
        # o relatorio diz quando o arquivo NAO vem por via nenhuma. A
        # recuperacao em si e exercitada em test_resgate_um_a_um.py.
        from core.android.adb_client import ResultadoStream

        return ResultadoStream(1, "", 0)

    def pull(self, caminho_remoto, caminho_local, preservar_timestamps=True, **kwargs):
        base = caminho_remoto.rstrip("/").rsplit("/", 1)[-1]
        destino = Path(caminho_local) / base
        destino.mkdir(parents=True, exist_ok=True)
        copiados = self._copiados.get(caminho_remoto, [])
        for nome in copiados:
            alvo = destino / nome
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(f"conteudo de {nome}", encoding="utf-8")
        arquivos = [c for c in Path(caminho_local).rglob("*") if c.is_file()]
        return ResultadoPull(
            caminho_remoto=caminho_remoto,
            caminho_local=Path(caminho_local),
            codigo_saida=0,
            stdout="",
            stderr="",
            arquivos_copiados=len(arquivos),
            bytes_copiados=sum(a.stat().st_size for a in arquivos),
            situacao=SituacaoPull.OK if arquivos else SituacaoPull.VAZIO,
        )


def montar(classe, por_caminho, **kwargs):
    extrator = classe.__new__(classe)
    extrator._log_callback = lambda mensagem: None
    extrator._progress_callback = lambda percentual: None
    extrator._cancelado = False
    extrator.adb = FakeADB(por_caminho, **kwargs)
    return extrator


# ---------------------------------------------------------------------------
print("\n[1] Classificacao do desfecho de uma copia")
# ---------------------------------------------------------------------------
classificar = ADBClient._classificar_pull

checar("copia com arquivos e OK", classificar(0, "", 12) is SituacaoPull.OK)
checar("codigo 0 sem arquivo nenhum NAO e OK", classificar(0, "", 0) is SituacaoPull.VAZIO)
checar(
    "permission denied vira ACESSO_NEGADO",
    classificar(1, "adb: error: failed to stat remote object: Permission denied", 0)
    is SituacaoPull.ACESSO_NEGADO,
)
checar(
    "acesso negado prevalece mesmo com arquivos parciais",
    classificar(1, "Permission denied", 5) is SituacaoPull.ACESSO_NEGADO,
)
checar(
    "caminho ausente vira INEXISTENTE",
    classificar(1, "adb: error: failed to stat: No such file or directory", 0)
    is SituacaoPull.INEXISTENTE,
)
checar("outra falha do ADB vira ERRO", classificar(1, "device offline", 0) is SituacaoPull.ERRO)

# ---------------------------------------------------------------------------
print("\n[2] O pull e controlavel: cancelamento, teto de inatividade, progresso")
# ---------------------------------------------------------------------------
# Em vez de simular o subprocesso, roda-se um processo REAL (o proprio
# Python) no lugar do ADB. Assim o cancelamento, o teto de inatividade e a
# drenagem concorrente de stdout/stderr sao exercitados de verdade -- e nao
# apenas a logica em volta deles.


class ADBSimulado(ADBClient):
    """Substitui o binario do ADB por um processo Python controlado."""

    def __init__(self, script):
        super().__init__(caminho_binario=Path(sys.executable))
        self.script = script
        self.argumentos_vistos = None

    def _montar_comando(self, argumentos, vincular_serial=True):
        self.argumentos_vistos = list(argumentos)
        return [sys.executable, "-c", self.script]


SCRIPT_COM_PROGRESSO = (
    "import sys\n"
    "for p in (10, 55, 100):\n"
    "    sys.stdout.write(f'[ {p}%] /sdcard/DCIM/foto.jpg\\n')\n"
    "    sys.stdout.flush()\n"
)

SCRIPT_TRAVADO = "import time\ntime.sleep(30)\n"

SCRIPT_INTERMINAVEL = (
    "import sys, time\n"
    "while True:\n"
    "    sys.stdout.write('[ 5%] copiando\\n')\n"
    "    sys.stdout.flush()\n"
    "    time.sleep(0.05)\n"
)

with tempfile.TemporaryDirectory() as td:
    percentuais = []
    cliente = ADBSimulado(SCRIPT_COM_PROGRESSO)
    resultado = cliente.pull(
        "/sdcard/DCIM", Path(td) / "saida", ao_progredir=percentuais.append
    )

    checar("flag -a e usada (preserva data de modificacao original)", "-a" in cliente.argumentos_vistos)
    checar("o caminho de origem vai no comando", "/sdcard/DCIM" in cliente.argumentos_vistos)
    # O leitor entrega blocos, nao linhas: varias atualizacoes podem chegar
    # juntas e so a mais recente e repassada. O contrato e o progresso ser
    # crescente e terminar em 100, nao reproduzir cada linha do ADB.
    checar("o progresso do ADB e repassado ao chamador", len(percentuais) >= 1)
    checar("o progresso nao retrocede", percentuais == sorted(percentuais))
    checar("o progresso termina em 100%", percentuais[-1] == 100)
    checar("a saida do processo e capturada", "100%" in resultado.stdout)
    checar("pasta vazia com codigo 0 nao e sucesso", resultado.sucesso is False)
    checar("desfecho de pasta vazia e VAZIO", resultado.situacao is SituacaoPull.VAZIO)

with tempfile.TemporaryDirectory() as td:
    inicio_espera = time.monotonic()
    resultado = ADBSimulado(SCRIPT_TRAVADO).pull(
        "/sdcard", Path(td) / "saida", segundos_sem_sinal=1
    )
    duracao = time.monotonic() - inicio_espera

    checar("processo sem sinal algum e interrompido", resultado.situacao is SituacaoPull.EXPIRADO)
    checar("a interrupcao ocorre perto do teto, nao apos os 30s", duracao < 10)
    checar("copia expirada conta como interrompida", resultado.interrompida is True)
    checar("copia expirada NAO e sucesso", resultado.sucesso is False)
    checar("o resumo explica que o ADB parou de responder", "parou de responder" in resultado.resumo())

with tempfile.TemporaryDirectory() as td:
    sinais = {"n": 0}

    def contar(_percentual):
        sinais["n"] += 1

    inicio_espera = time.monotonic()
    resultado = ADBSimulado(SCRIPT_INTERMINAVEL).pull(
        "/sdcard",
        Path(td) / "saida",
        cancelado=lambda: sinais["n"] > 0,
        ao_progredir=contar,
    )
    duracao = time.monotonic() - inicio_espera

    checar("o cancelamento interrompe a copia em andamento", resultado.situacao is SituacaoPull.CANCELADO)
    checar("o processo e encerrado em segundos, nao ao fim da copia", duracao < 10)
    checar("copia cancelada conta como interrompida", resultado.interrompida is True)
    checar("copia cancelada NAO e sucesso", resultado.sucesso is False)
    checar("o resumo diz que foi cancelada pelo examinador", "CANCELADA" in resultado.resumo())

with tempfile.TemporaryDirectory() as td:
    inexistente = ADBClient(caminho_binario=Path(td) / "adb_que_nao_existe")
    resultado = inexistente.pull("/sdcard/DCIM", Path(td) / "saida")
    checar("binario ausente vira ERRO com motivo registrado", resultado.situacao is SituacaoPull.ERRO)
    checar("motivo do erro fica no stderr do resultado", "ADB" in resultado.stderr)

# ---------------------------------------------------------------------------
print("\n[3] Dump de filesystem: nada copiado NAO pode ser sucesso")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)

    negado_tudo = montar(
        FilesystemDumpExtractor,
        {
            "/data/data": montar_pull(
                "/data/data", SituacaoPull.ACESSO_NEGADO, stderr="Permission denied"
            ),
            "/sdcard": montar_pull("/sdcard", SituacaoPull.ACESSO_NEGADO, stderr="Permission denied"),
        },
    )
    r = negado_tudo.executar(pasta)
    checar("tudo negado e reportado como FALHA", r.sucesso is False)
    checar("mensagem explica que exige root", "root" in r.mensagem.lower())
    checar("detalhes marcam ressalva de acesso negado", r.detalhes.get("acesso_negado") is True)

    vazio_tudo = montar(
        FilesystemDumpExtractor,
        {
            "/data/data": montar_pull("/data/data", SituacaoPull.INEXISTENTE),
            "/sdcard": montar_pull("/sdcard", SituacaoPull.VAZIO),
        },
    )
    r = vazio_tudo.executar(pasta)
    checar("zero arquivo copiado e FALHA mesmo sem erro do ADB", r.sucesso is False)

    parcial = montar(
        FilesystemDumpExtractor,
        {
            "/data/data": montar_pull(
                "/data/data", SituacaoPull.ACESSO_NEGADO, stderr="Permission denied"
            ),
            "/sdcard": montar_pull("/sdcard", SituacaoPull.OK, arquivos=430, bytes_copiados=90_000),
        },
    )
    r = parcial.executar(pasta)
    checar("sdcard OK com /data/data negado e sucesso PARCIAL", r.sucesso is True)
    checar("parcial sinaliza acesso negado", r.detalhes.get("acesso_negado") is True)
    checar("parcial nomeia o caminho recusado", "/data/data" in r.mensagem)
    checar("parcial informa a contagem adquirida", "430" in r.mensagem)
    checar("caminhos negados ficam listados nos detalhes", r.detalhes["caminhos_negados"] == ["/data/data"])

# ---------------------------------------------------------------------------
print("\n[4] Backup logico: metadados sem midia e ressalva, nao sucesso limpo")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    # Os caminhos saem do proprio modulo. Repeti-los aqui fazia o teste
    # explodir com KeyError quando uma pasta era acrescentada -- e um teste
    # que quebra por motivo alheio ao que ele verifica ensina a ignora-lo.
    caminhos_midia = list(PASTAS_MIDIA.values())

    sem_midia = montar(
        BackupLogicoExtractor,
        {c: montar_pull(c, SituacaoPull.INEXISTENTE) for c in caminhos_midia},
    )
    r = sem_midia.executar(pasta)
    checar("metadados coletados sem midia continua sucesso", r.sucesso is True)
    checar("porem marcado como copia incompleta", r.detalhes.get("copia_incompleta") is True)
    checar("mensagem diz explicitamente que NENHUMA midia veio", "NENHUM" in r.mensagem)

    nada = montar(
        BackupLogicoExtractor,
        {c: montar_pull(c, SituacaoPull.INEXISTENTE) for c in caminhos_midia},
        saida_texto="",
    )
    r = nada.executar(pasta)
    checar("sem metadados e sem midia e FALHA", r.sucesso is False)

    com_midia = montar(
        BackupLogicoExtractor,
        {c: montar_pull(c, SituacaoPull.OK, arquivos=100, bytes_copiados=5_000) for c in caminhos_midia},
    )
    r = com_midia.executar(pasta)
    checar("midia copiada e sucesso limpo", r.sucesso is True and not r.detalhes.get("copia_incompleta"))
    # Os totais saem da quantidade de caminhos, e nao de um numero fixo: o
    # que se verifica aqui e que a consolidacao SOMA todos, e nao quantos
    # caminhos o modulo tem hoje.
    checar(
        "total consolidado de arquivos confere",
        r.detalhes["arquivos_copiados"] == 100 * len(caminhos_midia),
    )
    checar(
        "total consolidado de bytes confere",
        r.detalhes["bytes_copiados"] == 5_000 * len(caminhos_midia),
    )


# ---------------------------------------------------------------------------
print("\n[5] Reconciliacao origem x destino e hash na aquisicao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td) / "caso"

    completo = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    completo._log_callback = lambda m: None
    completo._progress_callback = lambda p: None
    completo._cancelado = False
    completo.adb = ADBQueGrava(
        inventario={"/sdcard/DCIM": ["a.jpg", "b.jpg", "sub/c.jpg"]},
        copiados_por_caminho={"/sdcard/DCIM": ["a.jpg", "b.jpg", "sub/c.jpg"]},
    )
    aquisicao = completo.adquirir_caminho(
        "/sdcard/DCIM", pasta_caso / "media", pasta_caso, rotulo="midia_Camera"
    )
    checar("origem inventariada informa a contagem real", aquisicao.arquivos_na_origem == 3)
    checar("nada faltando quando tudo foi copiado", aquisicao.faltantes == [])
    checar("completude confirmada e verificavel", aquisicao.completa is True)
    checar("hash calculado para cada arquivo adquirido", len(aquisicao.hashes) == 3)
    checar(
        "hash e um SHA-256 valido",
        all(len(h) == 64 and h.isalnum() for h in aquisicao.hashes.values()),
    )
    checar(
        "manifesto da aquisicao gravado fora da pasta de evidencia",
        (pasta_caso / "aquisicao" / "midia_Camera.sha256").exists(),
    )
    reconciliacao = (pasta_caso / "aquisicao" / "midia_Camera_reconciliacao.txt").read_text(
        encoding="utf-8"
    )
    checar("relatorio de reconciliacao gravado", "RECONCILIA" in reconciliacao)
    checar("relatorio declara completude", "COMPLETA" in reconciliacao)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td) / "caso"

    parcial = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    parcial._log_callback = lambda m: None
    parcial._progress_callback = lambda p: None
    parcial._cancelado = False
    parcial.adb = ADBQueGrava(
        inventario={"/sdcard/DCIM": ["a.jpg", "b.jpg", "sumiu.jpg"]},
        copiados_por_caminho={"/sdcard/DCIM": ["a.jpg", "b.jpg"]},
    )
    aquisicao = parcial.adquirir_caminho(
        "/sdcard/DCIM", pasta_caso / "media", pasta_caso, rotulo="midia_Camera"
    )
    checar("arquivo que existia e nao veio e detectado", aquisicao.faltantes == ["sumiu.jpg"])
    checar("copia parcial NAO e declarada completa", aquisicao.completa is False)
    reconciliacao = (pasta_caso / "aquisicao" / "midia_Camera_reconciliacao.txt").read_text(
        encoding="utf-8"
    )
    checar("relatorio declara incompletude", "INCOMPLETA" in reconciliacao)
    checar("relatorio nomeia o arquivo faltante", "sumiu.jpg" in reconciliacao)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td) / "caso"

    sem_inventario = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    sem_inventario._log_callback = lambda m: None
    sem_inventario._progress_callback = lambda p: None
    sem_inventario._cancelado = False
    class SemFind(ADBQueGrava):
        def executar(self, argumentos, timeout=None):
            if "find" in linha_do_comando(argumentos):
                return "find: /data/data: Permission denied"
            return ""

    sem_inventario.adb = SemFind(inventario={}, copiados_por_caminho={"/data/data": ["x.db"]})
    aquisicao = sem_inventario.adquirir_caminho(
        "/data/data", pasta_caso / "fs", pasta_caso, rotulo="filesystem_data"
    )
    checar("origem nao inventariavel nao inventa contagem", aquisicao.arquivos_na_origem is None)
    checar(
        "completude nao verificavel NAO e reportada como completa",
        aquisicao.completa is None,
    )
    reconciliacao = (pasta_caso / "aquisicao" / "filesystem_data_reconciliacao.txt").read_text(
        encoding="utf-8"
    )
    checar("relatorio diz que a completude nao e verificavel", "VERIFIC" in reconciliacao)

    consolidado = FilesystemDumpExtractor.consolidar_reconciliacao([aquisicao])
    checar(
        "consolidacao marca completude como nao verificavel",
        consolidado["completude_verificavel"] is False,
    )


# ---------------------------------------------------------------------------
print("\n[5] Erro do ADB nao pode voltar pelo canal do dado legitimo")
# ---------------------------------------------------------------------------
from core.android.adb_client import ResultadoComando as RC

checar("comando bem-sucedido e sucesso", RC(0, "saida", "").sucesso is True)
checar("codigo de saida diferente de zero NAO e sucesso", RC(1, "", "boom").sucesso is False)
checar("timeout NAO e sucesso", RC(0, "", "", expirou=True).sucesso is False)
checar("timeout e descrito como tal", "tempo limite" in RC(0, "", "", expirou=True).motivo_falha)
checar("stderr vira motivo da falha", "boom" in RC(1, "", "boom").motivo_falha)
checar("sucesso nao tem motivo de falha", RC(0, "ok", "").motivo_falha == "")


class ADBQueFalha(ADBClient):
    """Simula o ADB estourando o tempo limite."""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        return ResultadoComando(-1, "", "tempo limite de execucao excedido", expirou=True)


falho = ADBQueFalha(caminho_binario=Path("adb"))
checar(
    "falha devolve string VAZIA, nunca a mensagem de erro como se fosse dado",
    falho.executar(["shell", "getprop", "ro.product.manufacturer"]) == "",
)
checar(
    "a propriedade lida de um comando que falhou vem vazia",
    falho.obter_propriedade("ro.product.manufacturer") == "",
)

# ---------------------------------------------------------------------------
print("\n[6] Origem vazia e um fato verificado, nao ausencia de verificacao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td) / "caso"

    vazio = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    vazio._log_callback = lambda m: None
    vazio._progress_callback = lambda p: None
    vazio._cancelado = False
    vazio.adb = ADBQueGrava(inventario={"/sdcard/DCIM": []}, copiados_por_caminho={})

    aquisicao = vazio.adquirir_caminho(
        "/sdcard/DCIM", pasta_caso / "media", pasta_caso, rotulo="midia_Camera"
    )
    checar("origem vazia informa ZERO, nao None", aquisicao.arquivos_na_origem == 0)

    consolidado = FilesystemDumpExtractor.consolidar_reconciliacao([aquisicao])
    checar("consolidacao preserva o zero verificado", consolidado["arquivos_na_origem"] == 0)
    checar(
        "origem vazia inventariada CONTINUA sendo verificavel",
        consolidado["completude_verificavel"] is True,
    )

    reconciliacao = (pasta_caso / "aquisicao" / "midia_Camera_reconciliacao.txt").read_text(
        encoding="utf-8"
    )
    checar("relatorio diz ORIGEM VAZIA, nao COMPLETA", "ORIGEM VAZIA" in reconciliacao)
    checar(
        "relatorio nao sugere que algo foi adquirido",
        "todo arquivo inventariado na origem foi adquirido" not in reconciliacao,
    )


print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
