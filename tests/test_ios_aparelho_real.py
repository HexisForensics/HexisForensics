"""
Três defeitos achados no primeiro iPhone real (iPhone 11, iOS 18.6.2, 29/10/2026).

1. Aparelho que nunca teve senha de backup não tem o valor `WillEncrypt`, e a
   suíte tratava a ausência como erro — o backup cifrado nem começava.
2. A recusa do iPhone ("Unable to backup until Setup is finished", código
   212) ia para o desfecho crua, em inglês, com o convite da biblioteca para
   abrir chamado no GitHub. Agora é traduzida; a resposta crua vai para o log.
3. O console terminava em "[CONCLUÍDO] ... Manifesto": quem lia só o fim
   achava que a coleta dera certo, com o backup recusado logo acima. Agora o
   lacre diz [LACRE] e a última coisa mostrada é o desfecho.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from pymobiledevice3.exceptions import MissingValueError, PyMobileDevice3Exception  # noqa: E402

from core import hashing  # noqa: E402
from core.desfecho import descrever_execucao  # noqa: E402
from core.ios import client as modulo_cliente  # noqa: E402
from core.ios.client import ErroIOS, IOSClient  # noqa: E402
from core.ios.extractors.backup import BackupCompletoExtractorIOS  # noqa: E402
from services.extraction_service import ExtractionService  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


UDID = "00000000-00000000000X000X"

# Texto exato devolvido pelo iPhone 11 real em 29/10/2026.
RECUSA_212 = (
    "The device reported an error: {'ErrorCode': 212, 'ErrorDescription': 'Unable to backup "
    "until Setup is finished (MBErrorDomain/212)', 'MessageName': 'Response'}.\nPlease report "
    "it at https://github.com/doronz88/pymobiledevice3/issues, with the output of the same "
    "command run with -v (`pymobiledevice3 -v ...`), so support for it can be added."
)


class LockdownFalso:
    def __init__(self, valor):
        self.valor = valor

    async def get_value(self, dominio, chave):
        if self.valor is None:
            raise MissingValueError("No such value.", UDID, "18.6.2")
        return self.valor

    async def close(self):
        pass


def cliente_com(valor) -> IOSClient:
    cliente = IOSClient(UDID)

    async def lockdown(_udid):
        return LockdownFalso(valor)

    cliente._lockdown = lockdown
    return cliente


print("\n[1] Senha de backup nunca definida: o valor não existe no aparelho")
cliente = cliente_com(None)
checar("ausência de 'WillEncrypt' é 'sem senha', não erro", cliente.cifragem_ativa() is False)
checar("e fica anotado que a resposta veio da ausência", cliente.cifragem_informada is False)
cliente = cliente_com(True)
checar("valor informado continua valendo", cliente.cifragem_ativa() is True
       and cliente.cifragem_informada is True)


print("\n[2] A recusa do iPhone é traduzida, e a resposta crua é preservada")


class ServicoQueRecusa:
    def __init__(self, _lockdown):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def backup(self, **_):
        raise PyMobileDevice3Exception(RECUSA_212)


original_biblioteca = modulo_cliente._biblioteca
modulo_cliente._biblioteca = lambda: (None, None, ServicoQueRecusa)
try:
    cliente = cliente_com(False)
    with tempfile.TemporaryDirectory() as temporario:
        try:
            cliente.fazer_backup(Path(temporario))
            erro = None
        except ErroIOS as e:
            erro = e
finally:
    modulo_cliente._biblioteca = original_biblioteca

checar("a mensagem diz, em português, o que fazer",
       erro is not None and "configuração inicial" in str(erro) and "212" in str(erro))
checar("o convite para abrir chamado no GitHub não vai para o documento",
       erro is not None and "github" not in str(erro).lower())
checar("a resposta crua do iPhone é guardada",
       erro is not None and "Unable to backup until Setup is finished" in erro.original
       and "Please report" not in erro.original)


class ClienteQueRecusa:
    udid = UDID

    def definir_udid(self, udid):
        self.udid = udid

    def fazer_backup(self, destino, progresso=None):
        raise ErroIOS(modulo_cliente.RECUSAS_DE_BACKUP[212],
                      "PyMobileDevice3Exception: ... Unable to backup until Setup is finished")


linhas_do_log = []
with tempfile.TemporaryDirectory() as temporario:
    extrator = BackupCompletoExtractorIOS(client=ClienteQueRecusa())
    extrator.log = linhas_do_log.append
    resultado = extrator.executar(Path(temporario))
checar("o módulo continua sem sucesso", not resultado.sucesso)
checar("a resposta crua vai para o log da aquisição",
       any("Unable to backup until Setup is finished" in l for l in linhas_do_log))


print("\n[3] O console termina no desfecho, não no lacre")
servico = ExtractionService([], Path(tempfile.gettempdir()))
servico.desfecho = descrever_execucao([
    ("ios_identificacao", "Identificação do iPhone", True, "ok", {}),
    ("ios_backup_completo", "Backup local do iPhone", False, "recusado", {}),
])
linhas = servico.linhas_do_desfecho()
texto = "\n".join(linhas)
checar("com módulo sem dado, o desfecho chama atenção",
       any(l.startswith("[DESFECHO — ATENÇÃO]") for l in linhas))
checar("e nomeia o módulo que não obteve dado",
       "NÃO OBTEVE DADO: Backup local do iPhone" in texto)
checar("a barra de status também avisa",
       servico.texto_da_barra_de_status().startswith("ATENÇÃO")
       and "sem obter dado" in servico.texto_da_barra_de_status())

servico.desfecho = descrever_execucao([
    ("ios_identificacao", "Identificação do iPhone", True, "ok", {}),
])
checar("coleta integral: desfecho sem alerta",
       any(l.startswith("[DESFECHO] ") for l in servico.linhas_do_desfecho())
       and not servico.texto_da_barra_de_status().startswith("ATENÇÃO"))

with tempfile.TemporaryDirectory() as temporario:
    (Path(temporario) / "a.txt").write_text("x", encoding="utf-8")
    mensagens = []
    hashing.gerar_manifesto(Path(temporario), log_callback=mensagens.append)
checar("o lacre não se anuncia como [CONCLUÍDO]",
       any(m.startswith("[LACRE]") for m in mensagens)
       and not any("[CONCLUÍDO]" in m for m in mensagens))

print("\n[4] A senha temporária chega à decifragem sem ser copiada do log")
from core import backup_ios  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from services.decifragem_service import senha_gerada_na_aquisicao  # noqa: E402

with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "ios_20261029_181234"
    pasta = aquisicao / backup_ios.PASTA
    pasta.mkdir(parents=True)
    checar("sem o arquivo da senha, nada é sugerido", senha_gerada_na_aquisicao(aquisicao) == "")
    arquivo = pasta / "senha_do_backup.txt"
    arquivo.write_text("SENHA DE BACKUP TEMPORÁRIA\nSenha: P2B6-VFSL-KHNN-URDR\n", encoding="utf-8")
    checar("arquivo sem lacre não é oferecido", senha_gerada_na_aquisicao(aquisicao) == "")
    gerar_manifesto(aquisicao, log_callback=lambda _m: None)
    checar("arquivo lacrado: a senha vem preenchida",
           senha_gerada_na_aquisicao(aquisicao) == "P2B6-VFSL-KHNN-URDR")
    arquivo.write_text("SENHA DE BACKUP TEMPORÁRIA\nSenha: OUTRA\n", encoding="utf-8")
    checar("arquivo alterado depois do lacre não é oferecido",
           senha_gerada_na_aquisicao(aquisicao) == "")


print("\n[5] A barra de progresso zera a cada módulo")


source = (RAIZ_PROJETO / "services" / "extraction_service.py").read_text(encoding="utf-8")
inicio = source.index("extrator._progress_callback = self.progresso_emitido.emit")
trecho = source[inicio:inicio + 400]
checar("o serviço zera a barra antes de cada módulo", "self.progresso_emitido.emit(0)" in trecho)

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
