"""
Testes da autorizacao de acesso aos dados.

O que esta ferramenta faz com o documento que autoriza a extracao e
deliberadamente estreito: guarda uma copia dentro do caso, calcula o
SHA-256 dessa copia e prende esse hash ao selo da aquisicao. Ela nao le o
PDF, nao confere assinatura e nao interpreta datas -- e por isso nao afirma
nada disso.

Dai as duas regras de nivel que estes testes exercitam:

- A AUTORIZACAO pertence ao caso. Uma decisao cobre todos os aparelhos da
  mesma operacao, inclusive quando a busca alcanca mais de um endereco.
- O HASH DO DIA pertence a aquisicao. Cada coleta registra quais documentos
  estavam a vista naquele momento; documento juntado depois nao retroage.

O caso mais perigoso e o terceiro bloco: sem documento anexado, o caso tem
de DECLARAR a ausencia por extenso. Ausencia silenciosa e indistinguivel de
esquecimento.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.fundamento import (
    NOME_AUTORIZACAO,
    NOME_FUNDAMENTO,
    PASTA_AUTORIZACAO,
    PASTA_FUNDAMENTO,
    TipoDocumento,
    anexar_documento,
    gravar_autorizacao,
    gravar_autorizacao_da_aquisicao,
    ler_autorizacao,
    ler_autorizacao_da_aquisicao,
)
from core.hashing import (
    calcular_sha256,
    conferir_manifesto,
    gerar_manifesto,
    ler_manifesto,
    localizar_manifesto,
)
from services.case_service import CaseService, opcoes_tipo_documento

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def escrever_pdf(pasta, nome, conteudo=b"%PDF-1.4 decisao judicial"):
    caminho = Path(pasta) / nome
    caminho.write_bytes(conteudo)
    return caminho


def texto_do_caso(pasta_caso):
    return (Path(pasta_caso) / PASTA_FUNDAMENTO / NOME_FUNDAMENTO).read_text(
        encoding="utf-8"
    )


def texto_da_aquisicao(pasta_aquisicao):
    return (Path(pasta_aquisicao) / PASTA_AUTORIZACAO / NOME_AUTORIZACAO).read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
print("\n[1] Anexar documento: copia dentro do caso, hash da copia")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    pasta_caso = raiz / "CASO_001"
    pasta_caso.mkdir()
    origem = escrever_pdf(raiz, "decisao.pdf")

    documento = anexar_documento(pasta_caso, TipoDocumento.DECISAO_JUDICIAL, origem)
    copia = pasta_caso / PASTA_FUNDAMENTO / "decisao.pdf"

    checar("o documento e copiado para dentro do caso", copia.is_file())
    checar("o original permanece onde estava", origem.is_file())
    checar("o registro aponta para a copia, nao para o original", documento.arquivo == copia)
    checar("o hash e o do arquivo", documento.sha256 == calcular_sha256(origem))
    checar("o hash tem 64 hexadigitos", len(documento.sha256) == 64)
    checar("a data da juntada e registrada", bool(documento.juntado_em))

    # Copiar em vez de referenciar existe porque um caminho externo pode ser
    # movido ou apagado, e ponteiro quebrado nao demonstra nada.
    origem.unlink()
    checar("apagar o original nao afeta a copia do caso", copia.is_file())

    relido = ler_autorizacao(pasta_caso)
    checar("a autorizacao relida traz um documento", len(relido.documentos) == 1)
    checar("o tipo sobrevive a ida e volta", relido.documentos[0].tipo is TipoDocumento.DECISAO_JUDICIAL)
    checar("o hash sobrevive a ida e volta", relido.documentos[0].sha256 == documento.sha256)

    corpo = texto_do_caso(pasta_caso)
    checar("o texto do caso lista o arquivo", "decisao.pdf" in corpo)
    checar("o texto do caso traz o SHA-256", documento.sha256 in corpo)
    checar("o texto do caso declara o alcance do registro", "ALCANCE DESTE REGISTRO" in corpo)
    checar("o texto do caso NAO afirma autenticidade", "não atesta autenticidade" in corpo)

# ---------------------------------------------------------------------------
print("\n[2] Um mesmo documento nao entra duas vezes")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    pasta_caso = raiz / "CASO_001"
    pasta_caso.mkdir()
    origem = escrever_pdf(raiz, "decisao.pdf")

    anexar_documento(pasta_caso, TipoDocumento.DECISAO_JUDICIAL, origem)

    # Mesmo conteudo, outro nome: continua sendo o mesmo documento, e anexar
    # de novo faria o relatorio sugerir duas autorizacoes onde ha uma.
    igual = escrever_pdf(raiz, "decisao_copia.pdf")
    recusou = False
    try:
        anexar_documento(pasta_caso, TipoDocumento.DECISAO_JUDICIAL, igual)
    except ValueError:
        recusou = True
    checar("conteudo ja anexado e recusado, mesmo com outro nome", recusou)
    checar("o caso continua com um unico documento", len(ler_autorizacao(pasta_caso).documentos) == 1)

    # Mesmo nome, conteudo diferente: sao dois documentos, e um nao pode
    # sobrescrever o outro em silencio.
    outra_pasta = raiz / "outra"
    outra_pasta.mkdir()
    homonimo = escrever_pdf(outra_pasta, "decisao.pdf", b"%PDF-1.4 aditamento")
    segundo = anexar_documento(pasta_caso, TipoDocumento.OUTRO, homonimo, "aditamento")

    checar("homonimo com outro conteudo e anexado", len(ler_autorizacao(pasta_caso).documentos) == 2)
    checar("o homonimo NAO sobrescreveu o primeiro", segundo.arquivo.name != "decisao.pdf")
    checar(
        "os dois arquivos convivem no caso",
        len(list((pasta_caso / PASTA_FUNDAMENTO).glob("*.pdf"))) == 2,
    )
    checar("a descricao livre entra no rotulo", "aditamento" in segundo.rotulo)

    inexistente = False
    try:
        anexar_documento(pasta_caso, TipoDocumento.DECISAO_JUDICIAL, raiz / "nao_existe.pdf")
    except ValueError:
        inexistente = True
    checar("arquivo inexistente e recusado", inexistente)

# ---------------------------------------------------------------------------
print("\n[3] Sem documento: a ausencia e declarada, nao silenciada")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial123")

    resumo = servico.registrar_autorizacao(pasta_aquisicao, [])

    caminho_caso = pasta_aquisicao.parent / PASTA_FUNDAMENTO / NOME_FUNDAMENTO
    caminho_aquisicao = pasta_aquisicao / PASTA_AUTORIZACAO / NOME_AUTORIZACAO

    checar("o arquivo do caso e escrito mesmo sem documento", caminho_caso.is_file())
    checar("o arquivo da aquisicao e escrito mesmo sem documento", caminho_aquisicao.is_file())
    checar("o resumo diz que nada foi anexado", "nenhum documento" in resumo.lower())

    corpo_caso = texto_do_caso(pasta_aquisicao.parent)
    checar("o caso declara a ausencia em destaque", "[NENHUM DOCUMENTO ANEXADO]" in corpo_caso)
    checar(
        "o caso esclarece que a ausencia nao nega a autorizacao",
        "NÃO afirma que a autorização inexista" in corpo_caso,
    )

    corpo_aquisicao = texto_da_aquisicao(pasta_aquisicao)
    checar(
        "a aquisicao avisa que documento posterior nao retroage",
        "DEPOIS desta data" in corpo_aquisicao,
    )

    # O bloco de alcance falava em "os arquivos acima" mesmo sem arquivo
    # nenhum -- descrevia uma lista inexistente. Registro que menciona o que
    # nao esta ali e da mesma familia do defeito que este modulo evita.
    for onde, corpo in (("caso", corpo_caso), ("aquisicao", corpo_aquisicao)):
        checar(
            f"o alcance do {onde} NAO fala em arquivos acima quando nao ha nenhum",
            "arquivos acima" not in corpo,
        )
        checar(
            f"e o alcance do {onde} nomeia a propria ausencia",
            "além da própria" in corpo,
        )

# ---------------------------------------------------------------------------
print("\n[4] O hash do dia fica dentro da aquisicao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    origem = escrever_pdf(raiz, "decisao.pdf")

    primeira = servico.abrir_caso("Android", "CASO_001", "serial_A")
    servico.registrar_autorizacao(
        primeira, [{"tipo": "DECISAO_JUDICIAL", "arquivo": str(origem)}]
    )

    hash_esperado = calcular_sha256(origem)
    corpo_primeira = texto_da_aquisicao(primeira)
    checar("a aquisicao registra o SHA-256 do documento", hash_esperado in corpo_primeira)
    checar("a aquisicao nomeia o arquivo", "decisao.pdf" in corpo_primeira)

    # Segunda aquisicao no mesmo caso: a mesma decisao cobre o outro
    # aparelho, sem reanexar nada.
    segunda = servico.abrir_caso("Android", "CASO_001", "serial_B")
    resumo = servico.registrar_autorizacao(segunda, [])

    checar("as duas aquisicoes convivem no mesmo caso", primeira != segunda)
    checar("a segunda herda a autorizacao do caso", hash_esperado in texto_da_aquisicao(segunda))
    checar("o resumo da segunda cita a decisao judicial", "Decisão judicial" in resumo)
    checar(
        "o caso continua com um unico documento",
        len(servico.documentos_do_caso("CASO_001")) == 1,
    )

    documentos = servico.documentos_do_caso("CASO_001")
    checar("os documentos chegam a interface em campos simples", isinstance(documentos[0], dict))
    checar("com o hash junto", documentos[0]["sha256"] == hash_esperado)
    checar("e com rotulo legivel", documentos[0]["rotulo"] == "Decisão judicial")

    vazio = CaseService(raiz / "outra_raiz")
    checar("caso inexistente devolve lista vazia", vazio.documentos_do_caso("CASO_999") == [])

# ---------------------------------------------------------------------------
print("\n[5] Trocar o PDF depois do selo nao passa despercebido")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    origem = escrever_pdf(raiz, "decisao.pdf")

    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    servico.registrar_autorizacao(
        pasta_aquisicao, [{"tipo": "DECISAO_JUDICIAL", "arquivo": str(origem)}]
    )
    pasta_caso = pasta_aquisicao.parent
    gerar_manifesto(pasta_caso)

    checar("o caso selado esta integro", conferir_manifesto(pasta_caso).integro)

    copia = pasta_caso / PASTA_FUNDAMENTO / "decisao.pdf"
    copia.write_bytes(b"%PDF-1.4 outra decisao")

    depois = conferir_manifesto(pasta_caso)
    checar("trocar o PDF quebra a integridade do caso", not depois.integro)
    checar(
        "e o arquivo trocado e apontado pelo nome",
        any("decisao.pdf" in nome for nome in depois.alterados),
    )

# ---------------------------------------------------------------------------
print("\n[6] Juntar documento a caso ja selado: complemento e reselo")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)

    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    servico.registrar_autorizacao(pasta_aquisicao, [])
    gerar_manifesto(pasta_aquisicao)
    gerar_manifesto(pasta_aquisicao.parent)

    pasta_caso = pasta_aquisicao.parent
    corpo_antes = texto_da_aquisicao(pasta_aquisicao)
    registro_original = pasta_caso / PASTA_FUNDAMENTO / NOME_FUNDAMENTO
    original_antes = registro_original.read_bytes()

    # A decisao so foi digitalizada dias depois -- caso classico.
    tardio = escrever_pdf(raiz, "decisao_tardia.pdf")
    servico.anexar_ao_caso(pasta_caso, "DECISAO_JUDICIAL", tardio)

    checar("o documento entra na pasta do caso", (pasta_caso / PASTA_FUNDAMENTO / "decisao_tardia.pdf").is_file())
    checar("o caso passa a ter um documento", len(servico.documentos_do_caso("CASO_001")) == 1)

    checar(
        "a aquisicao ja selada NAO e reescrita",
        texto_da_aquisicao(pasta_aquisicao) == corpo_antes,
    )

    # O nucleo da correcao: com o caso ja selado, a juntada acrescenta folha
    # em vez de rasurar a que existia. Reescrever o registro original faria a
    # conferencia acusar alteracao desde o selo original -- corretamente -- e
    # o caso nunca mais fecharia integro por causa de uma juntada legitima.
    checar("o registro de autorizacao original NAO e reescrito", registro_original.read_bytes() == original_antes)
    novos = sorted((pasta_caso / PASTA_FUNDAMENTO).glob("fundamento_*.txt"))
    checar("a juntada gera um registro proprio, com carimbo", len(novos) == 1)
    checar("o registro novo avisa que substitui o anterior", "[REGISTRO ATUALIZADO]" in novos[0].read_text(encoding="utf-8"))
    checar("e nele consta o documento juntado", "decisao_tardia.pdf" in novos[0].read_text(encoding="utf-8"))

    checar("a aquisicao selada continua integra", conferir_manifesto(pasta_aquisicao).integro)
    checar("o caso reselado continua integro", conferir_manifesto(pasta_caso).integro)

    # O que o laudo desta aquisicao pode afirmar. Documento juntado depois
    # NAO estava a vista quando o exame foi feito: exibi-lo no laudo desta
    # aquisicao afirmaria o que nao ocorreu.
    checar(
        "o registro da aquisicao continua vazio -- o documento nao retroage",
        ler_autorizacao_da_aquisicao(pasta_aquisicao).vazia,
    )
    checar(
        "enquanto o caso, hoje, ja tem o documento",
        len(ler_autorizacao(pasta_caso).documentos) == 1,
    )

    complementos = [
        caminho
        for caminho in (pasta_caso / "complementos").glob("*.txt")
        if caminho.name != "INDICE.txt"
    ]
    checar("a juntada gera um complemento", len(complementos) == 1)
    corpo_complemento = complementos[0].read_text(encoding="utf-8")
    checar("o complemento traz o hash do que foi juntado", calcular_sha256(tardio) in corpo_complemento)
    checar(
        "o complemento avisa que aquisicoes anteriores nao passam a conta-lo",
        "NÃO passam a contar" in corpo_complemento,
    )

# ---------------------------------------------------------------------------
print("\n[7] Escrita direta da autorizacao, sem passar pelo servico")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    pasta_caso = raiz / "CASO_001"
    pasta_caso.mkdir()

    vazia = gravar_autorizacao(pasta_caso, ler_autorizacao(pasta_caso))
    checar("caso novo comeca sem documento", vazia.vazia)
    checar("e mesmo assim o texto e gravado", (pasta_caso / PASTA_FUNDAMENTO / NOME_FUNDAMENTO).is_file())

    pasta_aquisicao = pasta_caso / "android_20260823_100000"
    pasta_aquisicao.mkdir()
    caminho = gravar_autorizacao_da_aquisicao(pasta_aquisicao, vazia)
    checar("a aquisicao recebe o registro no lugar certo", caminho.parent.name == PASTA_AUTORIZACAO)

    # JSON corrompido nao pode derrubar a abertura do caso: melhor devolver
    # autorizacao vazia -- que declara ausencia -- do que estourar.
    (pasta_caso / PASTA_FUNDAMENTO / "fundamento.json").write_text("{ nao e json", encoding="utf-8")
    checar("json ilegivel devolve autorizacao vazia", ler_autorizacao(pasta_caso).vazia)

# ---------------------------------------------------------------------------
print("\n[8] A interface recebe as opcoes sem conhecer core")
# ---------------------------------------------------------------------------
opcoes = opcoes_tipo_documento()
rotulos = {rotulo for _, rotulo in opcoes}
checar("os tipos de documento sao oferecidos", len(opcoes) == 4)
checar("decisao judicial esta entre eles", "Decisão judicial" in rotulos)
checar("termo de consentimento esta entre eles", "Termo de consentimento do titular" in rotulos)
checar("requisicao do exame esta entre eles", "Requisição ou contrato do exame" in rotulos)
# A CHAVE gravada nos casos antigos continua valendo: so o rotulo mudou.
checar("a chave antiga do termo continua existindo",
       "TERMO_DE_DECLARACOES" in {chave for chave, _ in opcoes})
checar(
    "todas as opcoes vem como (chave, rotulo) legivel",
    all(isinstance(c, str) and isinstance(r, str) for c, r in opcoes),
)

# ---------------------------------------------------------------------------
print("\n[9] Adulterar a decisao e detectado sem selar o caso inteiro")
# ---------------------------------------------------------------------------
# Este e o fluxo REAL: a extracao sela a AQUISICAO, nao o caso. O documento
# mora um nivel acima e nao entra no manifesto da aquisicao -- e re-hashear o
# caso todo a cada coleta dobraria o tempo de uma extracao fisica. O que
# fecha a lacuna e o hash que a aquisicao selou no dia.
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    origem = escrever_pdf(raiz, "decisao.pdf")

    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    (pasta_aquisicao / "dado.txt").write_text("evidencia", encoding="utf-8")
    servico.registrar_autorizacao(
        pasta_aquisicao, [{"tipo": "DECISAO_JUDICIAL", "arquivo": str(origem)}]
    )
    gerar_manifesto(pasta_aquisicao)
    pasta_caso = pasta_aquisicao.parent
    copia = pasta_caso / PASTA_FUNDAMENTO / "decisao.pdf"

    checar("o caso NAO e selado pela extracao", localizar_manifesto(pasta_caso) is None)
    checar("o documento nao entra no manifesto da aquisicao", "decisao.pdf" not in
           " ".join(ler_manifesto(localizar_manifesto(pasta_aquisicao))))
    checar("e mesmo assim a aquisicao esta integra", conferir_manifesto(pasta_aquisicao).integro)

    guardado = copia.read_bytes()
    copia.write_bytes(b"%PDF-1.4 outra decisao")
    resultado = conferir_manifesto(pasta_aquisicao)
    checar("trocar a decisao quebra a integridade da aquisicao", not resultado.integro)
    checar("e o documento trocado e apontado pelo nome", "decisao.pdf" in resultado.autorizacao_divergente)
    checar("o resumo fala em documento de AUTORIZACAO", "AUTORIZAÇÃO" in resultado.resumo)

    copia.write_bytes(guardado)
    checar("restaurar o documento devolve a integridade", conferir_manifesto(pasta_aquisicao).integro)

    copia.unlink()
    resultado = conferir_manifesto(pasta_aquisicao)
    checar("apagar a decisao tambem e detectado", not resultado.integro)
    checar("e entra como ausente, nao como alterado", resultado.autorizacao_ausente == ["decisao.pdf"])
    checar("sem se confundir com alteracao", resultado.autorizacao_divergente == [])

    relatorio = sorted(pasta_aquisicao.glob("conferencia_integridade*.txt"))[-1]
    checar(
        "o relatorio de conferencia explica o achado",
        "DOCUMENTOS DE AUTORIZAÇÃO AUSENTES" in relatorio.read_text(encoding="utf-8"),
    )

# ---------------------------------------------------------------------------
print("\n[10] Aquisicao sem documento nao inventa divergencia")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    (pasta_aquisicao / "dado.txt").write_text("evidencia", encoding="utf-8")
    servico.registrar_autorizacao(pasta_aquisicao, [])
    gerar_manifesto(pasta_aquisicao)

    resultado = conferir_manifesto(pasta_aquisicao)
    checar("aquisicao sem documento continua integra", resultado.integro)
    checar("e nada e reportado como divergente", resultado.autorizacao_divergente == [])
    checar("nem como ausente", resultado.autorizacao_ausente == [])

# ---------------------------------------------------------------------------
print("\n[11] Juntada em caso NAO selado tambem junta folha, nao rasura")
# ---------------------------------------------------------------------------
# Reproduz o CASO_009, que falhou em uso real. A protecao contra rasura
# perguntava se o CASO tinha manifesto -- e a extracao sela a AQUISICAO, nao
# o caso. Entao, na primeira juntada, o registro original que declarava a
# ausencia era silenciosamente sobrescrito, justamente no caminho comum.
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    origem = escrever_pdf(raiz, "decisao_tardia.pdf")

    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    (pasta_aquisicao / "dado.txt").write_text("evidencia", encoding="utf-8")
    servico.registrar_autorizacao(pasta_aquisicao, [])
    gerar_manifesto(pasta_aquisicao)          # a extracao sela SO a aquisicao
    pasta_caso = pasta_aquisicao.parent

    checar("o caso nao tem selo proprio", localizar_manifesto(pasta_caso) is None)
    registro_original = pasta_caso / PASTA_FUNDAMENTO / NOME_FUNDAMENTO
    antes = registro_original.read_bytes()
    checar("e o registro original declara a ausencia", "[NENHUM DOCUMENTO ANEXADO]" in antes.decode("utf-8"))

    servico.anexar_ao_caso(pasta_caso, "DECISAO_JUDICIAL", origem)

    checar("o registro original NAO e reescrito", registro_original.read_bytes() == antes)
    checar(
        "e continua declarando a ausencia que havia na epoca",
        "[NENHUM DOCUMENTO ANEXADO]" in registro_original.read_text(encoding="utf-8"),
    )
    novos = sorted((pasta_caso / PASTA_FUNDAMENTO).glob("fundamento_*.txt"))
    checar("a juntada gera um registro proprio, com carimbo", len(novos) == 1)
    corpo_novo = novos[0].read_text(encoding="utf-8")
    checar("o registro novo avisa que substitui o anterior", "[REGISTRO ATUALIZADO]" in corpo_novo)
    checar("e nele consta o documento juntado", "decisao_tardia.pdf" in corpo_novo)
    checar("o caso passa a ter o documento", len(servico.documentos_do_caso("CASO_001")) == 1)
    # O aviso NAO pode supor que o registro anterior estava selado: quando a
    # juntada acontece, o caso quase nunca tem manifesto -- foi exatamente
    # essa suposicao que causou o defeito do CASO_009.
    checar(
        "o aviso fala do que o caso declarava, nao do que foi selado",
        "que o caso declarava à época" in corpo_novo,
    )
    checar(
        "e nao supoe selo no registro anterior",
        "à época em que foi selado" not in corpo_novo,
    )

    # O que o teste existe para provar: o documento NAO retroage.
    checar(
        "a aquisicao continua sem documento a vista",
        ler_autorizacao_da_aquisicao(pasta_aquisicao).vazia,
    )
    checar("e continua integra", conferir_manifesto(pasta_aquisicao).integro)
    checar("o caso reselado esta integro", conferir_manifesto(pasta_caso).integro)

# ---------------------------------------------------------------------------
print("\n[12] Varios documentos num mesmo ato deixam UM registro")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario)
    servico = CaseService(raiz)
    decisao = escrever_pdf(raiz, "decisao.pdf", b"%PDF decisao")
    termo = escrever_pdf(raiz, "termo.pdf", b"%PDF termo")

    pasta_aquisicao = servico.abrir_caso("Android", "CASO_001", "serial_A")
    servico.registrar_autorizacao(
        pasta_aquisicao,
        [
            {"tipo": "DECISAO_JUDICIAL", "arquivo": str(decisao)},
            {"tipo": "TERMO_DE_DECLARACOES", "arquivo": str(termo)},
        ],
    )
    pasta_fundamento = pasta_aquisicao.parent / PASTA_FUNDAMENTO

    checar("os dois documentos entram no caso", len(ler_autorizacao(pasta_aquisicao.parent).documentos) == 2)
    checar("mas o caso ganha um unico registro", not list(pasta_fundamento.glob("fundamento_*.json")))
    checar("o registro base existe", (pasta_fundamento / NOME_FUNDAMENTO).is_file())

    corpo = texto_da_aquisicao(pasta_aquisicao)
    checar("a aquisicao registra os dois", "decisao.pdf" in corpo and "termo.pdf" in corpo)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
