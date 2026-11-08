"""
Protocolos periciais do exame, conforme a ABNT NBR ISO/IEC 27037:2013.

O questionário é dividido em dois blocos, e a divisão é a coisa mais
importante deste módulo:

**O que a ferramenta verifica, ela responde sozinha.** Perguntar ao
examinador se as alterações foram registradas, quando o próprio
`registro_procedimento.txt` as registra, é pedir que ele confirme um fato
que o sistema já conhece — e abrir a porta para que a resposta divirja da
evidência. Cada resposta automática vem acompanhada do arquivo que a
sustenta, de modo que o leitor do laudo possa conferir.

**O que só o examinador sabe, só ele responde.** Se o aparelho estava
ligado ao ser recebido, se o lacre estava íntegro, por qual meio foi
isolado — nada disso o software observa. Aqui ele pergunta, e aceita não
saber: item sem resposta vira "Não respondido", nunca "Sim".

Referências de cláusula da norma acompanham cada item, para que o laudo
possa ser confrontado com ela.
"""

from __future__ import annotations

from pathlib import Path

from .case import juntar_complemento, pasta_do_caso

SIM = "Sim"
NAO = "Não"
NAO_SE_APLICA = "Não se aplica"
NAO_RESPONDIDO = "Não respondido"
NAO_LOCALIZADO = "Registro não localizado"

# Títulos das entradas do diário, escritos por `core.procedimento`. São
# strings da própria ferramenta, não de terceiro — por isso procurá-las é
# leitura de registro conhecido, e não interpretação frágil de texto alheio.
TITULO_AMBIENTE = "AMBIENTE DA ESTAÇÃO FORENSE"
TITULO_RELOGIO = "AFERIÇÃO DE RELÓGIO"
TITULO_ALTERACAO = "ALTERAÇÃO NO DISPOSITIVO EXAMINADO"
TITULO_DECISAO = "DECISÃO METODOLÓGICA"

# ---------------------------------------------------------------------------
# Bloco 1 — o que só o examinador sabe
# ---------------------------------------------------------------------------
# Cada item é (cláusula, pergunta). A cláusula vai ao laudo para que a
# aderência à norma possa ser conferida item a item.
# A redacao pergunta FATO, e nao conformidade. "O dispositivo estava
# ligado?" e observavel; "foi mantido no estado em que foi recebido?" pedia
# que o examinador certificasse o proprio cumprimento da norma. A diferenca
# tem consequencia no laudo: aqui "Nao" nao e defeito, e por isso este bloco
# nao pode ser apresentado como lista de conformidade.
#
# Os itens marcados "Especificar" so ficam completos com a observacao ao
# lado; sem ela o laudo imprime "Sim -- nao especificado", para o silencio
# aparecer em vez de passar por resposta.
PERGUNTAS_DO_EXAMINADOR = (
    (
        "6.8",
        "Há autorização do interessado ou decisão judicial autorizando a coleta?",
    ),
    (
        "6.2.1",
        "O dispositivo estava ligado no momento da coleta?",
    ),
    (
        "6.2.1",
        "O dispositivo foi isolado de redes durante a coleta? Especificar.",
    ),
    (
        "6.1",
        "A integridade física do lacre foi conferida no recebimento?",
    ),
    (
        "6.4",
        "O operador atuou dentro dos limites de sua competência técnica?",
    ),
    (
        "5.4.1",
        "Houve manuseio do dispositivo? Especificar.",
    ),
)

# Itens cuja resposta afirmativa fica incompleta sem a observacao ao lado.
# Identificados pelo texto da propria pergunta, para nao existir uma
# segunda lista que possa divergir desta.
MARCA_ESPECIFICAR = "Especificar."

# Separador de linha do texto do complemento.
QUEBRA = chr(10)


def exige_especificacao(pergunta: str) -> bool:
    """`True` se a pergunta pede detalhamento na observação do item."""
    return pergunta.strip().endswith(MARCA_ESPECIFICAR)


