"""
Testes da conferencia de integridade -- a operacao que faltava.

Gerar um hash prova pouco: o que sustenta a cadeia de custodia e poder
demonstrar, depois, que o material nao mudou entre a coleta e o exame. Ate
aqui a suite selava e nunca conferia, e o manifesto era uma afirmacao que
ninguem jamais testava.

O teste de ponta a ponta ao final cobre um defeito real encontrado assim que
a conferencia passou a existir: TODO caso produzido pela ferramenta falhava
na propria verificacao, acusando 'extracao.log' e 'registro_procedimento.txt'
como alterados -- porque o manifesto era gerado ANTES de esses arquivos
receberem suas ultimas linhas.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.base_extractor import BaseExtractor, Plataforma, ResultadoExtracao
from core.hashing import (
    NOME_MANIFESTO,
    conferir_manifesto,
    gerar_manifesto,
    ler_manifesto,
    listar_manifestos,
    localizar_manifesto,
)
from core.procedimento import RegistroProcedimento
from services.extraction_service import ExtractionService

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar_pasta(destino: Path) -> None:
    (destino / "sub").mkdir(parents=True, exist_ok=True)
    (destino / "a.txt").write_text("conteudo A", encoding="utf-8")
    (destino / "sub" / "b.txt").write_text("conteudo B", encoding="utf-8")


# ---------------------------------------------------------------------------
print("\n[1] Leitura do manifesto")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    montar_pasta(pasta)
    caminho = gerar_manifesto(pasta)

    hashes = ler_manifesto(caminho)
    checar("o manifesto e lido de volta", len(hashes) == 2)
    checar("os caminhos sao relativos", "a.txt" in hashes and "sub/b.txt" in hashes)
    checar("os valores sao SHA-256", all(len(v) == 64 for v in hashes.values()))
    checar("o cabecalho nao vira entrada", not any("MANIFESTO" in k for k in hashes))
    checar("o manifesto e localizavel", localizar_manifesto(pasta) == caminho)

with tempfile.TemporaryDirectory() as td:
    checar("pasta sem manifesto devolve None", localizar_manifesto(Path(td)) is None)

# ---------------------------------------------------------------------------
print("\n[2] Conferencia: as quatro situacoes")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    montar_pasta(pasta)
    gerar_manifesto(pasta)

    resultado = conferir_manifesto(pasta)
    checar("material intocado e declarado integro", resultado.integro is True)
    checar("todos os arquivos constam como intactos", len(resultado.intactos) == 2)
    checar("o resumo diz INTEGRO", "ÍNTEGRO" in resultado.resumo)

    relatorios = list(pasta.glob("conferencia_integridade_*.txt"))
    checar("o relatorio da conferencia e gravado", len(relatorios) == 1)

with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    montar_pasta(pasta)
    gerar_manifesto(pasta)

    (pasta / "a.txt").write_text("CONTEUDO ADULTERADO", encoding="utf-8")
    (pasta / "sub" / "b.txt").unlink()
    (pasta / "intruso.txt").write_text("entrou depois do selo", encoding="utf-8")

    resultado = conferir_manifesto(pasta)
    checar("arquivo alterado e identificado", resultado.alterados == ["a.txt"])
    checar("arquivo ausente e identificado", resultado.ausentes == ["sub/b.txt"])
    checar("arquivo acrescentado e identificado", resultado.acrescentados == ["intruso.txt"])
    checar("nada disso passa por integro", resultado.integro is False)
    checar("o resumo anuncia DIVERGENCIAS", "DIVERGÊNCIAS" in resultado.resumo)

    relatorio = next(pasta.glob("conferencia_integridade_*.txt")).read_text(encoding="utf-8")
    checar("o relatorio nomeia o alterado", "a.txt" in relatorio)
    checar("o relatorio explica o que significa alterado", "MUDOU após o manifesto" in relatorio)
    checar("o relatorio separa o acrescentado", "ACRESCENTADOS" in relatorio)

with tempfile.TemporaryDirectory() as td:
    resultado = conferir_manifesto(Path(td))
    checar("pasta sem manifesto nao e declarada integra", resultado.integro is False)
    checar("e o motivo e explicito", "não há manifesto" in resultado.erro)

# ---------------------------------------------------------------------------
print("\n[3] Gerar nunca destroi o selo anterior")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    montar_pasta(pasta)

    primeiro = gerar_manifesto(pasta)
    conteudo_original = primeiro.read_text(encoding="utf-8")

    # Cenario critico: alguem altera um arquivo e manda "gerar" de novo,
    # achando que reforca a cadeia de custodia. O selo original NAO pode ser
    # destruido -- e ele que prova a alteracao.
    (pasta / "a.txt").write_text("ADULTERADO", encoding="utf-8")
    segundo = gerar_manifesto(pasta)

    checar("o novo manifesto tem outro nome", segundo != primeiro)
    checar("o manifesto original continua existindo", primeiro.exists())
    checar(
        "e seu conteudo permanece intacto",
        primeiro.read_text(encoding="utf-8") == conteudo_original,
    )
    checar("o selo VIGENTE passa a ser o mais recente", localizar_manifesto(pasta) == segundo)
    checar("os dois selos ficam registrados", listar_manifestos(pasta) == [primeiro, segundo])

    # Cadeia de selos: o manifesto novo cobre o anterior, de modo que apagar
    # ou adulterar o selo original tambem seria detectavel.
    checar(
        "o selo novo cobre o selo anterior",
        NOME_MANIFESTO in ler_manifesto(segundo),
    )
    checar(
        "mas nao contem o proprio hash",
        segundo.name not in ler_manifesto(segundo),
    )

    resultado = conferir_manifesto(pasta)
    checar(
        "a alteracao continua detectavel apos a segunda geracao",
        resultado.alterados_desde_o_original == ["a.txt"],
    )
    checar("e o caso NAO e declarado integro", resultado.integro is False)
    checar("o resumo aponta o selo original", "SELO ORIGINAL" in resultado.resumo)

    relatorio = sorted(pasta.glob("conferencia_integridade_*.txt"))[-1].read_text(encoding="utf-8")
    checar("o relatorio explica o que isso significa", "regerado em seguida" in relatorio)
    checar("e lista os selos da pasta", "Selos da pasta" in relatorio)

with tempfile.TemporaryDirectory() as td:
    pasta = Path(td)
    montar_pasta(pasta)
    gerar_manifesto(pasta)
    conferir_manifesto(pasta)
    conferir_manifesto(pasta)
    checar(
        "conferencias sucessivas nao se sobrescrevem",
        len(list(pasta.glob("conferencia_integridade_*.txt"))) == 2,
    )

# ---------------------------------------------------------------------------
print("\n[4] Um caso produzido pela suite passa na propria conferencia")
# ---------------------------------------------------------------------------
class ExtratorFalso(BaseExtractor):
    id = "modulo_de_teste"
    nome_exibicao = "Modulo de Teste"
    plataforma = Plataforma.ANDROID

    def disponivel(self):
        return True, ""

    def executar(self, pasta_caso):
        pasta = pasta_caso / "evidencia"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "arquivo.txt").write_text("dado extraido do aparelho", encoding="utf-8")
        self.log("[*] modulo executou e gravou evidencia")
        return ResultadoExtracao(True, "concluido", caminho_saida=pasta)


with tempfile.TemporaryDirectory() as td:
    caso = Path(td) / "caso"
    caso.mkdir()
    RegistroProcedimento(caso).abrir("CASO_TESTE", "Android", "SERIAL_TESTE")

    ExtractionService([ExtratorFalso()], caso).run()

    checar("o manifesto e gerado automaticamente", (caso / NOME_MANIFESTO).exists())
    checar("o log da extracao existe", (caso / "extracao.log").exists())
    checar("o registro do procedimento existe", (caso / "registro_procedimento.txt").exists())

    resultado = conferir_manifesto(caso)
    checar("o caso passa na propria conferencia de integridade", resultado.integro is True)
    checar("o log NAO aparece como alterado", "extracao.log" not in resultado.alterados)
    checar(
        "o registro do procedimento NAO aparece como alterado",
        "registro_procedimento.txt" not in resultado.alterados,
    )
    checar("nada aparece como acrescentado apos o selo", resultado.acrescentados == [])

    conteudo = (caso / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o encerramento consta do registro, ANTES do selo", "ENCERRAMENTO" in conteudo)

# ---------------------------------------------------------------------------
print("\n[5] Quem escreve no fim da aquisicao escreve ANTES do selo")
# ---------------------------------------------------------------------------
# Defeito real: a conferencia do aparelho rodava na interface, DEPOIS que o
# servico havia selado o caso, e gravava uma decisao no
# registro_procedimento.txt. Resultado: todo caso extraido pela interface
# acusava esse arquivo como alterado -- e o teste anterior nao pegava,
# porque chamava o servico direto, sem passar pela UI.
with tempfile.TemporaryDirectory() as td:
    caso = Path(td) / "caso"
    caso.mkdir()
    RegistroProcedimento(caso).abrir("CASO_TESTE", "Android", "SERIAL_TESTE")

    def finalizar_escrevendo_no_caso():
        """Reproduz o que a interface faz: anota uma decisao no encerramento."""
        RegistroProcedimento(caso).registrar_decisao(
            "Conferência do aparelho no encerramento da aquisição.",
            "Aparelho 'SERIAL_TESTE' confirmado ao final.",
        )
        return "Aparelho 'SERIAL_TESTE' confirmado ao final."

    servico = ExtractionService(
        [ExtratorFalso()], caso, ao_finalizar=finalizar_escrevendo_no_caso
    )
    servico.run()

    conteudo = (caso / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("a anotacao final chegou ao registro", "Conferência do aparelho" in conteudo)

    resultado = conferir_manifesto(caso)
    checar(
        "e o caso CONTINUA integro apesar dela",
        resultado.integro is True,
    )
    checar(
        "o registro do procedimento nao aparece como alterado",
        "registro_procedimento.txt" not in resultado.alterados,
    )

    posicao_decisao = conteudo.index("Conferência do aparelho")
    posicao_encerramento = conteudo.index("ENCERRAMENTO")
    checar(
        "a conferencia do aparelho precede o encerramento no registro",
        posicao_decisao < posicao_encerramento,
    )

with tempfile.TemporaryDirectory() as td:
    caso = Path(td) / "caso"
    caso.mkdir()

    def finalizador_que_falha():
        raise RuntimeError("aparelho desconectou")

    servico = ExtractionService([ExtratorFalso()], caso, ao_finalizar=finalizador_que_falha)
    servico.run()

    checar(
        "falha no finalizador nao impede o selo do caso",
        (caso / NOME_MANIFESTO).exists(),
    )
    checar("e o caso segue integro", conferir_manifesto(caso).integro is True)

# ---------------------------------------------------------------------------
print("\n[6] Selar o caso cobre tambem o selo de cada aquisicao")
# ---------------------------------------------------------------------------
# A regra de exclusao original mantinha QUALQUER manifesto fora do hash, em
# qualquer nivel. Consequencia: o selo do caso nao cobria o selo das
# aquisicoes, e adulterar o manifesto de uma coleta passaria despercebido
# pela conferencia do caso.
with tempfile.TemporaryDirectory() as td:
    raiz = Path(td)
    aquisicao = raiz / "CASO_001" / "android_20260822_183237"
    (aquisicao / "evidencia").mkdir(parents=True)
    (aquisicao / "evidencia" / "foto.jpg").write_text("dado", encoding="utf-8")

    manifesto_da_aquisicao = gerar_manifesto(aquisicao)
    caso = raiz / "CASO_001"
    entradas = ler_manifesto(gerar_manifesto(caso))

    checar(
        "o selo do caso cobre o manifesto da aquisicao",
        any(nome.endswith("manifesto_hashes.txt") for nome in entradas),
    )
    checar(
        "e cobre a evidencia da aquisicao",
        any(nome.endswith("foto.jpg") for nome in entradas),
    )
    checar("o caso, intocado, esta integro", conferir_manifesto(caso).integro is True)

    # Conferir a aquisicao grava um relatorio DENTRO dela. Isso nao pode
    # quebrar o selo do caso, ou cada conferencia invalidaria a seguinte.
    conferir_manifesto(aquisicao)
    checar(
        "conferir a aquisicao nao quebra o selo do caso",
        conferir_manifesto(caso).integro is True,
    )

    manifesto_da_aquisicao.write_text("SELO ADULTERADO", encoding="utf-8")
    resultado = conferir_manifesto(caso)
    checar("adulterar o selo da aquisicao e detectado pelo caso", resultado.integro is False)
    checar(
        "e o arquivo apontado e o manifesto da aquisicao",
        any(nome.endswith("manifesto_hashes.txt") for nome in resultado.alterados),
    )

# ---------------------------------------------------------------------------
print("\n[7] Complemento juntado depois nao quebra o selo da aquisicao")
# ---------------------------------------------------------------------------
# A rotina exige juntar informacao depois: a referencia do processo so
# e conhecida mais tarde, a autorizacao pode ser digitalizada dias depois, e o
# titular de um aparelho subtraido pode ser identificado a partir do proprio
# exame. Nada disso pode obrigar a reescrever a aquisicao ja selada.
from services.case_service import CaseService

with tempfile.TemporaryDirectory() as td:
    servico = CaseService(Path(td))
    aquisicao = servico.abrir_caso("Android", "CASO_010", "SERIAL")
    (aquisicao / "evidencia.txt").write_text("dado extraido", encoding="utf-8")
    gerar_manifesto(aquisicao)

    caso = aquisicao.parent
    gerar_manifesto(caso)
    checar("o caso comeca integro", conferir_manifesto(caso).integro is True)

    complemento = servico.juntar_complemento(
        caso, "Referência nos autos", "Termo juntado às fls. 145/147 do processo 123/2026."
    )

    checar("o complemento e gravado no nivel do CASO", complemento.parent.parent == caso)
    checar("a aquisicao NAO foi tocada", conferir_manifesto(aquisicao).integro is True)
    checar("e o caso segue integro apos o reselo", conferir_manifesto(caso).integro is True)
    checar("o caso passa a ter dois selos", len(listar_manifestos(caso)) == 2)

    conteudo = complemento.read_text(encoding="utf-8")
    checar("o complemento traz o assunto", "Referência nos autos" in conteudo)
    checar("e o texto informado", "fls. 145/147" in conteudo)
    checar(
        "e declara que nao altera o que ja foi selado",
        "NÃO altera as aquisições já seladas" in conteudo,
    )

    indice = (caso / "complementos" / "INDICE.txt").read_text(encoding="utf-8")
    checar("o indice de complementos registra a juntada", "Referência nos autos" in indice)

    servico.juntar_complemento(caso, "Retificação", "Onde se lê X, leia-se Y.")
    checar("varias juntadas convivem", len(list((caso / "complementos").glob("*.txt"))) == 3)
    checar("e o caso continua integro", conferir_manifesto(caso).integro is True)

# ---------------------------------------------------------------------------
print("\n[8] O indice de complementos nao entra no selo")
# ---------------------------------------------------------------------------
# Regressao real, e alcancavel pelo fluxo normal: a extracao sela a AQUISICAO,
# nao o caso. Entao o primeiro selo do CASO costuma nascer no primeiro
# complemento -- ja contendo o INDICE.txt. Como o indice cresce a cada
# juntada, a segunda juntada legitima o fazia divergir do selo original, e o
# caso ficava permanentemente inconferivel por ter recebido informacao nova.
with tempfile.TemporaryDirectory() as td:
    servico = CaseService(Path(td))
    aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    (aquisicao / "dado.txt").write_text("evidencia", encoding="utf-8")
    gerar_manifesto(aquisicao)
    caso = aquisicao.parent
    checar("o caso ainda nao tem selo proprio", localizar_manifesto(caso) is None)

    servico.juntar_complemento(caso, "Referência nos autos", "fls. 145/147")
    checar("o primeiro complemento sela o caso", localizar_manifesto(caso) is not None)
    checar("e o caso esta integro", conferir_manifesto(caso).integro is True)

    servico.juntar_complemento(caso, "Retificação", "Onde se lê X, leia-se Y.")
    resultado = conferir_manifesto(caso)
    checar("a segunda juntada NAO quebra o selo original", resultado.integro is True)
    checar(
        "e o indice nao aparece como alterado",
        not any("INDICE" in nome for nome in resultado.alterados_desde_o_original),
    )

    manifesto = ler_manifesto(localizar_manifesto(caso))
    checar(
        "o indice nao consta do manifesto",
        not any("INDICE.txt" in nome for nome in manifesto),
    )
    checar(
        "mas os complementos constam, que e o que precisa ser selado",
        sum("complementos/" in nome for nome in manifesto) == 2,
    )

    # O indice fica de fora por ser derivado -- nao por ser dispensavel.
    # Mexer num complemento continua sendo detectado.
    complementos = sorted(
        c for c in (caso / "complementos").glob("*.txt") if c.name != "INDICE.txt"
    )
    complementos[0].write_text("adulterado", encoding="utf-8")
    checar(
        "adulterar um complemento continua sendo detectado",
        conferir_manifesto(caso).integro is False,
    )

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
