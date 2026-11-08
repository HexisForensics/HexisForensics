"""
O navegador de material: só leitura, conferência contra o lacre, prévias
e banco aberto sobre cópia. Navegar não pode alterar a aquisição.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import gerar_manifesto  # noqa: E402
from services.material_service import Material  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def estado(pasta: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in pasta.rglob("*")}


with tempfile.TemporaryDirectory() as temporario:
    aq = Path(temporario) / "CASO" / "android_20261024_100000"
    (aq / "sms").mkdir(parents=True)
    (aq / "sms" / "sms_todas.txt").write_text("Row: 0 body=ola\n", encoding="utf-8")
    (aq / "planilha.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    (aq / "binario.bin").write_bytes(b"\x00\x01\x02ABC" * 10)
    banco = aq / "dados.db"
    conexao = sqlite3.connect(banco)
    conexao.execute("CREATE TABLE mensagens (id INTEGER)")
    conexao.executemany("INSERT INTO mensagens VALUES (?)", [(1,), (2,), (3,)])
    conexao.commit()
    conexao.close()
    gerar_manifesto(aq)
    antes = estado(aq)

    m = Material(aq)
    print("\n[1] Lista, busca e conferência")
    nomes = [e.nome for e in m.listar()]
    checar("pastas primeiro, depois arquivos", nomes[0] == "sms" and "dados.db" in nomes)
    checar("abre uma subpasta", [e.relativo for e in m.listar("sms")] == ["sms/sms_todas.txt"])
    achados, cortado = m.buscar("SMS_")
    checar("busca pelo nome, sem diferenciar maiúsculas", [e.relativo for e in achados]
           == ["sms/sms_todas.txt"] and not cortado)
    checar("arquivo selado confere", m.conferir("sms/sms_todas.txt").situacao == "confere")
    try:
        m.listar("../..")
        fora = False
    except ValueError:
        fora = True
    checar("não sai da pasta da aquisição", fora)

    print("\n[2] Prévias")
    checar("texto", m.previa_texto("sms/sms_todas.txt")[0].startswith("Row: 0"))
    cabecalho, linhas, _ = m.previa_planilha("planilha.csv")
    checar("planilha em tabela", cabecalho == ["a", "b"] and linhas == [["1", "2"], ["3", "4"]])
    checar("binário vira hexadecimal, dito como tal",
           m.tipo_de_previa("binario.bin") == "binario"
           and "hexadecimal" in m.previa_hex("binario.bin"))
    tabelas, motivo = m.previa_banco("dados.db")
    checar("banco: tabelas e quantidades, lidas sobre cópia",
           tabelas == [("mensagens", 3)] and not motivo)

    print("\n[3] Navegar não altera nada")
    checar("nenhum arquivo criado, removido ou modificado", estado(aq) == antes)

    (aq / "sms" / "sms_todas.txt").write_text("adulterado\n", encoding="utf-8")
    checar("alteração posterior é acusada: DIVERGE",
           Material(aq).conferir("sms/sms_todas.txt").situacao == "DIVERGE")

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
