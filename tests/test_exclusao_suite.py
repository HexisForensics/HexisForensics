"""
Testes da exclusao da propria suite na varredura de computador.

Periciar a unidade onde o HexisForensics esta instalado fazia a copia
logica encontrar a pasta de saida dentro da arvore que varria e copiar de
volta para dentro de si o que acabara de gravar, ate travar ou encher o
disco. A protecao poda a lista de subpastas do os.walk em andamento.

O bloco [2] guarda o defeito que motivou este arquivo. A protecao subia um
nivel a partir do que recebia, supondo ser a pasta do caso -- mas o que os
extratores recebem e a pasta da AQUISICAO, um nivel abaixo. Um `.parent` so
parava no caso corrente e deixava os DEMAIS casos de fora da exclusao: a
aquisicao copiaria para dentro de si a evidencia de todos os casos
anteriores, e o manifesto a selaria como se fosse do disco periciado.

O defeito era silencioso duas vezes. `.parent` devolve uma pasta que existe
e parece plausivel, e na instalacao padrao a exclusao da raiz da suite
cobria `extracoes/` por tabela -- so aparecendo se a saida fosse
configurada fora da pasta de instalacao, que e exatamente o cenario para o
qual a segunda camada existe.
"""
import os
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao, raiz_das_extracoes
from core.computador.extractors.base import (
    podar_subpastas_ignoradas,
    raiz_instalacao_suite,
)
from core.computador.extractors.file_index import IndiceArquivosExtractor
from core.computador.extractors.logical_copy import CopiaLogicaExtractor

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
print("\n[1] A raiz das extracoes e alcancada a partir da aquisicao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / "extracoes"
    aquisicao = criar_pasta_aquisicao(raiz, "CASO_001", "Computador")

    checar("a pasta criada e a da aquisicao, nao a do caso",
           aquisicao.parent.name == "CASO_001")
    checar("da aquisicao sobe dois niveis ate a raiz",
           raiz_das_extracoes(aquisicao) == raiz.resolve())
    checar("da pasta do caso sobe um nivel ate a mesma raiz",
           raiz_das_extracoes(aquisicao.parent) == raiz.resolve())
    checar("o nome da aquisicao e reconhecido, nao contado",
           raiz_das_extracoes(aquisicao) != aquisicao.parent.resolve())

# ---------------------------------------------------------------------------
print("\n[2] Casos anteriores ficam fora da varredura")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / "extracoes"
    anterior = criar_pasta_aquisicao(raiz, "CASO_001", "Android")
    (anterior / "evidencia_do_caso_anterior.bin").write_bytes(b"\x00" * 16)
    atual = criar_pasta_aquisicao(raiz, "CASO_002", "Computador")

    ignoradas = IndiceArquivosExtractor().pastas_a_ignorar(atual)

    checar("a raiz das extracoes esta entre as ignoradas",
           raiz.resolve() in ignoradas)
    checar("copia logica e indice protegem a mesma coisa",
           CopiaLogicaExtractor().pastas_a_ignorar(atual) == ignoradas)
    checar("a raiz da suite tambem esta",
           raiz_instalacao_suite() in ignoradas)
    checar("nao para na pasta do caso corrente (o defeito)",
           atual.parent.resolve() not in ignoradas)

    # A varredura do disco encontra `extracoes/` e precisa nao descer nela.
    disco = Path(tmp)
    subpastas = [p.name for p in disco.iterdir() if p.is_dir()]
    excluidas = podar_subpastas_ignoradas(str(disco), subpastas, ignoradas)

    checar("a poda remove extracoes/ da lista do walk",
           "extracoes" not in subpastas)
    checar("e devolve o caminho excluido, para o log",
           [p.name for p in excluidas] == ["extracoes"])

    visitados = []
    for pasta_atual, subs, _arquivos in os.walk(disco):
        podar_subpastas_ignoradas(pasta_atual, subs, ignoradas)
        visitados.append(Path(pasta_atual))

    checar("o walk nunca visita a aquisicao anterior",
           anterior.resolve() not in [p.resolve() for p in visitados])
    checar("nem a aquisicao corrente, que cresce durante a copia",
           atual.resolve() not in [p.resolve() for p in visitados])

# ---------------------------------------------------------------------------
print("\n[3] A poda nao remove o que nao foi mandada remover")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    disco = Path(tmp)
    for nome in ("Documentos", "Imagens", "extracoes"):
        (disco / nome).mkdir()

    ignoradas = [(disco / "extracoes").resolve()]
    subpastas = ["Documentos", "Imagens", "extracoes"]
    excluidas = podar_subpastas_ignoradas(str(disco), subpastas, ignoradas)

    checar("as pastas do usuario permanecem",
           subpastas == ["Documentos", "Imagens"])
    checar("so a ignorada saiu", len(excluidas) == 1)

    subpastas = ["Documentos", "Imagens"]
    excluidas = podar_subpastas_ignoradas(str(disco), subpastas, ignoradas)
    checar("sem nada a excluir, a lista fica intacta",
           subpastas == ["Documentos", "Imagens"] and excluidas == [])

# ---------------------------------------------------------------------------
print("\n[4] A raiz da suite acompanha onde a suite esta")
# ---------------------------------------------------------------------------
checar("aponta para a raiz do projeto rodando do codigo-fonte",
       raiz_instalacao_suite() == RAIZ_PROJETO)
checar("e a pasta core/ esta dentro dela",
       (raiz_instalacao_suite() / "core" / "computador").is_dir())

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
