"""
Testes do metodo declarado de uma aquisicao.

O que os modulos escolhidos alcancam e o que NAO alcancam e gravado dentro
da aquisicao, antes do selo, e nao montado na hora do laudo. A razao esta no
bloco [3]: a combinacao de modulos define o alcance daquele exame, e um
laudo emitido meses adiante -- com a ferramenta ja atualizada -- exibiria as
limitacoes da versao nova como se fossem as da coleta antiga.

O bloco [4] guarda a distincao mais delicada: o metodo declara o que a
execucao PODE alterar no aparelho, nunca que alterou. O que de fato ocorreu
e do registro do procedimento, anotado no momento em que ocorre. Confundir
as duas faria o caso afirmar que se mexeu no aparelho quando talvez nao se
tenha mexido.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

import core.android.extractors  # noqa: F401  (registra os extratores)
from core.base_extractor import BaseExtractor, Perfil, Plataforma, ResultadoExtracao
from core.hashing import conferir_manifesto, ler_manifesto, localizar_manifesto
from core.metodo import (
    NOME_METODO,
    NOME_METODO_DADOS,
    PASTA_METODO,
    descrever,
    gravar_metodo,
    ler_metodo,
)
from core.procedimento import RegistroProcedimento
from services.extraction_service import ExtractionService, descrever_metodo, listar_extratores

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


class ExtratorComLimite(BaseExtractor):
    id = "modulo_com_limite"
    nome_exibicao = "Modulo de Teste"
    plataforma = Plataforma.ANDROID
    perfil_minimo = Perfil.DES
    limitacoes_conhecidas = (
        "Nao alcanca a area privada dos aplicativos sem privilegio elevado.",
    )
    alteracoes_no_dispositivo = (
        ("Exibe pedido de confirmacao na tela do aparelho.", "Unica via disponivel."),
    )

    def disponivel(self):
        return True, ""

    def executar(self, pasta_caso):
        pasta = pasta_caso / "evidencia"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "arquivo.txt").write_text("dado extraido", encoding="utf-8")
        return ResultadoExtracao(True, "concluido", caminho_saida=pasta)


# ---------------------------------------------------------------------------
print("\n[1] A declaracao de cada modulo e lida como esta na classe")
# ---------------------------------------------------------------------------
metodo = descrever([ExtratorComLimite()])
checar("um modulo descrito", len(metodo.modulos) == 1)

modulo = metodo.modulos[0]
checar("o identificador vem junto", modulo.identificador == "modulo_com_limite")
checar("a limitacao e preservada", modulo.limitacoes == list(ExtratorComLimite.limitacoes_conhecidas))
checar("a alteracao vem em par", modulo.alteracoes == [("Exibe pedido de confirmacao na tela do aparelho.", "Unica via disponivel.")])
checar("o perfil vira texto legivel", modulo.perfil == Perfil.DES.value)
checar("o metodo sabe que ha limitacao", metodo.tem_limitacao)
checar("e que ha alteracao", metodo.tem_alteracao)


class ExtratorMudo(BaseExtractor):
    id = "modulo_mudo"
    nome_exibicao = "Modulo Sem Declaracao"
    plataforma = Plataforma.ANDROID

    def disponivel(self):
        return True, ""

    def executar(self, pasta_caso):
        return ResultadoExtracao(True, "concluido")


# Um modulo que ainda nao declarou nada nao pode derrubar uma extracao em
# andamento. A cobranca de que ele declare e da suite, nao do meio do exame.
mudo = descrever([ExtratorMudo()])
checar("modulo sem declaracao nao quebra a descricao", len(mudo.modulos) == 1)
checar("e entra com alcance em branco", not mudo.tem_limitacao and not mudo.tem_alteracao)
checar("com o perfil padrao", mudo.modulos[0].perfil == Perfil.DEFR.value)

# ---------------------------------------------------------------------------
print("\n[2] Grava e rele sem perder nada")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "CASO_001" / "android_20260823_120000"
    aquisicao.mkdir(parents=True)

    caminho = gravar_metodo(aquisicao, descrever([ExtratorComLimite()]))
    checar("o texto e gravado no lugar certo", caminho.parent.name == PASTA_METODO)
    checar("o texto existe", (aquisicao / PASTA_METODO / NOME_METODO).is_file())
    checar("e os dados tambem", (aquisicao / PASTA_METODO / NOME_METODO_DADOS).is_file())

    relido = ler_metodo(aquisicao)
    checar("um modulo relido", len(relido.modulos) == 1)
    checar("limitacao sobrevive a ida e volta", relido.modulos[0].limitacoes == modulo.limitacoes)
    checar("alteracao sobrevive como par", relido.modulos[0].alteracoes == modulo.alteracoes)
    checar("perfil sobrevive", relido.modulos[0].perfil == Perfil.DES.value)

    corpo = (aquisicao / PASTA_METODO / NOME_METODO).read_text(encoding="utf-8")
    checar("o texto nomeia o modulo", "Modulo de Teste" in corpo)
    checar("traz a limitacao por extenso", "area privada dos aplicativos" in corpo)
    checar("e a justificativa da alteracao", "Unica via disponivel" in corpo)

    checar("aquisicao sem registro devolve metodo vazio", ler_metodo(Path(temporario)).vazio)

    (aquisicao / PASTA_METODO / NOME_METODO_DADOS).write_text("{ nao e json", encoding="utf-8")
    checar("json ilegivel devolve vazio, sem estourar", ler_metodo(aquisicao).vazio)

# ---------------------------------------------------------------------------
print("\n[3] O metodo fica DENTRO do selo da aquisicao")
# ---------------------------------------------------------------------------
# E o ponto da gravacao: preso ao exame que ocorreu, e nao remontado depois
# a partir da versao atual da ferramenta.
with tempfile.TemporaryDirectory() as temporario:
    caso = Path(temporario) / "caso"
    caso.mkdir()
    RegistroProcedimento(caso).abrir("CASO_TESTE", "Android", "SERIAL_TESTE")

    ExtractionService([ExtratorComLimite()], caso).run()

    checar("a extracao gravou o metodo", (caso / PASTA_METODO / NOME_METODO).is_file())

    manifesto = ler_manifesto(localizar_manifesto(caso))
    nomes = " ".join(manifesto)
    checar("o texto do metodo esta no manifesto", NOME_METODO in nomes)
    checar("os dados do metodo tambem", NOME_METODO_DADOS in nomes)
    checar("e o caso confere integro", conferir_manifesto(caso).integro)

    relido = ler_metodo(caso)
    checar("o metodo relido do caso selado traz o modulo", len(relido.modulos) == 1)
    checar("com a limitacao declarada", relido.tem_limitacao)

# ---------------------------------------------------------------------------
print("\n[4] Declarar o que PODE alterar nao e afirmar que alterou")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    caso = Path(temporario) / "caso"
    caso.mkdir()
    RegistroProcedimento(caso).abrir("CASO_TESTE", "Android", "SERIAL_TESTE")
    ExtractionService([ExtratorComLimite()], caso).run()

    metodo_txt = (caso / PASTA_METODO / NOME_METODO).read_text(encoding="utf-8")
    checar("o metodo fala em PODE alterar", "Pode alterar no aparelho" in metodo_txt)
    checar(
        "e explica que a alteracao ocorrida esta no registro do procedimento",
        "registro_procedimento.txt" in metodo_txt,
    )

    # O modulo de teste nao registrou alteracao nenhuma; o diario nao pode
    # ter inventado uma so porque o metodo a declarou como possivel.
    diario = (caso / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar(
        "o diario NAO registra alteracao que nao ocorreu",
        "Exibe pedido de confirmacao" not in diario,
    )

# ---------------------------------------------------------------------------
print("\n[5] A interface recebe o metodo sem conhecer core")
# ---------------------------------------------------------------------------
reais = [c for c in listar_extratores("Android") if c.id in ("android_sms", "android_whatsapp")]
dados = descrever_metodo(reais)
checar("dois modulos descritos", len(dados) == 2)
checar("em campos simples", all(isinstance(d, dict) for d in dados))
checar("com nome legivel", all(d["nome"] for d in dados))
checar("e limitacoes em lista de strings", all(
    isinstance(d["limitacoes"], list) and all(isinstance(t, str) for t in d["limitacoes"])
    for d in dados
))
checar("alteracao vem como par de dois", all(
    len(par) == 2 for d in dados for par in d["alteracoes"]
))
checar("ao menos um dos dois declara alteracao", any(d["alteracoes"] for d in dados))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
