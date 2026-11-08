"""
Inventário do `/sdcard`, que é link simbólico.

Defeito travado aqui (07/11/2026, visto num emulador Android 13): o
inventário preferido usa `find`, e `find /sdcard` SEM barra final não entra
no link — devolvia 0 arquivo(s). Com o inventário vazio não há lista de
faltantes, a recuperação um a um nunca dispara e a completude da cópia
deixa de ser conferível. Não é defeito de aparelho antigo: aparece em
qualquer Android cujo `/sdcard` seja link.

Duas garantias:
  1. o `find` do inventário pede o caminho COM barra final (segue o link),
     recuando para a forma sem barra caso o alvo seja um arquivo;
  2. a saída com barras repetidas (`/sdcard//DCIM/…`, que o toybox imprime
     quando se passa a barra) é relativizada corretamente, sem "/" na frente.
"""
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando  # noqa: E402
from core.android.extractors.filesystem_dump import FilesystemDumpExtractor  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


class ADBComLink:
    """
    ADB falso que imita um `/sdcard` link: só responde ao `find` quando ele
    vem COM barra final, e aí imprime caminhos com barra dupla (como o
    toybox). Sem a barra, devolve vazio — o comportamento que zerava o
    inventário.
    """

    def __init__(self):
        self.linhas_find = []
        self._arquivos = ["DCIM/Camera/a.jpg", "Download/b.pdf", "c.txt"]

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        linha = " ".join(argumentos)
        self.linhas_find.append(linha)
        # Primeiro alvo entre aspas simples.
        alvo = linha.split("'")[1] if "'" in linha else ""
        if alvo.endswith("/"):
            raiz = alvo.rstrip("/")
            # Barra dupla de propósito: é o que o toybox imprime.
            saida = "\n".join(f"{raiz}//{rel}" for rel in self._arquivos)
            return ResultadoComando(0, saida, "")
        # Sem barra, o link não é seguido: inventário vazio.
        return ResultadoComando(0, "", "")


def montar():
    extrator = FilesystemDumpExtractor.__new__(FilesystemDumpExtractor)
    extrator._log_callback = lambda mensagem: None
    extrator._progress_callback = lambda percentual: None
    extrator._cancelado = False
    extrator.adb = ADBComLink()
    return extrator


print("\n[1] `find` do inventário segue o link (pede o caminho com barra)")
extrator = montar()
inventario = extrator._inventariar_por_find("/sdcard")
primeira = extrator.adb.linhas_find[0]
checar("o find foi emitido com a barra final ('/sdcard/')", "'/sdcard/'" in primeira)
checar("há um recuo sem barra para o caso de arquivo ('|| find')", "|| find" in primeira)

print("\n[2] inventário do link não vem vazio")
checar("3 arquivos inventariados (não 0)", len(inventario.arquivos) == 3)
checar("método é 'find'", inventario.metodo == "find")
checar("não ficou indisponível", not inventario.motivo_indisponivel)

print("\n[3] barras duplas relativizadas sem '/' na frente")
checar("caminhos relativos corretos",
       sorted(inventario.arquivos) == ["DCIM/Camera/a.jpg", "Download/b.pdf", "c.txt"])
checar("nenhum relativo começa com '/'",
       all(not a.startswith("/") for a in inventario.arquivos))

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões): {', '.join(falhas)}")
    sys.exit(1)
print("Todas as verificações passaram.")
