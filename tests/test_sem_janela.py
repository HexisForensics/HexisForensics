"""
Todo comando do ADB roda sem abrir janela de console.

Aberta pelo ícone (sem console), a suíte fazia o Windows abrir uma janela
preta por comando: piscavam ao fundo, a do bugreport cobria a suíte, e
fechá-la matava a coleta no meio.
"""

import subprocess
import sys
from pathlib import Path
from unittest import mock

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android import adb_client  # noqa: E402
from core.android.adb_client import SEM_JANELA, ADBClient  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


if sys.platform == "win32":
    checar("a opção é a do Windows para não criar console",
           SEM_JANELA == subprocess.CREATE_NO_WINDOW)

chamadas = []


def falso_run(*args, **kwargs):
    chamadas.append(kwargs)
    return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")


with mock.patch.object(adb_client.subprocess, "run", side_effect=falso_run):
    ADBClient(caminho_binario=Path("adb.exe")).executar_detalhado(["version"])
checar("executar_detalhado passa a opção sem janela",
       chamadas and chamadas[-1].get("creationflags") == SEM_JANELA)

fonte = Path(adb_client.__file__).read_text(encoding="utf-8")
lancamentos = fonte.count("subprocess.run(") + fonte.count("subprocess.Popen(")
checar(f"todos os {lancamentos} lançamentos de processo levam a opção",
       fonte.count("creationflags=SEM_JANELA") == lancamentos)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificacao(oes):")
    sys.exit(1)
print("Todas as verificacoes passaram.")
