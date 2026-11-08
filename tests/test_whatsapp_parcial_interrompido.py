"""
WhatsApp: cópia interrompida COM dado no disco não é "nenhum dado".

Defeito travado aqui (A56 real, Android 16, 07/11/2026): o aparelho caiu do
USB no meio da cópia da mídia do WhatsApp. A cópia daquele caminho terminou
em ERRO — e, como `ResultadoPull.sucesso` só é verdadeiro em `OK`, o caminho
não entrou em `caminhos_com_dados`. Resultado: `localizacoes_com_dados == 0`,
e o módulo concluía **"Nenhum dado do WhatsApp foi encontrado"** — com 2,9 GB
(10.716 arquivos) já gravados na pasta. Afirmar ausência do que se obteve é a
conclusão negativa falsa que a ferramenta não admite.

A correção: "nada" só quando NADA veio. Com bytes no disco, o desfecho é
cópia PARCIAL (sucesso com ressalva `copia_incompleta`), nunca "nenhum dado".
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoPull, SituacaoPull  # noqa: E402
from core.android.extractors.base import ResultadoAquisicao  # noqa: E402
from core.android.extractors.whatsapp import WhatsAppExtractor  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def pull(caminho, situacao, arquivos=0, bytes_copiados=0):
    return ResultadoPull(
        caminho_remoto=caminho,
        caminho_local=Path("."),
        codigo_saida=0 if situacao is SituacaoPull.OK else 1,
        stdout="",
        stderr="",
        arquivos_copiados=arquivos,
        bytes_copiados=bytes_copiados,
        situacao=situacao,
    )


def montar(fabrica_de_pull):
    """
    WhatsAppExtractor com `adquirir_caminho` dublado: cada caminho candidato
    recebe o `ResultadoPull` que `fabrica_de_pull(caminho)` devolver.
    """
    e = WhatsAppExtractor.__new__(WhatsAppExtractor)
    e._log_callback = lambda m: None
    e._progress_callback = lambda p: None
    e._cancelado = False
    e._registrar_datas_dos_backups = lambda *a, **k: None

    def adquirir(caminho_android, destino, pasta_caso, rotulo="", faixa_progresso=(0, 100)):
        return ResultadoAquisicao(copia=fabrica_de_pull(caminho_android))

    e.adquirir_caminho = adquirir
    return e


# ---------------------------------------------------------------------------
print("\n[1] Cópia que ERROU com 2,9 GB no disco -> PARCIAL, nunca 'nenhum dado'")
# ---------------------------------------------------------------------------
def erro_com_bytes(caminho):
    # Um caminho traz muito dado mas a cópia é interrompida (ERRO); o resto
    # simplesmente não existe no aparelho.
    if "com.whatsapp/WhatsApp/Media" in caminho:
        return pull(caminho, SituacaoPull.ERRO, arquivos=10716, bytes_copiados=2_900_000_000)
    return pull(caminho, SituacaoPull.INEXISTENTE)


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    res = montar(erro_com_bytes).executar(Path(tmp))

checar("NÃO conclui 'Nenhum dado'", "Nenhum dado" not in res.mensagem)
checar("diz que a cópia é PARCIAL", "PARCIAL" in res.mensagem)
checar("informa os bytes obtidos", "2900000000" in res.mensagem.replace(".", ""))
checar("sucesso=True (dado foi obtido)", res.sucesso is True)
checar("ressalva copia_incompleta marcada", bool(res.detalhes.get("copia_incompleta")))

# ---------------------------------------------------------------------------
print("\n[2] Regressão: nada veio mesmo -> continua 'Nenhum dado', sucesso=False")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    res2 = montar(lambda c: pull(c, SituacaoPull.INEXISTENTE)).executar(Path(tmp))

checar("conclui 'Nenhum dado' quando nada veio", "Nenhum dado" in res2.mensagem)
checar("sucesso=False quando nada veio", res2.sucesso is False)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões): {', '.join(falhas)}")
    sys.exit(1)
print("Todas as verificações passaram.")
