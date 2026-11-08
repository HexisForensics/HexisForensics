"""Executa todos os testes da suite e devolve codigo de saida agregado."""
import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent

arquivos = sorted(p for p in PASTA.glob("test_*.py"))
falharam = []

# Cada teste herda o isolamento com que a suíte foi chamada. Sem isso, o
# empacotador rodava a suíte com `-s -E` e cada teste, num processo novo,
# voltava a enxergar a pasta pessoal do Python: o `packaging` faltou no
# instalador 0.4.0 e a suíte passou mesmo assim (31/10/2026).
ISOLAMENTO = (["-s"] if sys.flags.no_user_site else []) + (
    ["-E"] if sys.flags.ignore_environment else [])

for arquivo in arquivos:
    print("\n" + "=" * 70)
    print(f"  {arquivo.name}")
    print("=" * 70)
    processo = subprocess.run([sys.executable, *ISOLAMENTO, str(arquivo)], cwd=str(RAIZ))
    if processo.returncode != 0:
        falharam.append(arquivo.name)

print("\n" + "=" * 70)
if falharam:
    print(f"RESULTADO: {len(falharam)} arquivo(s) com falha: {', '.join(falharam)}")
else:
    print(f"RESULTADO: {len(arquivos)} arquivo(s) de teste, todos passaram.")
print("=" * 70)
sys.exit(1 if falharam else 0)
