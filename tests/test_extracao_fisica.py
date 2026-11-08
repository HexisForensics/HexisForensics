"""Testes dos cenários de falha da extração física."""
import sys
import hashlib
import tempfile
from pathlib import Path

# Permite rodar o teste direto (`python tests/test_extracao_fisica.py`) sem
# instalar o projeto: a raiz fica um nível acima desta pasta.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

# PySide6 não é necessário para core/, mas o registry importa pacotes; isolamos.
from core.android.adb_client import ResultadoStream
from core.hashing import EscritorComHash, gravar_hash_avulso
from core.android.extractors.physical_extraction import ExtracaoFisicaExtractor

class FakeADB:
    def __init__(self, particao=True, tamanho=None, dados=b"", codigo=0, stderr="", exec_out=True):
        self._particao, self._tamanho = particao, tamanho
        self._dados, self._codigo, self._stderr = dados, codigo, stderr
        self._exec_out = exec_out
    def executar(self, args, timeout=None):
        cmd = " ".join(args)
        if "ls /dev/block" in cmd:
            return "/dev/block/bootdevice/by-name/userdata" if self._particao else "No such file"
        if "getsize64" in cmd or "stat -c" in cmd:
            return str(self._tamanho) if self._tamanho else ""
        return ""
    def suporta_exec_out(self): return self._exec_out
    def stream_binario(self, args, ao_receber_bloco, tamanho_bloco=None, cancelado=None):
        # A sonda de acesso (`count=1`) e a copia real sao chamadas distintas:
        # a sonda le 512 bytes so para descobrir se a particao e legivel, e e
        # ela que captura o motivo de uma recusa -- a copia real silencia o
        # stderr do `dd` para nao contaminar a imagem.
        if "count=1" in " ".join(args):
            if "Permission denied" in self._stderr or "not permitted" in self._stderr:
                ao_receber_bloco(self._stderr.encode("utf-8"))
                return ResultadoStream(1, self._stderr, len(self._stderr))
            ao_receber_bloco(b"\x00" * 512)
            return ResultadoStream(0, "", 512)
        if self._dados: ao_receber_bloco(self._dados)
        return ResultadoStream(self._codigo, self._stderr, len(self._dados))
    def verificar_binario(self): return True, ""

def montar(**kw):
    e = ExtracaoFisicaExtractor.__new__(ExtracaoFisicaExtractor)
    e._log_callback = lambda m: None
    e._progress_callback = lambda p: None
    e._cancelado = False
    e.adb = FakeADB(**kw)
    return e

falhas = []
def checar(nome, cond):
    print(("  OK  " if cond else " FALHA ") + nome)
    if not cond: falhas.append(nome)

with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)

    # 1. Imagem de 0 byte -> DEVE falhar (antes retornava sucesso)
    r = montar(dados=b"").executar(pasta)
    checar("imagem de 0 byte é reportada como FALHA", r.sucesso is False)
    checar("mensagem explica que nada foi transmitido", "vazia" in r.mensagem.lower())

    # 2. Extração íntegra -> sucesso + hash correto
    dados = b"\x00\xffEVIDENCIA\x0a\x0d" * 1000
    r = montar(dados=dados, tamanho=len(dados)).executar(pasta)
    checar("extração completa retorna sucesso", r.sucesso is True)
    checar("hash confere com SHA-256 real", r.detalhes["sha256"] == hashlib.sha256(dados).hexdigest())
    checar("sidecar .sha256 foi gravado", (pasta/"physical"/"imagem_fisica_userdata.img.sha256").exists())

    # 3. Bytes preservados sem tradução de 0x0a
    gravado = (pasta/"physical"/"imagem_fisica_userdata.img").read_bytes()
    checar("bytes gravados idênticos à origem (sem corrupção)", gravado == dados)

    # 4. Imagem truncada (50% do esperado) -> falha
    r = montar(dados=b"X"*500, tamanho=1000).executar(pasta)
    checar("imagem truncada é reportada como FALHA", r.sucesso is False)
    checar("mensagem indica imagem incompleta", "incompleta" in r.mensagem.lower())

    # 5. Código de saída != 0 -> falha mesmo com bytes
    r = montar(dados=b"X"*1000, tamanho=1000, codigo=1).executar(pasta)
    checar("código de saída diferente de zero é FALHA", r.sucesso is False)

    # 6. Permission denied -> falha explícita
    r = montar(dados=b"", stderr="dd: /dev/block: Permission denied").executar(pasta)
    checar("acesso negado é FALHA explícita", r.sucesso is False and "root" in r.mensagem)

    # 7. ADB sem exec-out -> recusa em vez de corromper
    r = montar(dados=b"X"*100, exec_out=False).executar(pasta)
    checar("ADB sem exec-out interrompe a extração", r.sucesso is False and "exec-out" in r.mensagem)

    # 8. Partição inexistente
    r = montar(particao=False).executar(pasta)
    checar("partição não localizada é FALHA", r.sucesso is False)

    # 9. Sem tamanho conhecido -> sucesso COM ressalva
    r = montar(dados=b"X"*100).executar(pasta)
    checar("sem tamanho declarado: sucesso com ressalva", r.sucesso is True and "Ressalva" in r.mensagem)

    # 10. Imagem MAIOR que a particao -- defeito encontrado na primeira
    # execucao real deste modulo, contra um emulador Android 13.
    #
    # O `adb exec-out` funde o stderr do comando remoto no fluxo binario, e
    # o `dd` escreve seu resumo ao terminar ("N records in/out, X bytes
    # copied"). Resultado: 97 bytes de TEXTO colados no fim de uma copia
    # bit-a-bit de 6 GiB, com o hash cobrindo o lixo -- imagem que jamais
    # baterá com uma copia correta da mesma particao.
    #
    # A verificacao dizia `if gravados >= esperado: sucesso`, supondo que
    # sobra nao acontece. Acontece, e sobra e tao fatal quanto falta: byte a
    # mais so pode vir de algo que nao e a particao.
    r = montar(dados=b"D"*1097, tamanho=1000).executar(pasta)
    checar("imagem MAIOR que a particao e FALHA", r.sucesso is False)
    checar("a mensagem diz que ha bytes a mais", "97 byte(s) a mais" in r.mensagem)
    checar("e que a imagem nao e copia fiel", "NÃO é cópia fiel" in r.mensagem)
    checar("marcando como incompleta nos detalhes", r.detalhes.get("incompleta") is True)

    # 11. O comando de copia silencia o stderr NO APARELHO -- e o que impede
    # o resumo do `dd` de entrar na imagem. Sem isso, o defeito acima volta.
    comandos = []

    class ADBEspiao(FakeADB):
        def stream_binario(self, args, ao_receber_bloco, tamanho_bloco=None, cancelado=None):
            comandos.append(" ".join(args))
            return super().stream_binario(args, ao_receber_bloco, tamanho_bloco, cancelado)

    e = ExtracaoFisicaExtractor.__new__(ExtracaoFisicaExtractor)
    e._log_callback = lambda m: None
    e._progress_callback = lambda p: None
    e._cancelado = False
    e.adb = ADBEspiao(dados=b"Z"*1000, tamanho=1000)
    e.executar(pasta)

    sonda = [c for c in comandos if "count=1" in c]
    copia = [c for c in comandos if "count=1" not in c]
    checar("a sonda de acesso roda antes da copia", len(sonda) == 1 and len(copia) == 1)
    checar("a copia silencia o stderr no aparelho", "2>/dev/null" in copia[0])
    checar("e a sonda NAO silencia, pois precisa do motivo", "2>/dev/null" not in sonda[0])

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
