"""
Testes do nivel 3: estado do aparelho ao ser recebido, bugreport e a
limitacao de perfis de usuario.

A limitacao de perfis merece nota: ela existia desde o inicio do projeto e
NAO estava declarada em lugar nenhum. A extracao alcanca apenas o usuario
principal; um perfil de trabalho ou um segundo usuario mantem area de dados
propria, intocada. Concluir sobre o conteudo do aparelho sem saber disso e
concluir sobre uma fracao dele.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoStream
from core.android.extractors.bugreport import BugreportExtractor
from core.android.extractors.estado_dispositivo import EstadoDispositivoExtractor
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor

falhas = []

PNG_MINIMO = b"\x89PNG\r\n\x1a\n" + b"conteudo sintetico da imagem" * 10

UM_PERFIL = "Users:\n\tUserInfo{0:Owner:c13} running\n"
DOIS_PERFIS = (
    "Users:\n"
    "\tUserInfo{0:Owner:c13} running\n"
    "\tUserInfo{10:Perfil de trabalho:1030} running\n"
)


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


class ADBEstado:
    """Aparelho que responde ao estado e devolve uma captura de tela."""

    def __init__(self, usuarios=UM_PERFIL, exec_out=True, imagem=PNG_MINIMO):
        self.usuarios = usuarios
        self.exec_out = exec_out
        self.imagem = imagem
        self.argumentos_da_captura = None

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = " ".join(argumentos)
        if "list users" in linha:
            return ResultadoComando(0, self.usuarios, "")
        if "dumpsys" in linha:
            return ResultadoComando(0, "estado do subsistema consultado", "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos).stdout

    def suporta_exec_out(self):
        return self.exec_out

    def stream_binario(self, argumentos, ao_receber_bloco, tamanho_bloco=None, cancelado=None):
        self.argumentos_da_captura = list(argumentos)
        if self.imagem:
            ao_receber_bloco(self.imagem)
        return ResultadoStream(0, "", len(self.imagem))


# ---------------------------------------------------------------------------
print("\n[1] Estado do aparelho ao ser recebido")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    adb = ADBEstado()
    resultado = montar(EstadoDispositivoExtractor, adb).executar(pasta_caso)
    pasta = pasta_caso / "estado_inicial"

    checar("o estado inicial e registrado", resultado.sucesso is True)
    checar("a captura de tela e obtida", resultado.detalhes["captura_de_tela"] is True)
    checar("a imagem e gravada", (pasta / "tela_ao_receber.png").exists())
    checar(
        "os bytes da imagem chegam intactos",
        (pasta / "tela_ao_receber.png").read_bytes() == PNG_MINIMO,
    )
    checar("o hash da imagem e gravado ao lado", (pasta / "tela_ao_receber.png.sha256").exists())
    checar(
        "a captura usa exec-out, e nao adb shell",
        adb.argumentos_da_captura[0] == "exec-out",
    )
    checar("o resumo do estado e gerado", (pasta / "RESUMO_ESTADO.txt").exists())

    resumo = (pasta / "RESUMO_ESTADO.txt").read_text(encoding="utf-8")
    checar(
        "o resumo explica que tela bloqueada nao e falha",
        "não indica falha da coleta" in resumo,
    )

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    sem_exec_out = ADBEstado(exec_out=False)
    resultado = montar(EstadoDispositivoExtractor, sem_exec_out).executar(pasta_caso)

    checar("sem exec-out, a captura NAO e tentada", resultado.detalhes["captura_de_tela"] is False)
    checar(
        "e nenhuma imagem corrompida e gravada",
        not (pasta_caso / "estado_inicial" / "tela_ao_receber.png").exists(),
    )
    checar("o restante do estado continua sendo coletado", resultado.sucesso is True)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    sem_imagem = ADBEstado(imagem=b"")
    resultado = montar(EstadoDispositivoExtractor, sem_imagem).executar(pasta_caso)
    checar(
        "captura vazia nao deixa arquivo de 0 byte no caso",
        not (pasta_caso / "estado_inicial" / "tela_ao_receber.png").exists(),
    )

# ---------------------------------------------------------------------------
print("\n[2] Limitacao de perfis de usuario, antes silenciosa")
# ---------------------------------------------------------------------------
um = montar(EstadoDispositivoExtractor, ADBEstado(usuarios=UM_PERFIL))
dois = montar(EstadoDispositivoExtractor, ADBEstado(usuarios=DOIS_PERFIS))

checar("um perfil e contado corretamente", um.contar_perfis_de_usuario() == 1)
checar("dois perfis sao contados corretamente", dois.contar_perfis_de_usuario() == 2)

aviso = EstadoDispositivoExtractor.restricao_de_multiplos_usuarios(2)
checar("a ressalva informa a quantidade", "2 perfis" in aviso)
checar("a ressalva diz que so o perfil principal foi alcancado", "usuario 0" in aviso)
checar("a ressalva nomeia a area nao adquirida", "/data/user/" in aviso)
checar("a ressalva proibe a conclusao negativa", "NAO autoriza concluir" in aviso)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    resultado = montar(EstadoDispositivoExtractor, ADBEstado(usuarios=DOIS_PERFIS)).executar(
        pasta_caso
    )
    checar("com dois perfis, a extracao vira parcial", resultado.detalhes.get("copia_incompleta") is True)
    checar("os perfis nao extraidos sao contados", resultado.detalhes["perfis_nao_extraidos"] == 1)
    checar("a mensagem final menciona a ressalva", "perfis" in resultado.mensagem)

    registro = (pasta_caso / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("a limitacao vira decisao no registro do caso", "perfil principal" in registro)

with tempfile.TemporaryDirectory() as td:
    resultado = montar(EstadoDispositivoExtractor, ADBEstado(usuarios=UM_PERFIL)).executar(Path(td))
    checar(
        "com um unico perfil, nenhuma ressalva e criada",
        resultado.detalhes.get("copia_incompleta") is None,
    )

# ---------------------------------------------------------------------------
print("\n[3] Bugreport: formato conforme a versao, e vazio nao e evidencia")
# ---------------------------------------------------------------------------
class ADBBugreport:
    def __init__(self, api="28", gera_zip=True, texto="", expirou=False):
        self.api = api
        self.gera_zip = gera_zip
        self.texto = texto
        self.expirou = expirou
        self.argumentos = None

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        if "getprop" in " ".join(argumentos):
            return ResultadoComando(0, self.api, "")
        return ResultadoComando(0, "", "")

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        return self.executar_detalhado(argumentos).stdout

    def executar_longo(self, argumentos, cancelado=None, ao_progredir=None, segundos_sem_sinal=None):
        self.argumentos = list(argumentos)
        if self.gera_zip and len(argumentos) > 1:
            destino = Path(argumentos[1]) / "bugreport-teste-2026-08-22.zip"
            destino.write_bytes(b"PK\x03\x04conteudo sintetico do bugreport")
        return ResultadoComando(0, self.texto, "", expirou=self.expirou)


with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    adb = ADBBugreport(api="28")
    resultado = montar(BugreportExtractor, adb).executar(pasta_caso)

    checar("bugreport em zip e obtido", resultado.sucesso is True)
    checar("o formato e registrado", resultado.detalhes["formato"] == "zip")
    checar("o destino e passado ao ADB", len(adb.argumentos) == 2)
    checar("o hash do pacote e calculado", len(resultado.detalhes["sha256"]) == 64)
    checar(
        "o hash e gravado ao lado do pacote",
        (pasta_caso / "bugreport" / f"{resultado.detalhes['arquivo']}.sha256").exists(),
    )

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    antigo = ADBBugreport(api="21", gera_zip=False, texto="========\nDUMP OF SERVICE\n" * 20)
    resultado = montar(BugreportExtractor, antigo).executar(pasta_caso)

    checar("em Android antigo o bugreport sai como texto", resultado.detalhes["formato"] == "texto")
    checar("o texto e gravado", (pasta_caso / "bugreport" / "bugreport.txt").exists())
    checar("nenhum destino e passado ao ADB nesse formato", len(antigo.argumentos) == 1)

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    vazio = ADBBugreport(api="28", gera_zip=False, texto="")
    resultado = montar(BugreportExtractor, vazio).executar(pasta_caso)

    checar("bugreport sem conteudo e FALHA", resultado.sucesso is False)
    checar(
        "e nenhum arquivo vazio permanece no caso",
        list((pasta_caso / "bugreport").glob("*")) == [],
    )

with tempfile.TemporaryDirectory() as td:
    pasta_caso = Path(td)
    truncado = ADBBugreport(api="28", expirou=True)
    resultado = montar(BugreportExtractor, truncado).executar(pasta_caso)

    checar("bugreport interrompido ainda e aproveitado", resultado.sucesso is True)
    checar("porem marcado como parcial", resultado.detalhes.get("copia_incompleta") is True)
    checar("e a mensagem adverte sobre truncamento", "truncado" in resultado.mensagem)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