def perguntas_do_examinador() -> list:
    """(cláusula, pergunta) de cada item que depende de quem periciou."""
    return list(PERGUNTAS_DO_EXAMINADOR)


# ---------------------------------------------------------------------------
# Bloco 2 — o que a própria ferramenta comprova
# ---------------------------------------------------------------------------
def verificar_automaticos(pasta_aquisicao: Path) -> list:
    """
    Responde, com base nos registros da aquisição, os itens que a ferramenta
    pode comprovar sozinha.

    Devolve `(cláusula, pergunta, resposta, origem)`. A origem é o arquivo
    que sustenta a resposta — sem ela, a resposta seria mais uma afirmação
    sem lastro, que é justamente o que este módulo evita.

    Registro ausente NUNCA vira "Não": vira "Registro não localizado". As
    duas coisas são diferentes, e só a segunda é verdadeira quando o arquivo
    não está lá.
    """
    pasta = Path(pasta_aquisicao)
    diario = pasta / "registro_procedimento.txt"
    texto = ""
    if diario.is_file():
        try:
            texto = diario.read_text(encoding="utf-8")
        except OSError:
            texto = ""

    itens = []

    # 5.3.2 Auditabilidade — avaliação independente exige documentação de tudo.
    if texto:
        itens.append((
            "5.3.2",
            "As ações realizadas foram documentadas de modo a permitir avaliação "
            "independente do procedimento?",
            SIM,
            f"{diario.name} e extracao.log",
        ))
    else:
        itens.append((
            "5.3.2",
            "As ações realizadas foram documentadas de modo a permitir avaliação "
            "independente do procedimento?",
            NAO_LOCALIZADO,
            "—",
        ))

    # 5.3.3 e 5.3.4 Repetibilidade e reprodutibilidade — dependem de as
    # condições do exame estarem registradas.
    itens.append((
        "5.3.3 / 5.3.4",
        "As condições do exame — estação, ferramenta e versões — foram registradas, "
        "permitindo repetição e reprodução?",
        SIM if TITULO_AMBIENTE in texto else NAO_LOCALIZADO,
        f"{diario.name}, entrada de ambiente" if TITULO_AMBIENTE in texto else "—",
    ))

    # 5.3.5 Justificabilidade — as decisões metodológicas precisam constar.
    decisoes = texto.count(TITULO_DECISAO)
    itens.append((
        "5.3.5",
        "As decisões metodológicas do exame foram registradas com sua justificativa?",
        f"{SIM} ({decisoes} registrada(s))" if decisoes else NAO_LOCALIZADO,
        f"{diario.name}, decisões metodológicas" if decisoes else "—",
    ))

    # 5.4.1 e 6.1 — alteração inevitável não é proibida; é obrigatório
    # registrá-la e justificá-la. A norma NÃO exige ausência de alteração.
    alteracoes = texto.count(TITULO_ALTERACAO)
    if not texto:
        resposta_alteracao, origem_alteracao = NAO_LOCALIZADO, "—"
    elif alteracoes:
        resposta_alteracao = f"{SIM} ({alteracoes} registrada(s) e justificada(s))"
        origem_alteracao = f"{diario.name}, alterações no dispositivo"
    else:
        resposta_alteracao = "Nenhuma alteração foi registrada nesta aquisição"
        origem_alteracao = diario.name
    itens.append((
        "5.4.1 / 6.1",
        "As alterações provocadas no dispositivo foram registradas e justificadas?",
        resposta_alteracao,
        origem_alteracao,
    ))

    # 6.6 Documentação — o relógio do aparelho confrontado com fonte confiável.
    itens.append((
        "6.6",
        "O relógio do dispositivo foi confrontado com o da estação e o desvio "
        "registrado?",
        SIM if TITULO_RELOGIO in texto else NAO_LOCALIZADO,
        f"{diario.name}, aferição de relógio" if TITULO_RELOGIO in texto else "—",
    ))

    # 6.6 Documentação — identificadores únicos do dispositivo.
    tem_identificacao = (pasta / "identificacao").is_dir() or (pasta / "device_specs").is_dir()
    itens.append((
        "6.6",
        "Os identificadores do dispositivo foram documentados?",
        SIM if tem_identificacao else NAO_LOCALIZADO,
        "identificacao/ e device_specs/" if tem_identificacao else "—",
    ))

    # 6.1 Cadeia de custódia.
    custodia = pasta / "cadeia_custodia.txt"
    itens.append((
        "6.1",
        "Há registro de cadeia de custódia para esta aquisição?",
        SIM if custodia.is_file() else NAO_LOCALIZADO,
        custodia.name if custodia.is_file() else "—",
    ))

    # 5.4.5 Preservação — demonstrar que a evidência não foi modificada
    # depois de adquirida. É o que o manifesto sustenta.
    manifestos = sorted(pasta.glob("manifesto_hashes*.txt"))
    itens.append((
        "5.4.5",
        "A integridade do material adquirido está selada, permitindo demonstrar que "
        "não foi modificado após a coleta?",
        SIM if manifestos else NAO_LOCALIZADO,
        manifestos[-1].name if manifestos else "—",
    ))

    return itens


