"""
Testes da leitura individual dos arquivos que a copia em bloco deixou.

Achado em 09/10/2026, na primeira vez que o Dump do Sistema de Arquivos
rodou contra um aparelho com WhatsApp instalado e root:

    Origem inventariada por 'find': 693 arquivo(s) em /data/data
    adb: error: cannot create '...\\com.whatsapp\\app_qpl\\qpl_sampling_
        config_v2.5feceb66...': Not a directory
    Filesystem extraido: 7 arquivo(s), 9964 byte(s).      <- sucesso=True

O `adb pull` de uma pasta ABORTA INTEIRO no primeiro arquivo que a estacao
nao consegue gravar. Um arquivo de configuracao cujo caminho de destino
passava do limite do Windows derrubou os 693 -- e com eles o msgstore.db.

No mesmo teste, `/sdcard` falhou ao criar uma pasta LOCAL, o texto do erro
trazia "No such file or directory", e a copia foi classificada como
"caminho nao existe no aparelho": afirmacao sobre o dispositivo feita a
partir de um erro da estacao.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import (  # noqa: E402
    ADBClient,
    ResultadoPull,
    ResultadoStream,
    SituacaoPull,
)
from core.android.extractors.base import ResultadoAquisicao  # noqa: E402
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
print("\n[1] Erro ao gravar NA ESTACAO nao vira afirmacao sobre o aparelho")
# ---------------------------------------------------------------------------
classificar = ADBClient._classificar_pull
erro_local = ("adb: error: failed to create directory 'C:\\caso\\sdcard\\.Thumbs\\': "
              "No such file or directory")
checar("'failed to create directory' local NAO e 'caminho inexistente no aparelho'",
       classificar(1, erro_local, 0) is not SituacaoPull.INEXISTENTE)
checar("e classificado como ERRO", classificar(1, erro_local, 0) is SituacaoPull.ERRO)
checar("'cannot create' local com 'Permission denied' NAO e 'acesso negado pelo Android'",
       classificar(1, "adb: error: cannot create 'C:\\x': Permission denied", 0)
       is SituacaoPull.ERRO)
checar("caminho que realmente nao existe no aparelho continua INEXISTENTE",
       classificar(1, "adb: error: failed to stat remote object '/sdcard/x': "
                      "No such file or directory", 0) is SituacaoPull.INEXISTENTE)
checar("recusa real do Android continua ACESSO_NEGADO",
       classificar(1, "adb: error: failed to copy: Permission denied", 0)
       is SituacaoPull.ACESSO_NEGADO)


# ---------------------------------------------------------------------------
print("\n[2] O que a copia em bloco deixou e lido um a um")
# ---------------------------------------------------------------------------
CONTEUDO = {
    "/data/data/com.whatsapp/databases/msgstore.db": b"SQLite format 3\x00" + b"\r\n\x00\x1a" * 50,
    "/data/data/com.whatsapp/databases/wa.db": b"SQLite format 3\x00agenda",
    "/data/data/com.app/files/vazio": b"",
}


class ADBQueLeUmAUm:
    """`exec-out cat` devolve o arquivo; o que nao esta em CONTEUDO falha."""

    def __init__(self):
        self.comandos = []

    def stream_binario(self, argumentos, ao_receber_bloco, tamanho_bloco=0, cancelado=None):
        self.comandos.append(argumentos)
        remoto = argumentos[1].split("'")[1]
        if remoto not in CONTEUDO:
            return ResultadoStream(1, "", 0)
        ao_receber_bloco(CONTEUDO[remoto])
        return ResultadoStream(0, "", len(CONTEUDO[remoto]))


def aquisicao_que_falhou(destino, faltantes):
    return ResultadoAquisicao(
        copia=ResultadoPull(
            caminho_remoto="/data/data", caminho_local=destino, codigo_saida=1, stdout="",
            stderr="adb: error: cannot create '...': Not a directory",
            arquivos_copiados=0, bytes_copiados=0, situacao=SituacaoPull.ERRO,
        ),
        arquivos_na_origem=len(faltantes),
        faltantes=list(faltantes),
    )


with tempfile.TemporaryDirectory() as tmp:
    destino = Path(tmp) / "data_apps"
    destino.mkdir()
    extrator = FilesystemDumpExtractor()
    extrator.adb = ADBQueLeUmAUm()
    extrator.log = lambda texto: None

    aquisicao = aquisicao_que_falhou(destino, [
        "com.whatsapp/databases/msgstore.db",
        "com.whatsapp/databases/wa.db",
        "com.app/files/vazio",
    ])
    extrator._recuperar_faltantes("/data/data", destino, aquisicao)

    banco = destino / "data" / "com.whatsapp" / "databases" / "msgstore.db"
    checar("o banco que a copia em bloco perdeu e recuperado", banco.is_file())
    checar("byte a byte, sem traducao de fim de linha",
           banco.read_bytes() == CONTEUDO["/data/data/com.whatsapp/databases/msgstore.db"])
    checar("pelo exec-out, nunca por adb shell",
           all(c[0] == "exec-out" for c in extrator.adb.comandos))
    checar("arquivo legitimamente vazio e recuperado como vazio",
           (destino / "data" / "com.app" / "files" / "vazio").stat().st_size == 0)
    checar("os tres sao contados como recuperados", aquisicao.recuperados_um_a_um == 3)
    checar("nenhum faltante resta", aquisicao.faltantes == [])
    checar("a contagem em disco e refeita", aquisicao.copia.arquivos_copiados == 3)
    checar("o caminho, adquirido por inteiro pela segunda via, deixa de constar como erro",
           aquisicao.copia.situacao is SituacaoPull.OK)
    checar("e o erro original do ADB continua preservado",
           "cannot create" in aquisicao.copia.stderr)
    checar("a recuperacao cai no lugar que a reconciliacao confere",
           sorted(extrator._relativizar_obtidos("/data/data", destino)) == sorted([
               "com.whatsapp/databases/msgstore.db", "com.whatsapp/databases/wa.db",
               "com.app/files/vazio"]))


# ---------------------------------------------------------------------------
print("\n[3] O que NEM ASSIM vier continua faltante, com o motivo")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    destino = Path(tmp) / "data_apps"
    (destino / "data" / "com.app").mkdir(parents=True)
    # Ja adquirido pela copia em bloco. O Android tem tambem um `Config`,
    # que no Windows e o MESMO arquivo.
    (destino / "data" / "com.app" / "config").write_bytes(b"adquirido primeiro")

    extrator = FilesystemDumpExtractor()
    extrator.adb = ADBQueLeUmAUm()
    extrator.log = lambda texto: None
    aquisicao = aquisicao_que_falhou(destino, [
        "com.whatsapp/databases/wa.db",
        "com.app/Config",
        "com.app/recusado_pelo_aparelho",
    ])
    extrator._recuperar_faltantes("/data/data", destino, aquisicao)

    checar("o que deu para ler foi lido", aquisicao.recuperados_um_a_um == 1)
    checar("os dois que nao vieram continuam na lista",
           sorted(aquisicao.faltantes) == ["com.app/Config", "com.app/recusado_pelo_aparelho"])
    checar("a falha de leitura no aparelho tem o motivo e o codigo",
           "código 1" in aquisicao.motivos_dos_faltantes["com.app/recusado_pelo_aparelho"])
    checar("leitura que falhou nao deixa arquivo de zero byte no destino",
           not (destino / "data" / "com.app" / "recusado_pelo_aparelho").exists())
    checar("o arquivo ja adquirido NAO e sobrescrito pela tentativa do homonimo",
           (destino / "data" / "com.app" / "config").read_bytes() == b"adquirido primeiro")
    checar("com faltante restando, o caminho continua marcado como ERRO",
           aquisicao.copia.situacao is SituacaoPull.ERRO)


# ---------------------------------------------------------------------------
print("\n[4] Nome que o Windows nao aceita: gravado com nome alternativo, anotado")
# ---------------------------------------------------------------------------
# Visto no moto x4 em 24/10/2026: 'DOC-20261012-WA0000.' (ponto no fim) nao
# foi adquirido. O Windows tira ponto e espaco do fim do nome e nao
# distingue maiusculas; antes o arquivo ficava para tras.
CONTEUDO["/data/data/com.app/Config"] = b"homonimo com maiuscula"
CONTEUDO["/data/data/com.app/DOC-WA0000."] = b"documento com ponto no fim"
with tempfile.TemporaryDirectory() as tmp:
    destino = Path(tmp) / "data_apps"
    (destino / "data" / "com.app").mkdir(parents=True)
    (destino / "data" / "com.app" / "config").write_bytes(b"adquirido primeiro")
    extrator = FilesystemDumpExtractor()
    extrator.adb = ADBQueLeUmAUm()
    extrator.log = lambda texto: None
    aquisicao = aquisicao_que_falhou(destino, ["com.app/Config", "com.app/DOC-WA0000."])
    extrator._recuperar_faltantes("/data/data", destino, aquisicao)

    pasta = destino / "data" / "com.app"
    checar("os dois foram adquiridos, nenhum ficou para tras",
           aquisicao.faltantes == [] and aquisicao.recuperados_um_a_um == 2)
    checar("o que ja estava la continua intacto",
           (pasta / "config").read_bytes() == b"adquirido primeiro")
    if sys.platform == "win32":
        checar("o homonimo foi gravado com nome alternativo, com o conteudo dele",
               (pasta / "Config (nome alterado 1)").read_bytes() == b"homonimo com maiuscula")
    checar("o de ponto no fim tambem",
           (pasta / "DOC-WA0000 (nome alterado 1)").read_bytes() == b"documento com ponto no fim")
    checar("a correspondencia nome na estacao -> nome no aparelho e anotada",
           aquisicao.nomes_trocados.get("com.app/DOC-WA0000 (nome alterado 1)")
           == "com.app/DOC-WA0000.")

    from core.hashing import calcular_sha256  # noqa: E402
    aquisicao.hashes = {
        f.relative_to(destino).as_posix(): calcular_sha256(f) for f in destino.rglob("*")
        if f.is_file()
    }
    pedidos = []

    def hashear_na_origem(remoto, nomes):
        pedidos.extend(nomes)
        return {}, "simulado"

    extrator.hashear_na_origem = hashear_na_origem
    extrator.verificar_fidelidade("/data/data", destino, aquisicao)
    checar("a fidelidade e conferida pelo nome que o arquivo tem NO APARELHO",
           "com.app/DOC-WA0000." in pedidos
           and "com.app/DOC-WA0000 (nome alterado 1)" not in pedidos)


print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
