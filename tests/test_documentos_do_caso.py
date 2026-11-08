"""
Os documentos de um caso, listados e entregues pela própria ferramenta.

A lista diz o que é cada documento e de qual aquisição veio; a cópia para
entrega só é dada como feita se for idêntica ao original pelo SHA-256.
"""

import sys
import tempfile
import time
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import calcular_sha256  # noqa: E402
from services import documentos_service  # noqa: E402
from services.documentos_service import listar_documentos, salvar_copia  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


with tempfile.TemporaryDirectory() as temporario:
    caso = Path(temporario) / "CASO_X"
    (caso / "documentos").mkdir(parents=True)
    (caso / "relatorios" / "android_20261024_100000_20261024_101500").mkdir(parents=True)
    laudo = caso / "documentos" / "Laudo_Pericial_android_20261024_100000.pdf"
    laudo.write_bytes(b"%PDF-1.4 laudo")
    time.sleep(0.05)
    (caso / "documentos" / "Relatorio_de_Extracao_ios_20261024_110000.pdf").write_bytes(b"%PDF-1.4 rel")
    conteudo = caso / "relatorios" / "android_20261024_100000_20261024_101500" / "Relatorio_de_Conteudo.pdf"
    conteudo.write_bytes(b"%PDF-1.4 conteudo")
    (caso / "documentos" / "anotacao.txt").write_text("nao e pdf", encoding="utf-8")

    print("\n[1] A lista diz o que é cada documento e de onde veio")
    todos = listar_documentos(caso)
    checar("só PDFs, de documentos/ e de relatorios/", len(todos) == 3)
    checar("do mais recente para o mais antigo",
           [d.gerado_em for d in todos] == sorted((d.gerado_em for d in todos), reverse=True))
    por_nome = {d.caminho.name: d for d in todos}
    checar("o tipo vem do nome",
           por_nome[laudo.name].tipo == "Laudo Pericial"
           and por_nome[conteudo.name].tipo == "Relatório de Conteúdo")
    checar("a aquisição vem do nome do arquivo ou da pasta do relatório",
           por_nome[laudo.name].aquisicao == "android_20261024_100000"
           and por_nome[conteudo.name].aquisicao == "android_20261024_100000")
    so_android = listar_documentos(caso, "android_20261024_100000")
    checar("filtrar por aquisição deixa só os dela", {d.caminho.name for d in so_android}
           == {laudo.name, conteudo.name})

    print("\n[2] A cópia para entrega é conferida pelo hash")
    destino = Path(temporario) / "entrega" / "laudo.pdf"
    destino.parent.mkdir()
    resumo = salvar_copia(laudo, destino)
    checar("copia e devolve o SHA-256, igual ao do original",
           resumo == calcular_sha256(laudo) == calcular_sha256(destino))
    try:
        salvar_copia(laudo, laudo)
        recusou = False
    except OSError:
        recusou = True
    checar("copiar sobre o próprio original é recusado", recusou)

    original = documentos_service.calcular_sha256
    chamadas = iter(["aaaa", "bbbb"])
    documentos_service.calcular_sha256 = lambda _caminho: next(chamadas)
    try:
        salvar_copia(laudo, Path(temporario) / "entrega" / "outra.pdf")
        detectou = False
    except OSError as erro:
        detectou = "NÃO é idêntica" in str(erro)
    documentos_service.calcular_sha256 = original
    checar("cópia diferente do original é falha, nunca 'salvo'", detectou)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
