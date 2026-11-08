"""
Blocos de conteúdo compartilhados pelo Relatório de Extração e pelo Laudo
Pericial.

Cada função recebe o dossiê da aquisição e devolve uma lista de elementos
prontos para a página. A regra é a de toda a suíte: **o documento não
afirma o que a ferramenta não verificou**. Quando o registro necessário
não existe, o bloco diz isso por extenso, em vez de omitir a seção ou de
preenchê-la com suposição — seção ausente seria lida como "nada a
declarar", que é outra afirmação.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from core.aparelho import IDENTIFICADORES_GENERICOS
from core.operador import NAO_DECLARADO
from core.protocolos import desdobrar, exige_especificacao, verificar_automaticos
from core.relogio import alerta as alerta_do_relogio, descrever_desvio
from services.dossie_service import Dossie, carimbo_legivel, tamanho_legivel
from services.identidade_pdf import (
    CINZA_LINHA,
    escapar,
    estilos,
    imagem_ajustada,
    tabela,
    tabela_de_pares,
)

# Acima disto o manifesto não é impresso linha a linha: um dump de sistema
# de arquivos tem dezenas de milhares de arquivos, e mil páginas de hash
# não são lidas por ninguém. O arquivo de manifesto continua sendo a fonte.
LIMITE_DE_LINHAS_DO_MANIFESTO = 1200
# Por categoria, o mesmo raciocínio: a lista serve para ver o que há, e o
# manifesto continua sendo a relação completa.
LIMITE_DE_ARQUIVOS_POR_CATEGORIA = 200

NAO_INFORMADO = "<i>não informado</i>"


def _ou_nao_informado(valor: str) -> str:
    return escapar(valor) if str(valor or "").strip() else NAO_INFORMADO


# ---------------------------------------------------------------------------
# Identificação
# ---------------------------------------------------------------------------
def texto_do_operador(dossie: Dossie) -> str:
    if dossie.operador is None:
        return "Não registrado nesta aquisição (anterior ao registro de operador)"
    return dossie.operador.resumo()


def bloco_identificacao(dossie: Dossie, largura: float) -> list:
    pares = [("Caso", escapar(dossie.caso))]
    pares += [(rotulo, _ou_nao_informado(valor)) for rotulo, valor in dossie.dados_do_caso]
    pares += [
        ("Aquisição", escapar(dossie.pasta.name)),
        ("Plataforma", _ou_nao_informado(dossie.plataforma)),
        ("Início da aquisição", _ou_nao_informado(carimbo_legivel(dossie.abertura))),
        ("Encerramento", _ou_nao_informado(carimbo_legivel(dossie.encerramento))),
        ("Operador da aquisição", escapar(texto_do_operador(dossie))),
        ("Conta do sistema na estação", _ou_nao_informado(dossie.conta_da_estacao)),
    ]
    elementos = [tabela_de_pares(pares, largura)]
    e = estilos()
    if not dossie.tem_cadeia_de_custodia:
        elementos += [Spacer(1, 4), Paragraph(
            "Esta aquisição não tem registro de cadeia de custódia "
            "(cadeia_custodia.txt). Os dados do caso e da peça não puderam ser lidos.",
            e["alerta"],
        )]
    if dossie.operador is not None and not dossie.operador.declarado:
        elementos += [Spacer(1, 4), Paragraph(
            f"O operador consta como {NAO_DECLARADO}: o perfil do examinador não estava "
            "preenchido no momento da aquisição. A conta do sistema acima foi apurada "
            "pela ferramenta, e não equivale a identificação de pessoa.",
            e["nota"],
        )]
    elif dossie.operador is not None and dossie.de_teste:
        elementos += [Spacer(1, 4), Paragraph(
            "Aquisição feita pela conta de testes (Forensic Admin) da versão de "
            "desenvolvimento da suíte: é TESTE, sem valor pericial, e isso está gravado sob "
            "o selo da aquisição.",
            e["alerta"],
        )]
    elif dossie.operador is not None and dossie.operador.autenticacao.strip():
        elementos += [Spacer(1, 4), Paragraph(
            "O operador é o examinador cuja senha abriu a sessão nesta estação; os dados "
            "dele são os do cadastro. A senha não prova identidade, e a ferramenta não a "
            "confere além disso. A conta do sistema foi apurada por ela.",
            e["nota"],
        )]
    elif dossie.operador is not None:
        elementos += [Spacer(1, 4), Paragraph(
            "O operador é o que foi DECLARADO no perfil do examinador; a ferramenta não "
            "confere identidade. A conta do sistema foi apurada por ela.",
            e["nota"],
        )]
    return elementos


# ---------------------------------------------------------------------------
# Peça examinada
# ---------------------------------------------------------------------------
SEM_CARACTERISTICAS = (
    "Nenhuma característica foi apurada do próprio dispositivo nesta aquisição — "
    "os módulos que as leem não foram executados. Isso não é ausência de "
    "característica no dispositivo: é ausência de coleta."
)


def bloco_peca(dossie: Dossie, largura: float, sem_caracteristicas: str = "") -> list:
    e = estilos()
    elementos = [Paragraph("Declarado no cadastro (cadeia de custódia)", e["subsecao"])]
    if dossie.tem_cadeia_de_custodia:
        elementos.append(tabela_de_pares(
            [(rotulo, _ou_nao_informado(valor)) for rotulo, valor in dossie.peca], largura
        ))
    else:
        elementos.append(Paragraph("Registro de cadeia de custódia não localizado.", e["corpo"]))

    elementos.append(Paragraph("Apurado pela extração, do próprio dispositivo", e["subsecao"]))
    pares = list(dossie.apuradas)
    # O nome genérico ("celular_android") é dado quando nenhum aparelho
    # respondeu: não foi lido do dispositivo e não entra como apurado.
    if (dossie.identificador_do_dispositivo
            and dossie.identificador_do_dispositivo not in IDENTIFICADORES_GENERICOS):
        pares.insert(0, (
            "Identificador usado na aquisição", dossie.identificador_do_dispositivo
        ))
    if dossie.desvio_do_relogio is not None:
        pares.append(("Relógio do aparelho (aferido na aquisição)",
                      "sem desvio" if dossie.desvio_do_relogio == 0
                      else "desvio de " + descrever_desvio(dossie.desvio_do_relogio)))
    if pares:
        elementos.append(tabela_de_pares(
            [(rotulo, escapar(valor)) for rotulo, valor in pares], largura
        ))
        if alerta_do_relogio(dossie.desvio_do_relogio):
            elementos += [Spacer(1, 3), Paragraph(
                escapar(alerta_do_relogio(dossie.desvio_do_relogio)), e["alerta"])]
        elementos += [Spacer(1, 3), Paragraph(
            "São os valores que o sistema do dispositivo declara de si mesmo. Em "
            "dispositivo com sistema modificado, podem não corresponder ao equipamento "
            "real. A separação entre o declarado e o apurado é deliberada: o segundo a "
            "ferramenta sustenta com registro; o primeiro depende de quem preencheu.",
            e["nota"],
        )]
    else:
        elementos.append(Paragraph(sem_caracteristicas or SEM_CARACTERISTICAS, e["corpo"]))
    return elementos


def bloco_fotos(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.fotos:
        return [Paragraph(
            "Nenhuma fotografia da peça foi anexada a esta aquisição.", e["corpo"]
        )]

    celulas = []
    for indice, foto in enumerate(dossie.fotos, 1):
        imagem = imagem_ajustada(foto, largura / 2 - 14, 190)
        legenda = Paragraph(
            f"Foto {indice} — {escapar(foto.name)}<br/>"
            f"SHA-256: {escapar(dossie.hashes.get(foto.relative_to(dossie.pasta).as_posix(), 'fora do manifesto'))}",
            e["mono_pequeno"],
        )
        if imagem is None:
            # Imagem ilegível é fato a declarar, não a omitir.
            celulas.append([Paragraph(
                f"Foto {indice}: {escapar(foto.name)} — não pôde ser exibida", e["alerta"]
            ), legenda])
        else:
            celulas.append([imagem, Spacer(1, 3), legenda])

    linhas = [celulas[i:i + 2] for i in range(0, len(celulas), 2)]
    if len(linhas[-1]) == 1:
        linhas[-1].append("")
    grade = Table(linhas, colWidths=[largura / 2, largura / 2])
    grade.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, CINZA_LINHA),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, CINZA_LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [grade]


# ---------------------------------------------------------------------------
# Ambiente, autorização, método
# ---------------------------------------------------------------------------
def bloco_ambiente(dossie: Dossie, largura: float) -> list:
    e = estilos()
    elementos = []
    if dossie.ambiente:
        elementos.append(tabela_de_pares(
            [(chave, escapar(valor)) for chave, valor in dossie.ambiente], largura
        ))
        elementos += [Spacer(1, 3), Paragraph(
            "Ambiente gravado no momento da aquisição, no registro do procedimento — "
            "e não o da estação em que este documento foi impresso. É o que permite a "
            "terceiro reproduzir as condições do exame (repetibilidade e "
            "reprodutibilidade, ABNT NBR ISO/IEC 27037).",
            e["nota"],
        )]
    else:
        elementos.append(Paragraph(
            "O ambiente da estação não consta do registro do procedimento desta aquisição.",
            e["corpo"],
        ))

    relogio = dossie.evento("AFERIÇÃO DE RELÓGIO")
    elementos.append(Paragraph("Aferição de relógio", e["subsecao"]))
    if relogio:
        elementos.append(Paragraph(escapar(relogio.texto), e["esquerda"]))
    else:
        elementos.append(Paragraph(
            "Não há aferição de relógio registrada nesta aquisição. As datas dos "
            "registros do dispositivo não puderam ser confrontadas com o relógio da "
            "estação.",
            e["corpo"],
        ))
    return elementos


def bloco_autorizacao(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.autorizacao.vazia:
        return [Paragraph(
            "Nenhum documento de autorização estava anexado ao caso no momento desta "
            "aquisição. Isto NÃO afirma que a autorização inexista: significa apenas que "
            "a ferramenta não teve documento algum à vista para copiar e calcular o hash.",
            e["corpo"],
        )]
    linhas = [
        [escapar(d.rotulo), escapar(getattr(d.arquivo, "name", d.arquivo)),
         Paragraph(escapar(d.sha256), e["mono_pequeno"]), escapar(carimbo_legivel(d.juntado_em))]
        for d in dossie.autorizacao.documentos
    ]
    return [
        tabela(["Documento", "Arquivo", "SHA-256", "Anexado em"], linhas,
               [largura * 0.2, largura * 0.22, largura * 0.4, largura * 0.18]),
        Spacer(1, 3),
        Paragraph(
            "A ferramenta afirma apenas que estes arquivos, com estes hashes, estavam "
            "anexados ao caso no momento da aquisição. Ela não lê o conteúdo dos "
            "documentos: não atesta autenticidade, assinatura nem validade.",
            e["nota"],
        ),
    ]


def bloco_metodo(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.metodo.vazio:
        return [Paragraph(
            "O registro de método desta aquisição não foi localizado. Os módulos "
            "empregados não puderam ser reproduzidos aqui a partir do que foi selado.",
            e["corpo"],
        )]
    linhas = [[escapar(m.nome), escapar(m.perfil)] for m in dossie.metodo.modulos]
    return [tabela(["Módulo empregado", "Competência exigida"], linhas,
                   [largura * 0.68, largura * 0.32])]


def bloco_limitacoes(dossie: Dossie, largura: float) -> list:
    e = estilos()
    metodo = dossie.metodo
    if metodo.vazio:
        return [Paragraph(
            "O registro de método não foi localizado, e as limitações declaradas no dia "
            "do exame não puderam ser reproduzidas.",
            e["corpo"],
        )]
    elementos = []
    if not metodo.tem_limitacao:
        elementos.append(Paragraph("Os módulos empregados não declararam limitações.", e["corpo"]))
    else:
        elementos.append(Paragraph(
            "As limitações abaixo são do <b>método</b>, não deste dispositivo em "
            "particular. Constam para que a ausência de um dado no material coletado "
            "não seja interpretada como ausência do dado no dispositivo examinado.",
            e["corpo"],
        ))
        for modulo in metodo.modulos:
            if not modulo.limitacoes:
                continue
            itens = "".join(f"<br/>• {escapar(texto)}" for texto in modulo.limitacoes)
            elementos += [Spacer(1, 4), Paragraph(
                f"<b>{escapar(modulo.nome)}</b>{itens}", e["esquerda"]
            )]

    if metodo.tem_alteracao:
        elementos.append(Paragraph(
            "Alterações que a coleta podia provocar no dispositivo", e["subsecao"]
        ))
        # Dois módulos podem declarar a mesma alteração (a via de backup é
        # comum a SMS e chamadas); impressa duas vezes, pareceriam duas.
        ja_impressas = set()
        for modulo in metodo.modulos:
            for alteracao, justificativa in modulo.alteracoes:
                if (alteracao, justificativa) in ja_impressas:
                    continue
                ja_impressas.add((alteracao, justificativa))
                elementos.append(Paragraph(
                    f"• {escapar(alteracao)}<br/><i>Justificativa: {escapar(justificativa)}</i>",
                    e["esquerda"],
                ))
    return elementos


def bloco_alteracoes_ocorridas(dossie: Dossie, largura: float) -> list:
    """O que o registro anotou como alteração e como decisão, no momento em que ocorreu."""
    e = estilos()
    elementos = []
    for titulo, rotulo, vazio in (
        ("ALTERAÇÃO NO DISPOSITIVO EXAMINADO", "Alterações registradas no dispositivo",
         "Nenhuma alteração no dispositivo foi anotada no registro do procedimento."),
        ("DECISÃO METODOLÓGICA", "Decisões metodológicas registradas",
         "Nenhuma decisão metodológica foi anotada no registro do procedimento."),
    ):
        elementos.append(Paragraph(rotulo, e["subsecao"]))
        eventos = dossie.eventos_com(titulo)
        if not eventos:
            elementos.append(Paragraph(vazio, e["corpo"]))
            continue
        elementos.append(tabela(
            ["Momento", "Registro"],
            [[escapar(carimbo_legivel(ev.carimbo)), escapar(ev.texto)] for ev in eventos],
            [largura * 0.24, largura * 0.76],
        ))
    return elementos


def bloco_linha_do_tempo(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.eventos:
        return [Paragraph(
            "O registro do procedimento desta aquisição não foi localizado ou não tem "
            "entradas.", e["corpo"],
        )]
    linhas = [
        [escapar(carimbo_legivel(ev.carimbo)), escapar(ev.titulo.title()), escapar(ev.texto)]
        for ev in dossie.eventos
    ]
    return [tabela(["Momento", "Evento", "Registro"], linhas,
                   [largura * 0.2, largura * 0.22, largura * 0.58])]


# ---------------------------------------------------------------------------
# Desfecho
# ---------------------------------------------------------------------------
def bloco_desfecho(dossie: Dossie, largura: float) -> list:
    e = estilos()
    desfecho = dossie.desfecho
    if desfecho.vazio:
        return [Paragraph(
            "O registro de desfecho desta aquisição não foi localizado. Não é possível "
            "reproduzir aqui, a partir do que foi selado, o que cada módulo obteve.",
            e["corpo"],
        )]
    linhas = []
    for modulo in desfecho.modulos:
        detalhe = escapar(modulo.mensagem)
        if modulo.ressalvas:
            detalhe += "".join(f"<br/>• {escapar(r)}" for r in modulo.ressalvas)
        linhas.append([escapar(modulo.nome), f"<b>{escapar(modulo.rotulo)}</b>", detalhe])
    return [
        Paragraph(escapar(desfecho.resumo), e["corpo"]),
        Spacer(1, 5),
        tabela(["Módulo", "Situação", "Resultado"], linhas,
               [largura * 0.26, largura * 0.18, largura * 0.56]),
        Spacer(1, 3),
        Paragraph(
            "'Concluído com ressalva' não equivale a 'Concluído': o módulo obteve parte "
            "do material e declarou o que não alcançou. 'Não obteve dado' significa que "
            "aquele material não foi adquirido — não que ele inexista no dispositivo.",
            e["nota"],
        ),
    ]


# ---------------------------------------------------------------------------
# Conteúdo interpretado
# ---------------------------------------------------------------------------
def periodo_do_artefato(artefato) -> str:
    momentos = [r.momento for r in artefato.resultado.registros if r.momento] if artefato.resultado else []
    if not momentos:
        return ""
    return f"{min(momentos).strftime('%d/%m/%Y')} a {max(momentos).strftime('%d/%m/%Y')}"


def situacao_do_artefato(artefato) -> str:
    if not artefato.presente:
        return ("NÃO COLETADO — o módulo correspondente não foi executado ou não obteve o "
                "material. Não é ausência de dado no dispositivo.")
    if artefato.total:
        return f"{artefato.total} registro(s)"
    return f"Nenhum registro — {artefato.explicacao}"


def bloco_conteudo(artefatos, largura: float, nome_do_fuso: str) -> list:
    e = estilos()
    if not artefatos:
        return [Paragraph(
            "O conteúdo desta aquisição não foi interpretado para este documento.", e["corpo"]
        )]
    linhas = []
    for artefato in artefatos:
        conferencia = {True: "confere com o selo", False: "<b>DIVERGE do selo</b>",
                       None: "sem selo a comparar"}[artefato.confere_com_o_selo]
        if artefato.presente:
            origem = f"{escapar(artefato.caminho_relativo)}<br/>{conferencia}"
        else:
            # Para o que não foi coletado, o caminho é onde se PROCUROU.
            origem = f"<i>procurado em:</i> {escapar(artefato.caminho_relativo)}"
        descartes = len(artefato.resultado.descartes) if artefato.resultado else 0
        situacao = escapar(situacao_do_artefato(artefato))
        if descartes:
            situacao += f"<br/><b>{descartes} trecho(s) NÃO interpretado(s)</b>"
        if getattr(artefato, "nota_da_fonte", ""):
            situacao += f"<br/><b>Atenção:</b> {escapar(artefato.nota_da_fonte)}"
        linhas.append([escapar(artefato.titulo), situacao,
                       escapar(periodo_do_artefato(artefato)), origem])
    return [
        tabela(["Artefato", "Situação", "Período", "Origem na aquisição"], linhas,
               [largura * 0.2, largura * 0.36, largura * 0.16, largura * 0.28]),
        Spacer(1, 3),
        Paragraph(
            f"Datas convertidas para {escapar(nome_do_fuso)}. O conteúdo é interpretação "
            "do material bruto, que permanece intocado sob o selo; o registro por "
            "registro está no Relatório de Conteúdo. Trecho "
            "não interpretado significa que o documento está incompleto em relação à "
            "evidência naquele ponto.",
            e["nota"],
        ),
    ]


def bloco_analise_do_conteudo(artefatos, largura: float) -> list:
    """
    Por artefato com registros: sentido das comunicações e interlocutores
    mais frequentes.

    A coluna do nome traz o que o PRÓPRIO registro carrega. Este bloco não
    cruza os números com a agenda: chamá-la de "nome na agenda" faria um
    travessão ser lido como "não consta na agenda", o que ninguém verificou.
    """
    e = estilos()
    elementos = []
    for artefato in artefatos:
        if not artefato.total:
            continue
        registros = artefato.resultado.registros
        partes = [f"<b>{escapar(artefato.titulo)}</b> — {artefato.total} registro(s)"]
        periodo = periodo_do_artefato(artefato)
        if periodo:
            partes.append(f"período de {periodo}")
        sentidos = Counter(str(r.campos.get("direcao") or "").strip() for r in registros)
        sentidos.pop("", None)
        if sentidos:
            partes.append("; ".join(f"{quantos} {sentido}" for sentido, quantos in sentidos.most_common()))
        elementos.append(Paragraph("; ".join(partes) + ".", e["esquerda"]))

        chave = "conversa" if "conversa" in artefato.colunas else (
            "numero" if "numero" in artefato.colunas else ("de" if "de" in artefato.colunas else "")
        )
        if chave and artefato.chave != "contato":
            frequentes = Counter(str(r.campos.get(chave) or "").strip() for r in registros)
            frequentes.pop("", None)
            if frequentes:
                nomes = {}
                for r in registros:
                    nome = str(r.campos.get("contato") or "").strip()
                    if nome:
                        nomes.setdefault(str(r.campos.get(chave) or "").strip(), nome)
                linhas = [
                    [escapar(valor), escapar(nomes.get(valor, "") if chave == "numero" else ""),
                     str(quantos)]
                    for valor, quantos in frequentes.most_common(10)
                ]
                rotulo = {"conversa": "Conversa", "numero": "Número", "de": "Remetente"}[chave]
                elementos += [Spacer(1, 3), tabela(
                    [f"{rotulo} (10 mais frequentes)", "Nome no próprio registro", "Registros"], linhas,
                    [largura * 0.5, largura * 0.34, largura * 0.16],
                )]
        elementos.append(Spacer(1, 8))
    if not elementos:
        elementos.append(Paragraph(
            "Nenhum artefato de comunicação com registros foi interpretado nesta aquisição.",
            e["corpo"],
        ))
    return elementos


# ---------------------------------------------------------------------------
# Integridade e inventário
# ---------------------------------------------------------------------------
def bloco_integridade(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.manifesto is None:
        return [Paragraph(
            "Esta aquisição não possui manifesto de integridade. Nada se pode afirmar "
            "aqui sobre a preservação do material: a ausência do selo impede a verificação.",
            e["alerta"],
        )]
    elementos = [
        tabela_de_pares([
            ("Algoritmo", "SHA-256"),
            ("Manifesto", escapar(dossie.manifesto.name)),
            ("Arquivos cobertos pelo selo", str(dossie.total_de_arquivos)),
            ("Volume coberto pelo selo",
             f"{tamanho_legivel(dossie.total_de_bytes)} ({dossie.total_de_bytes} bytes)"),
            ("SHA-256 do manifesto", Paragraph(escapar(dossie.sha256_do_manifesto), e["mono"])),
            ("Última conferência registrada",
             escapar(dossie.ultima_conferencia) if dossie.ultima_conferencia
             else "<i>nenhuma conferência posterior à coleta foi registrada — isso não "
                  "indica problema, indica que a verificação ainda não foi executada</i>"),
        ], largura),
        Spacer(1, 3),
        Paragraph(
            "O manifesto registra o hash individual de cada arquivo adquirido, calculado "
            "no encerramento da aquisição. O valor acima é o hash do próprio manifesto: "
            "alterar qualquer arquivo, ou o próprio selo, muda esse número. Ele consta "
            "também do rodapé de cada página deste documento.",
            e["nota"],
        ),
    ]
    if dossie.ausentes_no_disco:
        elementos += [Spacer(1, 4), Paragraph(
            f"ATENÇÃO: {len(dossie.ausentes_no_disco)} arquivo(s) listado(s) no manifesto "
            "não foram encontrados em disco no momento da emissão deste documento. "
            "Execute a conferência de integridade.",
            e["alerta"],
        )]
    return elementos


def bloco_inventario(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.hashes:
        return [Paragraph("Sem manifesto, o material não pôde ser inventariado.", e["corpo"])]
    linhas = [
        [escapar(nome), str(arquivos), tamanho_legivel(tamanho)]
        for nome, arquivos, tamanho in dossie.inventario
    ]
    linhas.append([
        "<b>Total</b>", f"<b>{dossie.total_de_arquivos}</b>",
        f"<b>{tamanho_legivel(dossie.total_de_bytes)}</b>",
    ])
    return [tabela(["Pasta da aquisição", "Arquivos", "Volume"], linhas,
                   [largura * 0.6, largura * 0.18, largura * 0.22])]


def bloco_arquivos_por_categoria(dossie: Dossie, largura: float) -> list:
    """
    Os arquivos adquiridos, contados e listados por categoria.

    A tabela mostra TODAS as categorias, inclusive as que não têm arquivo:
    linha omitida seria lida como "não se olhou", e zero impresso diz "não
    há arquivo com essa extensão no que foi adquirido".
    """
    e = estilos()
    if not dossie.hashes:
        return [Paragraph(
            "Sem manifesto, os arquivos adquiridos não puderam ser relacionados.", e["corpo"]
        )]
    categorias = dossie.categorias
    total = sum(categoria.quantidade for categoria in categorias)
    volume = sum(categoria.volume for categoria in categorias)
    if not total:
        return [Paragraph(
            "Nenhum arquivo foi adquirido além dos registros da própria aquisição.", e["corpo"]
        )]

    linhas = [
        [escapar(categoria.nome), str(categoria.quantidade), tamanho_legivel(categoria.volume)]
        for categoria in categorias
    ]
    linhas.append(["<b>Total</b>", f"<b>{total}</b>", f"<b>{tamanho_legivel(volume)}</b>"])
    elementos = [
        tabela(["Categoria", "Arquivos", "Volume"], linhas,
               [largura * 0.6, largura * 0.18, largura * 0.22]),
        Spacer(1, 3),
        Paragraph(
            "A categoria vem da EXTENSÃO do nome do arquivo, não da análise do conteúdo: "
            "zero numa categoria significa que nenhum arquivo adquirido tem essa extensão, "
            "e não que não exista conteúdo desse tipo. Os arquivos permanecem onde foram "
            "adquiridos, sob o selo, com o caminho abaixo. Não entram aqui os registros da "
            "própria aquisição (procedimento, método, desfecho, fotos da peça). Saídas de "
            "comando gravadas pelos módulos aparecem como texto.",
            e["nota"],
        ),
    ]

    for categoria in categorias:
        if not categoria.quantidade:
            continue
        elementos.append(Paragraph(
            f"{escapar(categoria.nome)} — {categoria.quantidade} arquivo(s), "
            f"{tamanho_legivel(categoria.volume)}",
            e["subsecao"],
        ))
        arquivos = categoria.arquivos
        if len(arquivos) > LIMITE_DE_ARQUIVOS_POR_CATEGORIA:
            elementos.append(Paragraph(
                f"Relacionados os {LIMITE_DE_ARQUIVOS_POR_CATEGORIA} primeiros, em ordem "
                f"alfabética de caminho, de {len(arquivos)}. A relação completa, com o hash "
                f"de cada arquivo, está em {escapar(dossie.manifesto.name)}.",
                e["nota"],
            ))
            arquivos = arquivos[:LIMITE_DE_ARQUIVOS_POR_CATEGORIA]
        elementos.append(tabela(
            ["Arquivo (caminho na aquisição)", "Bytes", "SHA-256"],
            [
                [Paragraph(escapar(caminho), e["mono_pequeno"]),
                 Paragraph(str(tamanho), e["mono_pequeno"]),
                 Paragraph(escapar(dossie.hashes.get(caminho, "")), e["mono_pequeno"])]
                for caminho, tamanho in arquivos
            ],
            [largura * 0.38, largura * 0.1, largura * 0.52],
        ))
    return elementos


def bloco_manifesto(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.hashes:
        return [Paragraph("Não há manifesto a reproduzir.", e["corpo"])]
    itens = sorted(dossie.hashes.items())
    elementos = []
    if len(itens) > LIMITE_DE_LINHAS_DO_MANIFESTO:
        elementos += [Paragraph(
            f"O manifesto cobre {len(itens)} arquivos. São reproduzidos abaixo os "
            f"{LIMITE_DE_LINHAS_DO_MANIFESTO} primeiros, em ordem alfabética de caminho; a "
            f"relação completa está em {escapar(dossie.manifesto.name)}, na pasta da "
            "aquisição, e é ele — não esta reprodução — que o hash do rodapé sela.",
            e["corpo"],
        ), Spacer(1, 5)]
        itens = itens[:LIMITE_DE_LINHAS_DO_MANIFESTO]
    linhas = [
        [Paragraph(escapar(caminho), e["mono_pequeno"]),
         Paragraph(str(dossie.tamanhos.get(caminho, "—")), e["mono_pequeno"]),
         Paragraph(escapar(valor), e["mono_pequeno"])]
        for caminho, valor in itens
    ]
    elementos.append(tabela(["Arquivo", "Bytes", "SHA-256"], linhas,
                            [largura * 0.37, largura * 0.11, largura * 0.52]))
    return elementos


# ---------------------------------------------------------------------------
# Protocolos (ABNT NBR ISO/IEC 27037)
# ---------------------------------------------------------------------------
def bloco_protocolos_da_ferramenta(dossie: Dossie, largura: float) -> list:
    e = estilos()
    linhas = [
        [escapar(clausula), escapar(pergunta), f"<b>{escapar(resposta)}</b>", escapar(origem)]
        for clausula, pergunta, resposta, origem in verificar_automaticos(dossie.pasta)
    ]
    return [
        Paragraph(
            "Requisitos da ABNT NBR ISO/IEC 27037:2013 que a própria ferramenta comprova, "
            "cada um com o registro que sustenta a resposta.", e["corpo"],
        ),
        Spacer(1, 4),
        tabela(["Cláusula", "Requisito", "Resposta", "Registro"], linhas,
               [largura * 0.1, largura * 0.45, largura * 0.2, largura * 0.25]),
    ]


def bloco_protocolos_do_examinador(protocolos, observacoes: str, largura: float) -> list:
    e = estilos()
    if not protocolos:
        return [Paragraph(
            "Os protocolos que dependem do examinador não foram respondidos para este "
            "documento.", e["corpo"],
        )]
    linhas = []
    for item in protocolos:
        clausula, pergunta, resposta, observacao = desdobrar(item)
        if resposta == "Sim" and not observacao and exige_especificacao(pergunta):
            resposta = "Sim — não especificado"
        linhas.append([escapar(clausula), escapar(pergunta), f"<b>{escapar(resposta)}</b>",
                       escapar(observacao)])
    elementos = [
        Paragraph(
            "Circunstâncias do exame que só quem o realizou observou. São declarações de "
            "fato, e não aferição de conformidade: 'Não' não indica irregularidade.",
            e["corpo"],
        ),
        Spacer(1, 4),
        tabela(["Cláusula", "Questão", "Resposta", "Observação"], linhas,
               [largura * 0.1, largura * 0.42, largura * 0.2, largura * 0.28]),
    ]
    if (observacoes or "").strip():
        elementos += [Spacer(1, 5), Paragraph(
            f"<b>Observações do examinador:</b> {escapar(observacoes)}", e["esquerda"]
        )]
    return elementos


def secao(titulo: str, elementos: List) -> list:
    """Título de seção colado ao primeiro elemento, para não ficar órfão no pé da página."""
    e = estilos()
    cabeca = Paragraph(escapar(titulo), e["secao"])
    if not elementos:
        return [cabeca]
    return [KeepTogether([cabeca, elementos[0]])] + list(elementos[1:])
