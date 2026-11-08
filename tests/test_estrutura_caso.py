"""
Testes da estrutura de pastas: caso (projeto) x aquisicao.

O defeito que estes testes travam: a pasta de destino era
`extracoes/<identificador>` e era REAPROVEITADA quando ja existia. Duas
coletas com o mesmo identificador -- possivelmente de aparelhos diferentes
-- gravavam no mesmo lugar, sobrescrevendo arquivos e produzindo um
manifesto de hashes que cobria a mistura sem nada indicar que houve duas
aquisicoes.
"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import (
    criar_pasta_aquisicao,
    e_pasta_de_aquisicao,
    sugerir_proximo_identificador,
)
from core.hashing import listar_pastas_extracao
from services.case_service import CaseService

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
print("\n[1] Cada aquisicao ganha sua propria pasta dentro do caso")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    raiz = Path(td)
    momento = datetime(2026, 8, 22, 15, 22, 49)

    primeira = criar_pasta_aquisicao(raiz, "CASO_001", "Android", momento)
    checar("a pasta do caso e criada", (raiz / "CASO_001").is_dir())
    checar("a aquisicao fica dentro do caso", primeira.parent.name == "CASO_001")
    checar("o nome traz plataforma e timestamp", primeira.name == "android_20260822_152249")

    # Mesmo caso, mesmo segundo: nao pode colidir.
    segunda = criar_pasta_aquisicao(raiz, "CASO_001", "Android", momento)
    checar("segunda aquisicao no mesmo segundo NAO reaproveita a pasta", segunda != primeira)
    checar("a colisao e resolvida por sufixo", segunda.name == "android_20260822_152249_2")

    terceira = criar_pasta_aquisicao(raiz, "CASO_001", "Android", momento)
    checar("terceira colisao tambem e resolvida", terceira.name == "android_20260822_152249_3")

    # Plataformas diferentes convivem no mesmo caso.
    computador = criar_pasta_aquisicao(raiz, "CASO_001", "Computador", momento)
    checar("outra plataforma convive no mesmo caso", computador.parent.name == "CASO_001")
    checar("a plataforma aparece no nome", computador.name.startswith("computador_"))

    checar(
        "as quatro aquisicoes sao pastas distintas",
        len({primeira, segunda, terceira, computador}) == 4,
    )

    # Identificador com caracteres invalidos nao pode quebrar o caminho.
    bagunçado = criar_pasta_aquisicao(raiz, "caso 12/08: teste", "Android", momento)
    checar("identificador com barra e dois-pontos e sanitizado", bagunçado.parent.name.isascii())
    checar("nenhuma subpasta e criada por engano", bagunçado.parent.parent == raiz)

# ---------------------------------------------------------------------------
print("\n[2] Reconhecimento de pasta de aquisicao")
# ---------------------------------------------------------------------------
checar("android com timestamp e aquisicao", e_pasta_de_aquisicao("android_20260822_152249"))
checar("aquisicao com sufixo tambem e reconhecida", e_pasta_de_aquisicao("android_20260822_152249_2"))
checar("computador tambem", e_pasta_de_aquisicao("computador_20260822_152249"))
checar("pasta de evidencia NAO e aquisicao", not e_pasta_de_aquisicao("identificacao"))
checar("pasta de caso NAO e aquisicao", not e_pasta_de_aquisicao("CASO_001"))
checar("nome parecido sem hora NAO e aquisicao", not e_pasta_de_aquisicao("android_20260822"))

# ---------------------------------------------------------------------------
print("\n[3] Sugestao do proximo identificador")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    raiz = Path(td)
    checar("raiz vazia sugere CASO_001", sugerir_proximo_identificador(raiz) == "CASO_001")

    (raiz / "CASO_001").mkdir()
    (raiz / "CASO_012").mkdir()
    checar("sugere o sucessor do maior numero", sugerir_proximo_identificador(raiz) == "CASO_013")

    # O defeito real observado em campo: uma pasta com data no nome fazia a
    # sugestao pular para CASO_220827.
    (raiz / "teste_dia_220826").mkdir()
    checar(
        "pasta fora do padrao NAO contamina a sugestao",
        sugerir_proximo_identificador(raiz) == "CASO_013",
    )

    (raiz / "CASO_007_aparelho_do_fulano").mkdir()
    checar(
        "numero seguido de sufixo continua sendo lido",
        sugerir_proximo_identificador(raiz) == "CASO_013",
    )

# ---------------------------------------------------------------------------
print("\n[4] CaseService: abertura de caso ponta a ponta")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    servico = CaseService(Path(td))

    pasta = servico.abrir_caso("Android", "CASO_001", "0030000000")
    checar("abrir_caso devolve a pasta da aquisicao", e_pasta_de_aquisicao(pasta.name))
    checar("informacoes_caso.txt e gravado", (pasta / "informacoes_caso.txt").exists())

    conteudo = (pasta / "informacoes_caso.txt").read_text(encoding="utf-8")
    checar("o identificador do caso consta", "CASO_001" in conteudo)
    checar("o identificador do dispositivo consta", "0030000000" in conteudo)
    checar("a plataforma consta", "Android" in conteudo)

    outra = servico.abrir_caso("Android", "CASO_001", "OUTRO_APARELHO")
    checar("segunda coleta do mesmo caso vai para outra pasta", outra != pasta)
    checar("as duas convivem sob o mesmo caso", outra.parent == pasta.parent)
    checar(
        "o dispositivo de cada aquisicao fica separado",
        "OUTRO_APARELHO" in (outra / "informacoes_caso.txt").read_text(encoding="utf-8"),
    )

# ---------------------------------------------------------------------------
print("\n[5] Cadeia de custodia enxerga caso e aquisicao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    raiz = Path(td)
    servico = CaseService(raiz)
    aquisicao = servico.abrir_caso("Android", "CASO_001", "0030000000")
    (aquisicao / "media").mkdir()  # pasta de evidencia, nao de aquisicao

    destinos = [p.name for p in listar_pastas_extracao(raiz)]
    checar("a pasta do caso e um destino possivel", "CASO_001" in destinos)
    checar("a pasta da aquisicao tambem", aquisicao.name in destinos)
    checar("pasta de evidencia NAO vira destino", "media" not in destinos)

# ---------------------------------------------------------------------------
print("\n[6] Caso e aquisicao sao escopos distintos, nao duplicidade")
# ---------------------------------------------------------------------------
# Sem hierarquia visivel, a lista de cadeia de custodia mostrava o caso e a
# aquisicao como dois nomes soltos, e a leitura natural era de que a mesma
# pasta aparecia repetida. Sao escopos de selo diferentes: conferir a
# aquisicao verifica uma coleta; conferir o caso verifica o projeto inteiro.
from core.case import descrever_aquisicao
from services.hash_service import listar_pastas_custodia

plataforma, momento = descrever_aquisicao("android_20260822_183237")
checar("a plataforma e extraida do nome da pasta", plataforma == "Android")
checar("a data e hora sao extraidas", momento.strftime("%d/%m/%Y %H:%M") == "22/08/2026 18:32")

checar("computador tambem e reconhecido", descrever_aquisicao("computador_20260101_000000")[0] == "Computador")
checar("iOS mantem a grafia correta", descrever_aquisicao("ios_20260101_000000")[0] == "iOS")
checar("aquisicao com sufixo de colisao e reconhecida", descrever_aquisicao("android_20260822_183237_2")[0] == "Android")
checar("nome de caso nao e aquisicao", descrever_aquisicao("CASO_001") == ("", None))
checar("pasta de evidencia nao e aquisicao", descrever_aquisicao("identificacao") == ("", None))

with tempfile.TemporaryDirectory() as td:
    raiz = Path(td)
    servico = CaseService(raiz)
    primeira = servico.abrir_caso("Android", "CASO_001", "SERIAL_A")
    segunda = servico.abrir_caso("Computador", "CASO_001", "C:")
    (raiz / "caso_antigo_formato_plano").mkdir()

    itens = listar_pastas_custodia(raiz)
    casos = [i for i in itens if not i.e_aquisicao]
    aquisicoes = [i for i in itens if i.e_aquisicao]

    checar("os dois niveis aparecem na listagem", len(casos) == 2 and len(aquisicoes) == 2)
    checar(
        "o caso sabe quantas aquisicoes contem",
        next(i for i in casos if i.nome == "CASO_001").aquisicoes == 2,
    )
    checar(
        "pasta em formato antigo aparece sem aquisicoes",
        next(i for i in casos if i.nome == "caso_antigo_formato_plano").aquisicoes == 0,
    )
    checar(
        "a aquisicao carrega plataforma e momento para exibicao",
        all(i.plataforma and i.momento for i in aquisicoes),
    )
    checar(
        "as duas plataformas do mesmo caso aparecem",
        sorted(i.plataforma for i in aquisicoes) == ["Android", "Computador"],
    )
    checar("nenhuma pasta aparece selada antes de gerar", all(not i.selada for i in itens))

    from core.hashing import gerar_manifesto

    (primeira / "evidencia.txt").write_text("dado", encoding="utf-8")
    gerar_manifesto(primeira)

    itens = listar_pastas_custodia(raiz)
    selo_da_aquisicao = next(i for i in itens if i.caminho == primeira).selada
    selo_do_caso = next(i for i in itens if i.nome == "CASO_001" and not i.e_aquisicao).selada
    checar("selar a aquisicao marca apenas ela", selo_da_aquisicao is True)
    checar("o caso continua sem selo proprio", selo_do_caso is False)

print("\n[9] Caso ANTIGO (sem caso.json): a ficha le das aquisicoes e denuncia divergencia")
# ---------------------------------------------------------------------------
# Antes do registro unico, os dados do caso eram gravados dentro de CADA
# aquisicao, com os campos da epoca. O servico nao conhece mais esses nomes:
# trata como dado do caso tudo o que nao e da peca. Duas aquisicoes podem
# discordar, e escolher uma versao em silencio seria a ferramenta afirmando
# o que nao verificou.
from services.case_service import CaseService, ler_cadeia_custodia  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / 'extracoes'
    servico = CaseService(raiz)

    primeira = criar_pasta_aquisicao(raiz, 'CASO_100', 'Android',
                                     datetime(2026, 8, 1, 10, 0, 0))
    segunda = criar_pasta_aquisicao(raiz, 'CASO_100', 'Computador',
                                    datetime(2026, 8, 2, 11, 0, 0))
    (primeira / 'cadeia_custodia.txt').write_text(
        '=== CADEIA DE CUSTODIA ===' + chr(10) +
        'Natureza: Exame A' + chr(10) + 'Parte: Fulano' + chr(10) +
        'Equipamento: Celular A' + chr(10) + 'Lacre: 111' + chr(10), encoding='utf-8')
    (segunda / 'cadeia_custodia.txt').write_text(
        'Natureza: Exame B' + chr(10) + 'Parte: N/A' + chr(10) +
        'Equipamento: Pendrive' + chr(10) + 'Lacre: 222' + chr(10), encoding='utf-8')

    resumo = servico.resumo_do_caso(raiz / 'CASO_100')

    checar('a ficha encontra as duas aquisicoes', len(resumo.aquisicoes) == 2)
    checar('a mais recente vem primeiro',
           resumo.aquisicoes[0].plataforma == 'Computador')
    checar('cada aquisicao guarda o proprio equipamento',
           resumo.aquisicoes[0].equipamento == 'Pendrive'
           and resumo.aquisicoes[1].equipamento == 'Celular A')
    checar('o caso antigo e reconhecido como SEM registro proprio', not resumo.tem_registro)
    checar('a divergencia de dados do caso e DETECTADA', resumo.metadados_divergentes)
    checar('e o campo em conflito e nomeado', resumo.campos_divergentes == ['Natureza'])
    checar('a ficha mostra a versao da aquisicao mais recente',
           resumo.dados_do_caso.get('Natureza') == 'Exame B')
    checar("'N/A' e campo nao preenchido: nao diverge de quem preencheu",
           'Parte' not in resumo.campos_divergentes
           and resumo.dados_do_caso.get('Parte') == 'Fulano')
    checar('os dados da PECA nao sao tomados por dados do caso',
           'Equipamento' not in resumo.dados_do_caso and 'Lacre' not in resumo.dados_do_caso)
    checar('os lacres das pecas do caso sao reunidos', resumo.lacres == ['222', '111'])

with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / 'extracoes'
    servico = CaseService(raiz)
    unica = criar_pasta_aquisicao(raiz, 'CASO_101', 'Android',
                                  datetime(2026, 8, 1, 10, 0, 0))
    (unica / 'cadeia_custodia.txt').write_text(
        'Natureza: Exame A' + chr(10), encoding='utf-8')
    resumo = servico.resumo_do_caso(raiz / 'CASO_101')
    checar('caso coerente nao acusa divergencia',
           not resumo.metadados_divergentes)
    checar('campo ausente fica ausente, nao vira N/A inventado',
           'Parte' not in resumo.dados_do_caso)

    # Dentro do `with`: fora dele o diretorio temporario ja foi apagado, e
    # `ler_cadeia_custodia` devolveria {} por arquivo inexistente -- o teste
    # passaria a medir a ausencia do arquivo, nao a leitura.
    dados = ler_cadeia_custodia(unica / 'cadeia_custodia.txt')
    checar('a leitura ignora linhas de cabecalho',
           '=== CADEIA DE CUSTODIA ===' not in dados)
    checar('e devolve os pares chave/valor', dados.get('Natureza') == 'Exame A')

print("\n[10] Registro UNICO do caso: varios dispositivos, um cadastro")
# ---------------------------------------------------------------------------
# O defeito que este bloco trava: a segunda aquisicao de um caso gravava
# 'N/A' nos dados do caso em vez de herdar, e as duas passavam a discordar.
from core.hashing import conferir_manifesto, gerar_manifesto  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / 'extracoes'
    servico = CaseService(raiz)

    telefone_a = servico.abrir_caso('Android', 'CASO_200', 'SERIAL_A')
    servico.gravar_dados_do_caso('CASO_200', {
        'referencia': 'Proc. 123', 'descricao': 'Dois telefones', 'solicitante': ''})
    servico.gravar_cadeia_custodia(telefone_a, 'CASO_200', {
        'marca_modelo': 'Telefone A', 'lacre': 'L-001', 'fotos': []})

    # Segundo telefone do MESMO caso: nada do caso e perguntado de novo.
    import time
    time.sleep(1.1)
    telefone_b = servico.abrir_caso('Android', 'CASO_200', 'SERIAL_B')
    servico.gravar_cadeia_custodia(telefone_b, 'CASO_200', {
        'marca_modelo': 'Telefone B', 'lacre': 'L-002', 'fotos': []})

    cadeia_a = ler_cadeia_custodia(telefone_a / 'cadeia_custodia.txt')
    cadeia_b = ler_cadeia_custodia(telefone_b / 'cadeia_custodia.txt')
    checar('as duas aquisicoes sao pastas distintas do mesmo caso',
           telefone_a != telefone_b and telefone_a.parent == telefone_b.parent)
    checar('a segunda aquisicao HERDA a referencia do caso',
           cadeia_b.get('Referência') == 'Proc. 123' == cadeia_a.get('Referência'))
    checar('cada aquisicao guarda o proprio lacre',
           cadeia_a.get('Lacre') == 'L-001' and cadeia_b.get('Lacre') == 'L-002')
    checar('campo do caso em branco e DITO, nao omitido',
           cadeia_a.get('Solicitante') == 'não informado')
    checar('sem fotos, o registro diz que nao ha fotos',
           cadeia_a.get('Fotos Anexas') == 'nenhuma')

    resumo = servico.resumo_do_caso(raiz / 'CASO_200')
    checar('a ficha le do registro do caso', resumo.tem_registro)
    checar('e nao ha divergencia possivel entre aquisicoes',
           not resumo.metadados_divergentes)
    checar('a ficha reune os dois lacres', sorted(resumo.lacres) == ['L-001', 'L-002'])
    checar('a linha de reconhecimento traz so o que foi preenchido',
           resumo.reconhecimento == ['Proc. 123', 'Dois telefones'])

    # Retificacao: muda o registro do caso, NAO as aquisicoes seladas.
    gerar_manifesto(telefone_a)
    alterou = servico.retificar_caso(raiz / 'CASO_200', {
        'referencia': 'Proc. 456', 'descricao': 'Dois telefones', 'solicitante': ''})
    checar('a retificacao e reportada como alteracao', alterou is True)
    checar('o registro do caso passa a ter o valor novo',
           servico.dados_do_caso('CASO_200')['referencia'] == 'Proc. 456')
    checar('a aquisicao selada continua integra', conferir_manifesto(telefone_a).integro)
    checar('e continua dizendo o que o caso dizia NO DIA',
           ler_cadeia_custodia(telefone_a / 'cadeia_custodia.txt')['Referência'] == 'Proc. 123')
    complementos = [c for c in (raiz / 'CASO_200' / 'complementos').glob('*.txt')
                    if c.name != 'INDICE.txt']
    texto = complementos[0].read_text(encoding='utf-8') if complementos else ''
    checar('a retificacao vira complemento, com o antes e o depois',
           len(complementos) == 1 and 'Proc. 123  ->  Proc. 456' in texto)
    checar('retificar sem mudar nada nao gera complemento',
           servico.retificar_caso(raiz / 'CASO_200', {
               'referencia': 'Proc. 456', 'descricao': 'Dois telefones', 'solicitante': ''}) is False)

    # Retificacao da PECA: so as linhas da peca mudam.
    novo = servico.cadeia_com_dispositivo_retificado(
        telefone_b / 'cadeia_custodia.txt',
        {'marca_modelo': 'Telefone B (corrigido)', 'cor': 'Azul', 'estado': '', 'lacre': 'L-002'})
    checar('a retificacao da peca troca o equipamento',
           'Equipamento: Telefone B (corrigido)' in novo and 'Cor: Azul' in novo)
    checar('e preserva os dados do caso como estavam', 'Referência: Proc. 123' in novo)


print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
