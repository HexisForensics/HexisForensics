"""
Blocos de conteúdo compartilhados pelo Relatório de Extração e pelo Laudo
Pericial.

Cada função recebe o dossiê da aquisição e devolve uma lista de elementos
prontos para a página. A regra é a de toda a suíte: **o documento não
afirma o que a ferramenta não verificou**. Quando o registro necessário
não existe, o bloco diz isso por extenso, em vez de omitir a seção ou de
preenchê-la com suposição — seção ausente seria lida como "nada a
declarar", que é outra afirmação.

Documento DERIVADO: o texto dos blocos é resolvido por `traduzir` no idioma
ativo. O que é DADO — hashes, caminhos, valores do dossiê, nomes/rótulos
vindos do core, respostas de protocolo — NÃO se traduz. As chaves de busca
no registro SELADO (ex.: "AFERIÇÃO DE RELÓGIO") também ficam em português:
são o que foi gravado sob o selo, não texto de tela.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from core.aparelho import IDENTIFICADORES_GENERICOS
from core.categorias import nome_no_idioma as nome_categoria_no_idioma
from core.idioma import traduzir
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


def _ou_nao_informado(valor: str) -> str:
    return escapar(valor) if str(valor or "").strip() else traduzir("bl_nao_informado")


# ---------------------------------------------------------------------------
# Identificação
# ---------------------------------------------------------------------------
def texto_do_operador(dossie: Dossie) -> str:
    if dossie.operador is None:
        return traduzir("bl_operador_nao_registrado")
    return dossie.operador.resumo()


def bloco_identificacao(dossie: Dossie, largura: float) -> list:
    pares = [(traduzir("bl_id_caso"), escapar(dossie.caso))]
    pares += [(rotulo, _ou_nao_informado(valor)) for rotulo, valor in dossie.dados_do_caso]
    pares += [
        (traduzir("bl_id_aquisicao"), escapar(dossie.pasta.name)),
        (traduzir("bl_id_plataforma"), _ou_nao_informado(dossie.plataforma)),
        (traduzir("bl_id_inicio"), _ou_nao_informado(carimbo_legivel(dossie.abertura))),
        (traduzir("bl_id_encerramento"), _ou_nao_informado(carimbo_legivel(dossie.encerramento))),
        (traduzir("bl_id_operador"), escapar(texto_do_operador(dossie))),
        (traduzir("bl_id_conta"), _ou_nao_informado(dossie.conta_da_estacao)),
    ]
    elementos = [tabela_de_pares(pares, largura)]
    e = estilos()
    if not dossie.tem_cadeia_de_custodia:
        elementos += [Spacer(1, 4), Paragraph(traduzir("bl_id_sem_cadeia"), e["alerta"])]
    if dossie.operador is not None and not dossie.operador.declarado:
        elementos += [Spacer(1, 4), Paragraph(
            traduzir("bl_id_nao_declarado", valor=NAO_DECLARADO), e["nota"])]
    elif dossie.operador is not None and dossie.de_teste:
        elementos += [Spacer(1, 4), Paragraph(traduzir("bl_id_teste"), e["alerta"])]
    elif dossie.operador is not None and dossie.operador.autenticacao.strip():
        elementos += [Spacer(1, 4), Paragraph(traduzir("bl_id_auth_senha"), e["nota"])]
    elif dossie.operador is not None:
        elementos += [Spacer(1, 4), Paragraph(traduzir("bl_id_declarado"), e["nota"])]
    return elementos


# ---------------------------------------------------------------------------
# Peça examinada
# ---------------------------------------------------------------------------
def bloco_peca(dossie: Dossie, largura: float, sem_caracteristicas: str = "") -> list:
    e = estilos()
    elementos = [Paragraph(traduzir("bl_peca_declarado"), e["subsecao"])]
    if dossie.tem_cadeia_de_custodia:
        elementos.append(tabela_de_pares(
            [(rotulo, _ou_nao_informado(valor)) for rotulo, valor in dossie.peca], largura
        ))
    else:
        elementos.append(Paragraph(traduzir("bl_peca_sem_cadeia"), e["corpo"]))

    elementos.append(Paragraph(traduzir("bl_peca_apurado"), e["subsecao"]))
    pares = list(dossie.apuradas)
    # O nome genérico ("celular_android") é dado quando nenhum aparelho
    # respondeu: não foi lido do dispositivo e não entra como apurado.
    if (dossie.identificador_do_dispositivo
            and dossie.identificador_do_dispositivo not in IDENTIFICADORES_GENERICOS):
        pares.insert(0, (
            traduzir("bl_peca_identificador"), dossie.identificador_do_dispositivo
        ))
    if dossie.desvio_do_relogio is not None:
        pares.append((traduzir("bl_peca_relogio"),
                      traduzir("bl_peca_sem_desvio") if dossie.desvio_do_relogio == 0
                      else traduzir("bl_peca_desvio_de", valor=descrever_desvio(dossie.desvio_do_relogio))))
    if pares:
        elementos.append(tabela_de_pares(
            [(rotulo, escapar(valor)) for rotulo, valor in pares], largura
        ))
        if alerta_do_relogio(dossie.desvio_do_relogio):
            elementos += [Spacer(1, 3), Paragraph(
                escapar(alerta_do_relogio(dossie.desvio_do_relogio)), e["alerta"])]
        elementos += [Spacer(1, 3), Paragraph(traduzir("bl_peca_nota"), e["nota"])]
    else:
        elementos.append(Paragraph(
            sem_caracteristicas or traduzir("bl_sem_caracteristicas"), e["corpo"]))
    return elementos


def bloco_fotos(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.fotos:
        return [Paragraph(traduzir("bl_fotos_nenhuma"), e["corpo"])]

    celulas = []
    for indice, foto in enumerate(dossie.fotos, 1):
        imagem = imagem_ajustada(foto, largura / 2 - 14, 190)
        sha = escapar(dossie.hashes.get(
            foto.relative_to(dossie.pasta).as_posix(), traduzir("bl_fotos_fora_manifesto")))
        legenda = Paragraph(
            traduzir("bl_fotos_legenda", n=indice, nome=escapar(foto.name), sha=sha),
            e["mono_pequeno"],
        )
        if imagem is None:
            # Imagem ilegível é fato a declarar, não a omitir.
            celulas.append([Paragraph(
                traduzir("bl_fotos_ilegivel", n=indice, nome=escapar(foto.name)), e["alerta"]
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
        elementos += [Spacer(1, 3), Paragraph(traduzir("bl_ambiente_nota"), e["nota"])]
    else:
        elementos.append(Paragraph(traduzir("bl_ambiente_sem"), e["corpo"]))

    relogio = dossie.evento("relogio")  # tipo canônico; resolve no idioma do caso
    elementos.append(Paragraph(traduzir("bl_ambiente_relogio_titulo"), e["subsecao"]))
    if relogio:
        elementos.append(Paragraph(escapar(relogio.texto), e["esquerda"]))
    else:
        elementos.append(Paragraph(traduzir("bl_ambiente_sem_relogio"), e["corpo"]))
    return elementos


def bloco_autorizacao(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.autorizacao.vazia:
        return [Paragraph(traduzir("bl_auth_nenhuma"), e["corpo"])]
    linhas = [
        [escapar(d.rotulo), escapar(getattr(d.arquivo, "name", d.arquivo)),
         Paragraph(escapar(d.sha256), e["mono_pequeno"]), escapar(carimbo_legivel(d.juntado_em))]
        for d in dossie.autorizacao.documentos
    ]
    return [
        tabela([traduzir("bl_auth_h_documento"), traduzir("bl_auth_h_arquivo"),
                traduzir("bl_auth_h_sha"), traduzir("bl_auth_h_anexado")], linhas,
               [largura * 0.2, largura * 0.22, largura * 0.4, largura * 0.18]),
        Spacer(1, 3),
        Paragraph(traduzir("bl_auth_nota"), e["nota"]),
    ]


def bloco_metodo(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.metodo.vazio:
        return [Paragraph(traduzir("bl_metodo_vazio"), e["corpo"])]
    linhas = [[escapar(m.nome), escapar(m.perfil)] for m in dossie.metodo.modulos]
    return [tabela([traduzir("bl_metodo_h_modulo"), traduzir("bl_metodo_h_competencia")], linhas,
                   [largura * 0.68, largura * 0.32])]


def bloco_limitacoes(dossie: Dossie, largura: float) -> list:
    e = estilos()
    metodo = dossie.metodo
    if metodo.vazio:
        return [Paragraph(traduzir("bl_lim_vazio"), e["corpo"])]
    elementos = []
    if not metodo.tem_limitacao:
        elementos.append(Paragraph(traduzir("bl_lim_sem"), e["corpo"]))
    else:
        elementos.append(Paragraph(traduzir("bl_lim_intro"), e["corpo"]))
        for modulo in metodo.modulos:
            if not modulo.limitacoes:
                continue
            itens = "".join(f"<br/>• {escapar(texto)}" for texto in modulo.limitacoes)
            elementos += [Spacer(1, 4), Paragraph(
                f"<b>{escapar(modulo.nome)}</b>{itens}", e["esquerda"]
            )]

    if metodo.tem_alteracao:
        elementos.append(Paragraph(traduzir("bl_lim_alteracoes_titulo"), e["subsecao"]))
        justificativa_label = traduzir("bl_lim_justificativa_label")
        # Dois módulos podem declarar a mesma alteração (a via de backup é
        # comum a SMS e chamadas); impressa duas vezes, pareceriam duas.
        ja_impressas = set()
        for modulo in metodo.modulos:
            for alteracao, justificativa in modulo.alteracoes:
                if (alteracao, justificativa) in ja_impressas:
                    continue
                ja_impressas.add((alteracao, justificativa))
                elementos.append(Paragraph(
                    f"• {escapar(alteracao)}<br/><i>{justificativa_label} {escapar(justificativa)}</i>",
                    e["esquerda"],
                ))
    return elementos


def bloco_alteracoes_ocorridas(dossie: Dossie, largura: float) -> list:
    """O que o registro anotou como alteração e como decisão, no momento em que ocorreu."""
    e = estilos()
    elementos = []
    # (tipo canônico do evento SELADO, chave do rótulo, chave do vazio).
    for tipo, rotulo_key, vazio_key in (
        ("alteracao", "bl_alt_rotulo", "bl_alt_vazio"),
        ("decisao", "bl_dec_rotulo", "bl_dec_vazio"),
    ):
        elementos.append(Paragraph(traduzir(rotulo_key), e["subsecao"]))
        eventos = dossie.eventos_com(tipo)
        if not eventos:
            elementos.append(Paragraph(traduzir(vazio_key), e["corpo"]))
            continue
        elementos.append(tabela(
            [traduzir("bl_h_momento"), traduzir("bl_h_registro")],
            [[escapar(carimbo_legivel(ev.carimbo)), escapar(ev.texto)] for ev in eventos],
            [largura * 0.24, largura * 0.76],
        ))
    return elementos


def bloco_linha_do_tempo(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.eventos:
        return [Paragraph(traduzir("bl_tempo_vazio"), e["corpo"])]
    linhas = [
        [escapar(carimbo_legivel(ev.carimbo)), escapar(ev.titulo.title()), escapar(ev.texto)]
        for ev in dossie.eventos
    ]
    return [tabela([traduzir("bl_h_momento"), traduzir("bl_h_evento"), traduzir("bl_h_registro")],
                   linhas, [largura * 0.2, largura * 0.22, largura * 0.58])]


# ---------------------------------------------------------------------------
# Desfecho
# ---------------------------------------------------------------------------
def bloco_desfecho(dossie: Dossie, largura: float) -> list:
    e = estilos()
    desfecho = dossie.desfecho
    if desfecho.vazio:
        return [Paragraph(traduzir("bl_desfecho_vazio"), e["corpo"])]
    linhas = []
    for modulo in desfecho.modulos:
        detalhe = escapar(modulo.mensagem)
        if modulo.ressalvas:
            detalhe += "".join(f"<br/>• {escapar(r)}" for r in modulo.ressalvas)
        linhas.append([escapar(modulo.nome), f"<b>{escapar(modulo.rotulo)}</b>", detalhe])
    return [
        Paragraph(escapar(desfecho.resumo), e["corpo"]),
        Spacer(1, 5),
        tabela([traduzir("bl_desfecho_h_modulo"), traduzir("bl_desfecho_h_situacao"),
                traduzir("bl_desfecho_h_resultado")], linhas,
               [largura * 0.26, largura * 0.18, largura * 0.56]),
        Spacer(1, 3),
        Paragraph(traduzir("bl_desfecho_nota"), e["nota"]),
    ]


# ---------------------------------------------------------------------------
# Conteúdo interpretado
# ---------------------------------------------------------------------------
def periodo_do_artefato(artefato) -> str:
    momentos = [r.momento for r in artefato.resultado.registros if r.momento] if artefato.resultado else []
    if not momentos:
        return ""
    return traduzir("bl_periodo_a", inicio=min(momentos).strftime('%d/%m/%Y'),
                    fim=max(momentos).strftime('%d/%m/%Y'))


def situacao_do_artefato(artefato) -> str:
    if not artefato.presente:
        return traduzir("bl_art_nao_coletado")
    if artefato.total:
        return traduzir("bl_art_registros", n=artefato.total)
    return traduzir("bl_art_nenhum_registro", explicacao=artefato.explicacao)


def bloco_conteudo(artefatos, largura: float, nome_do_fuso: str) -> list:
    e = estilos()
    if not artefatos:
        return [Paragraph(traduzir("bl_conteudo_nao_interpretado"), e["corpo"])]
    linhas = []
    for artefato in artefatos:
        conferencia = {True: traduzir("bl_conf_confere"), False: traduzir("bl_conf_diverge"),
                       None: traduzir("bl_conf_sem_selo")}[artefato.confere_com_o_selo]
        if artefato.presente:
            origem = f"{escapar(artefato.caminho_relativo)}<br/>{conferencia}"
        else:
            # Para o que não foi coletado, o caminho é onde se PROCUROU.
            origem = traduzir("bl_conteudo_procurado", valor=escapar(artefato.caminho_relativo))
        descartes = len(artefato.resultado.descartes) if artefato.resultado else 0
        situacao = escapar(situacao_do_artefato(artefato))
        if descartes:
            situacao += "<br/><b>" + traduzir("bl_conteudo_descartes", n=descartes) + "</b>"
        if getattr(artefato, "nota_da_fonte", ""):
            situacao += f"<br/><b>{traduzir('bl_conteudo_atencao')}</b> {escapar(artefato.nota_da_fonte)}"
        linhas.append([escapar(artefato.titulo), situacao,
                       escapar(periodo_do_artefato(artefato)), origem])
    return [
        tabela([traduzir("bl_conteudo_h_artefato"), traduzir("bl_conteudo_h_situacao"),
                traduzir("bl_conteudo_h_periodo"), traduzir("bl_conteudo_h_origem")], linhas,
               [largura * 0.2, largura * 0.36, largura * 0.16, largura * 0.28]),
        Spacer(1, 3),
        Paragraph(traduzir("bl_conteudo_nota", fuso=escapar(nome_do_fuso)), e["nota"]),
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
        partes = [f"<b>{escapar(artefato.titulo)}</b> — {traduzir('bl_art_registros', n=artefato.total)}"]
        periodo = periodo_do_artefato(artefato)
        if periodo:
            partes.append(traduzir("bl_analise_periodo", valor=periodo))
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
                rotulo = {"conversa": traduzir("bl_analise_rotulo_conversa"),
                          "numero": traduzir("bl_analise_rotulo_numero"),
                          "de": traduzir("bl_analise_rotulo_remetente")}[chave]
                elementos += [Spacer(1, 3), tabela(
                    [traduzir("bl_analise_h_freq", rotulo=rotulo), traduzir("bl_analise_h_nome"),
                     traduzir("bl_analise_h_registros")], linhas,
                    [largura * 0.5, largura * 0.34, largura * 0.16],
                )]
        elementos.append(Spacer(1, 8))
    if not elementos:
        elementos.append(Paragraph(traduzir("bl_analise_nenhum"), e["corpo"]))
    return elementos


# ---------------------------------------------------------------------------
# Integridade e inventário
# ---------------------------------------------------------------------------
def bloco_integridade(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if dossie.manifesto is None:
        return [Paragraph(traduzir("bl_integ_sem_manifesto"), e["alerta"])]
    elementos = [
        tabela_de_pares([
            (traduzir("bl_integ_algoritmo"), "SHA-256"),
            (traduzir("bl_integ_manifesto"), escapar(dossie.manifesto.name)),
            (traduzir("bl_integ_arquivos_cobertos"), str(dossie.total_de_arquivos)),
            (traduzir("bl_integ_volume_coberto"),
             traduzir("bl_integ_volume_valor",
                      legivel=tamanho_legivel(dossie.total_de_bytes), bytes=dossie.total_de_bytes)),
            (traduzir("bl_integ_sha"), Paragraph(escapar(dossie.sha256_do_manifesto), e["mono"])),
            (traduzir("bl_integ_ultima_conf"),
             escapar(dossie.ultima_conferencia) if dossie.ultima_conferencia
             else traduzir("bl_integ_sem_conf")),
        ], largura),
        Spacer(1, 3),
        Paragraph(traduzir("bl_integ_nota"), e["nota"]),
    ]
    if dossie.ausentes_no_disco:
        elementos += [Spacer(1, 4), Paragraph(
            traduzir("bl_integ_ausentes", n=len(dossie.ausentes_no_disco)), e["alerta"])]
    return elementos


def bloco_inventario(dossie: Dossie, largura: float) -> list:
    e = estilos()
    if not dossie.hashes:
        return [Paragraph(traduzir("bl_inv_sem"), e["corpo"])]
    linhas = [
        [escapar(nome), str(arquivos), tamanho_legivel(tamanho)]
        for nome, arquivos, tamanho in dossie.inventario
    ]
    linhas.append([
        traduzir("bl_total"), f"<b>{dossie.total_de_arquivos}</b>",
        f"<b>{tamanho_legivel(dossie.total_de_bytes)}</b>",
    ])
    return [tabela([traduzir("bl_inv_h_pasta"), traduzir("bl_inv_h_arquivos"),
                    traduzir("bl_inv_h_volume")], linhas,
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
        return [Paragraph(traduzir("bl_cat_sem"), e["corpo"])]
    categorias = dossie.categorias
    total = sum(categoria.quantidade for categoria in categorias)
    volume = sum(categoria.volume for categoria in categorias)
    if not total:
        return [Paragraph(traduzir("bl_cat_nenhum"), e["corpo"])]

    linhas = [
        [escapar(nome_categoria_no_idioma(categoria.nome, dossie.idioma)),
         str(categoria.quantidade), tamanho_legivel(categoria.volume)]
        for categoria in categorias
    ]
    linhas.append([traduzir("bl_total"), f"<b>{total}</b>", f"<b>{tamanho_legivel(volume)}</b>"])
    elementos = [
        tabela([traduzir("bl_cat_h_categoria"), traduzir("bl_inv_h_arquivos"),
                traduzir("bl_inv_h_volume")], linhas,
               [largura * 0.6, largura * 0.18, largura * 0.22]),
        Spacer(1, 3),
        Paragraph(traduzir("bl_cat_nota"), e["nota"]),
    ]

    for categoria in categorias:
        if not categoria.quantidade:
            continue
        elementos.append(Paragraph(
            traduzir("bl_cat_subsecao",
                     nome=escapar(nome_categoria_no_idioma(categoria.nome, dossie.idioma)),
                     n=categoria.quantidade, volume=tamanho_legivel(categoria.volume)),
            e["subsecao"],
        ))
        arquivos = categoria.arquivos
        if len(arquivos) > LIMITE_DE_ARQUIVOS_POR_CATEGORIA:
            elementos.append(Paragraph(
                traduzir("bl_cat_primeiros", limite=LIMITE_DE_ARQUIVOS_POR_CATEGORIA,
                         total=len(arquivos), manifesto=escapar(dossie.manifesto.name)),
                e["nota"],
            ))
            arquivos = arquivos[:LIMITE_DE_ARQUIVOS_POR_CATEGORIA]
        elementos.append(tabela(
            [traduzir("bl_cat_h_arquivo"), traduzir("bl_cat_h_bytes"), "SHA-256"],
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
        return [Paragraph(traduzir("bl_man_sem"), e["corpo"])]
    itens = sorted(dossie.hashes.items())
    elementos = []
    if len(itens) > LIMITE_DE_LINHAS_DO_MANIFESTO:
        elementos += [Paragraph(
            traduzir("bl_man_limite", n=len(itens), limite=LIMITE_DE_LINHAS_DO_MANIFESTO,
                     manifesto=escapar(dossie.manifesto.name)),
            e["corpo"],
        ), Spacer(1, 5)]
        itens = itens[:LIMITE_DE_LINHAS_DO_MANIFESTO]
    linhas = [
        [Paragraph(escapar(caminho), e["mono_pequeno"]),
         Paragraph(str(dossie.tamanhos.get(caminho, "—")), e["mono_pequeno"]),
         Paragraph(escapar(valor), e["mono_pequeno"])]
        for caminho, valor in itens
    ]
    elementos.append(tabela([traduzir("bl_man_h_arquivo"), "Bytes", "SHA-256"], linhas,
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
        Paragraph(traduzir("bl_prot_f_intro"), e["corpo"]),
        Spacer(1, 4),
        tabela([traduzir("bl_prot_h_clausula"), traduzir("bl_prot_h_requisito"),
                traduzir("bl_prot_h_resposta"), traduzir("bl_prot_h_registro")], linhas,
               [largura * 0.1, largura * 0.45, largura * 0.2, largura * 0.25]),
    ]


def bloco_protocolos_do_examinador(protocolos, observacoes: str, largura: float) -> list:
    e = estilos()
    if not protocolos:
        return [Paragraph(traduzir("bl_prot_e_vazio"), e["corpo"])]
    linhas = []
    for item in protocolos:
        clausula, pergunta, resposta, observacao = desdobrar(item)
        # A resposta vem do caderno/laudo em PT canônico (dado): não se traduz.
        if resposta == "Sim" and not observacao and exige_especificacao(pergunta):
            resposta = "Sim — não especificado"
        linhas.append([escapar(clausula), escapar(pergunta), f"<b>{escapar(resposta)}</b>",
                       escapar(observacao)])
    elementos = [
        Paragraph(traduzir("bl_prot_e_intro"), e["corpo"]),
        Spacer(1, 4),
        tabela([traduzir("bl_prot_h_clausula"), traduzir("bl_prot_e_h_questao"),
                traduzir("bl_prot_h_resposta"), traduzir("bl_prot_e_h_observacao")], linhas,
               [largura * 0.1, largura * 0.42, largura * 0.2, largura * 0.28]),
    ]
    if (observacoes or "").strip():
        elementos += [Spacer(1, 5), Paragraph(
            traduzir("bl_prot_e_observacoes", valor=escapar(observacoes)), e["esquerda"]
        )]
    return elementos


def secao(titulo: str, elementos: List) -> list:
    """Título de seção colado ao primeiro elemento, para não ficar órfão no pé da página."""
    e = estilos()
    cabeca = Paragraph(escapar(titulo), e["secao"])
    if not elementos:
        return [cabeca]
    return [KeepTogether([cabeca, elementos[0]])] + list(elementos[1:])