# ---------------------------------------------------------------------------
# Persistência das respostas do examinador
# ---------------------------------------------------------------------------
def gravar_respostas(pasta_aquisicao: Path, protocolos, observacoes: str = "") -> Path:
    """
    Grava as respostas do examinador como **complemento ao caso**.

    Elas não existiam em lugar nenhum: saíam do formulário direto para o
    gerador do documento e morriam ali. Reemitir um laudo obrigava a
    responder tudo de novo, sem nada garantir que a segunda resposta fosse
    igual à primeira — duas declarações do mesmo exame, divergentes, e
    nenhuma delas preservada.

    Vai como complemento, e não para dentro da aquisição, porque a
    aquisição é selada no dia da coleta e estas respostas são dadas depois,
    na elaboração do laudo. Gravá-las lá dentro faria o material divergir
    do próprio manifesto. É a regra de todo registro formal, que
    `juntar_complemento` já implementa: não se rasura folha, junta-se
    aditamento — e o complemento carimba **quando** foi declarado.
    """
    pasta_aquisicao = Path(pasta_aquisicao)

    linhas = [
        f"Aquisição a que se referem: {pasta_aquisicao.name}",
        "",
        "Respostas do examinador aos protocolos periciais (ABNT NBR ISO/IEC 27037).",
        "São declarações de fato sobre circunstâncias do exame, não aferição de",
        "conformidade: 'Não' não indica irregularidade.",
        "",
    ]

    for item in protocolos:
        clausula, pergunta, resposta, observacao = desdobrar(item)
        if resposta == SIM and not observacao and exige_especificacao(pergunta):
            resposta = f"{SIM} — não especificado"
        linhas.append(f"[{clausula}] {pergunta}")
        linhas.append(f"    Resposta: {resposta}")
        linhas.append(f"    Observação: {observacao or '—'}")
        linhas.append("")

    texto_geral = (observacoes or "").strip()
    linhas.append("Observações gerais do examinador:")
    linhas.append(texto_geral or "—")

    return juntar_complemento(
        pasta_do_caso(pasta_aquisicao),
        f"Protocolos periciais - {pasta_aquisicao.name}",
        QUEBRA.join(linhas),
    )


def desdobrar(item) -> tuple:
    """
    Normaliza um item em `(cláusula, pergunta, resposta, observação)`.

    Aquisições anteriores à observação por item gravaram trincas, e antes
    delas houve pares sem cláusula. Um documento emitido hoje sobre uma
    coleta antiga precisa continuar abrindo: reescrever aquele registro
    para caber no formato novo seria alterar o que foi declarado na época.
    """
    if len(item) >= 4:
        return item[0], item[1], item[2], (item[3] or "")
    if len(item) == 3:
        return item[0], item[1], item[2], ""
    return "—", item[0], item[1], ""
