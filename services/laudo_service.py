"""
Laudo Pericial do dispositivo, em PDF.

O laudo é ato de quem o assina. Por isso este serviço separa, em cada
seção, três origens que não podem se confundir:

- o que a FERRAMENTA registrou e sustenta com arquivo selado (ambiente,
  método, desfecho, selo, conteúdo interpretado);
- o que o EXAMINADOR declara neste ato (objetivo do exame, circunstâncias
  que só ele observou, considerações) — impresso como declaração dele;
- o que foi DIGITADO no cadastro (descrição da peça, lacre).

Todo número que o documento afirma vem de registro da aquisição — nunca
de constante escrita no código, nunca de frase fixa. A conclusão é
derivada do desfecho por módulo. **O laudo não afirma o que a ferramenta
não verificou**: quando o registro necessário não existe, a seção diz
isso, em vez de omitir ou de supor.

Fica FORA da aquisição selada, em `<caso>/documentos/`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table

from core import exame_sem_extracao
from core.idioma import traduzir
from core.normalizacao import nome_do_fuso
from core.operador import de_dicionario
from core.protocolos import exige_especificacao, perguntas_do_examinador
from services import blocos_pdf as blocos
from services import identidade_pdf as identidade
from services.dossie_service import carimbo_legivel, montar_dossie
from services.relatorio_extracao_service import (
    DocumentoGerado,
    destino_livre,
    fuso_da_estacao,
    pasta_de_documentos,
)
from services.relatorio_service import levantar_artefatos

PREFIXO = "Laudo_Pericial"


def perguntas_dos_protocolos() -> list:
    """
    (cláusula, pergunta) dos protocolos que dependem do examinador.

    Existe para que `ui/` monte o formulário sem importar nada de `core` —
    mesma razão de `opcoes_tipo_documento` em `services.case_service`.
    """
    return perguntas_do_examinador()


def protocolo_exige_especificacao(pergunta: str) -> bool:
    """`True` se a pergunta pede detalhamento na observação do item."""
    return exige_especificacao(pergunta)


def texto_da_conclusao(desfecho) -> str:
    """
    A conclusão que os fatos sustentam, e nenhuma além disso.

    Uma versão antiga era frase fixa afirmando que os dados haviam sido
    armazenados "de forma íntegra", mesmo quando módulos falhavam — o
    próprio caso desmentia o laudo.
    """
    if desfecho.vazio:
        return traduzir("ld_conc_vazio")

    if desfecho.integral:
        return traduzir("ld_conc_integral", resumo=desfecho.resumo)

    partes = [desfecho.resumo]
    if desfecho.cancelada:
        partes.append(traduzir("ld_conc_cancelada"))
    if desfecho.falharam:
        partes.append(traduzir("ld_conc_falharam"))
    if desfecho.com_ressalva:
        partes.append(traduzir("ld_conc_ressalva"))
    partes.append(traduzir("ld_conc_final"))
    return " ".join(partes)


def _data_por_extenso(momento: datetime) -> str:
    mes = traduzir(f"ld_mes_{momento.month:02d}")
    return traduzir("ld_data_extenso", dia=momento.day, mes=mes, ano=momento.year)


def _declaracao(texto: str, vazio: str, e) -> Paragraph:
    """Texto do examinador, ou a declaração de que ele não o informou."""
    texto = (texto or "").strip()
    if texto:
        return Paragraph(identidade.escapar(texto), e["corpo"])
    return Paragraph(f"<i>{vazio}</i>", e["corpo"])


def gerar(
    pasta_aquisicao: Path,
    dados_form: dict,
    examinador: Optional[dict] = None,
    destino: Optional[Path] = None,
    fuso="estacao",
) -> DocumentoGerado:
    """
    Gera o Laudo Pericial da aquisição.

    `dados_form` traz o que o examinador declara neste ato: `numero`,
    `objetivo`, `tipo_extracao`, `protocolos`, `observacoes`,
    `consideracoes`. `examinador` é o perfil de quem SUBSCREVE o laudo —
    que pode não ser quem operou a aquisição, e o laudo mostra os dois.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    if fuso == "estacao":
        fuso = fuso_da_estacao()

    exame = exame_sem_extracao.ler_exame(pasta_aquisicao)
    if exame is not None:
        return _gerar_sem_extracao(pasta_aquisicao, exame, dados_form, examinador, destino)

    try:
        dossie = montar_dossie(pasta_aquisicao)
        try:
            artefatos = levantar_artefatos(pasta_aquisicao, fuso)
            erro_do_conteudo = ""
        except Exception as erro:
            artefatos, erro_do_conteudo = [], str(erro)

        subscritor = de_dicionario(examinador or {})
        agora = datetime.now().astimezone()
        e = identidade.estilos()
        largura = identidade.largura_util()
        numero = (dados_form.get("numero") or "").strip()

        subtitulo = traduzir("ld_subtitulo") + (
            traduzir("ld_subtitulo_numero", numero=identidade.escapar(numero)) if numero else "")
        historia = [
            Spacer(1, 6),
            Paragraph(traduzir("ld_titulo"), e["titulo"]),
            Paragraph(subtitulo, e["subtitulo"]),
        ]

        def acrescentar(titulo, elementos):
            historia.extend(blocos.secao(titulo, elementos))

        # --- 1. PREÂMBULO -------------------------------------------------
        pares = [(traduzir("ld_l_caso"), identidade.escapar(dossie.caso))]
        pares += [
            (rotulo, identidade.escapar(valor) if valor else traduzir("bl_nao_informado"))
            for rotulo, valor in dossie.dados_do_caso
        ]
        pares += [
            (traduzir("ld_l_aquisicao_examinada"), identidade.escapar(pasta_aquisicao.name)),
            (traduzir("ld_l_data_aquisicao"),
             identidade.escapar(carimbo_legivel(dossie.abertura)) or traduzir("bl_nao_informado")),
            (traduzir("ld_l_operador_aquisicao"), identidade.escapar(blocos.texto_do_operador(dossie))),
            (traduzir("ld_l_examinador_subscreve"),
             identidade.escapar(subscritor.resumo()) if subscritor.declarado
             else traduzir("ld_perfil_nao_preenchido")),
            (traduzir("ld_l_data_emissao"), agora.strftime("%d/%m/%Y %H:%M:%S %z")),
        ]
        acrescentar(traduzir("ld_sec_1"), [
            identidade.tabela_de_pares(pares, largura),
            Spacer(1, 3),
            Paragraph(
                traduzir("ld_preambulo_nota_base")
                + (traduzir("ld_preambulo_nota_senha")
                   if dossie.operador is not None and dossie.operador.autenticacao.strip()
                   else traduzir("ld_preambulo_nota_declarado")),
                e["nota"],
            ),
        ])

        # --- 2. OBJETIVO --------------------------------------------------
        acrescentar(traduzir("ld_sec_2"), [_declaracao(
            dados_form.get("objetivo"), traduzir("ld_sem_objetivo"), e,
        )])

        # --- 3. MATERIAL EXAMINADO ---------------------------------------
        acrescentar(traduzir("ld_sec_3"), blocos.bloco_peca(dossie, largura))
        historia.append(Paragraph(traduzir("ld_sub_fotos"), e["subsecao"]))
        historia.extend(blocos.bloco_fotos(dossie, largura))
        historia.append(Paragraph(traduzir("ld_sub_autorizacao"), e["subsecao"]))
        historia.extend(blocos.bloco_autorizacao(dossie, largura))

        # --- 4. METODOLOGIA ----------------------------------------------
        metodologia = [
            Paragraph(traduzir("ld_metodo_intro"), e["corpo"]),
            Spacer(1, 5),
            identidade.tabela_de_pares([
                (traduzir("ld_l_modalidade"),
                 identidade.escapar(dados_form.get("tipo_extracao"))
                 if (dados_form.get("tipo_extracao") or "").strip()
                 else traduzir("ld_modalidade_vazia")),
            ], largura),
            Paragraph(traduzir("ld_sub_modulos"), e["subsecao"]),
        ]
        metodologia += blocos.bloco_metodo(dossie, largura)
        metodologia.append(Paragraph(traduzir("ld_sub_ambiente"), e["subsecao"]))
        metodologia += blocos.bloco_ambiente(dossie, largura)
        metodologia += blocos.bloco_alteracoes_ocorridas(dossie, largura)
        metodologia.append(Paragraph(traduzir("ld_sub_requisitos"), e["subsecao"]))
        metodologia += blocos.bloco_protocolos_da_ferramenta(dossie, largura)
        metodologia.append(Paragraph(traduzir("ld_sub_circunstancias"), e["subsecao"]))
        metodologia += blocos.bloco_protocolos_do_examinador(
            dados_form.get("protocolos") or [], dados_form.get("observacoes", ""), largura
        )
        acrescentar(traduzir("ld_sec_4"), metodologia)

        # --- 5. LIMITAÇÕES -----------------------------------------------
        acrescentar(traduzir("ld_sec_5"), blocos.bloco_limitacoes(dossie, largura))

        # --- 6. EXAMES E RESULTADOS --------------------------------------
        resultados = [Paragraph(traduzir("ld_sub_desfecho"), e["subsecao"])]
        resultados += blocos.bloco_desfecho(dossie, largura)
        resultados.append(Paragraph(traduzir("ld_sub_conteudo"), e["subsecao"]))
        if erro_do_conteudo:
            resultados.append(Paragraph(
                traduzir("ld_conteudo_erro", erro=identidade.escapar(erro_do_conteudo)),
                e["alerta"],
            ))
        else:
            resultados += blocos.bloco_conteudo(artefatos, largura, nome_do_fuso(fuso))
            resultados.append(Paragraph(traduzir("ld_sub_comunicacoes"), e["subsecao"]))
            resultados += blocos.bloco_analise_do_conteudo(artefatos, largura)
        resultados.append(Paragraph(traduzir("ld_sub_arquivos"), e["subsecao"]))
        resultados += blocos.bloco_arquivos_por_categoria(dossie, largura)
        resultados.append(Paragraph(traduzir("ld_sub_inventario"), e["subsecao"]))
        resultados += blocos.bloco_inventario(dossie, largura)
        acrescentar(traduzir("ld_sec_6"), resultados)

        # --- 7. CADEIA DE CUSTÓDIA E INTEGRIDADE -------------------------
        acrescentar(traduzir("ld_sec_7"), blocos.bloco_integridade(dossie, largura))

        # --- 8. CONCLUSÃO -------------------------------------------------
        conclusao = [Paragraph(identidade.escapar(texto_da_conclusao(dossie.desfecho)), e["corpo"])]
        consideracoes = (dados_form.get("consideracoes") or "").strip()
        if consideracoes:
            conclusao += [
                Paragraph(traduzir("ld_sub_consideracoes"), e["subsecao"]),
                Paragraph(identidade.escapar(consideracoes), e["corpo"]),
            ]
        acrescentar(traduzir("ld_sec_8"), conclusao)

        # --- ENCERRAMENTO -------------------------------------------------
        linha = Table([[""]], colWidths=[230])
        linha.setStyle([("LINEABOVE", (0, 0), (-1, -1), 0.9, colors.black)])
        linha.hAlign = "CENTER"
        nome = subscritor.nome.strip() if subscritor.declarado else ""
        complementos = [
            parte.strip() for parte in
            (subscritor.funcao, subscritor.registro_funcional, subscritor.unidade)
            if parte.strip()
        ]
        historia.append(KeepTogether([
            Spacer(1, 18),
            Paragraph(traduzir("ld_encerramento"), e["corpo"]),
            Spacer(1, 14),
            Paragraph(_data_por_extenso(agora) + ".", e["assinatura"]),
            Spacer(1, 42),
            linha,
            Spacer(1, 4),
            Paragraph(
                f"<b>{identidade.escapar(nome)}</b>" if nome else traduzir("ld_assinatura_examinador"),
                e["assinatura"],
            ),
            Paragraph(identidade.escapar(" · ".join(complementos)) if complementos else "",
                      e["assinatura"]),
        ]))

        historia.append(PageBreak())
        acrescentar(traduzir("ld_anexo_tempo"), blocos.bloco_linha_do_tempo(dossie, largura))

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho,
            traduzir("ld_titulo_doc"),
            historia,
            rastreio=dossie.rastreio,
            selo=dossie.sha256_do_manifesto,
            autor=nome,
            teste=dossie.de_teste or subscritor.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")


# ---------------------------------------------------------------------------
# Exame sem extração
# ---------------------------------------------------------------------------
def _preambulo(dossie, pasta_aquisicao, subscritor, agora, largura, e) -> list:
    pares = [(traduzir("ld_l_caso"), identidade.escapar(dossie.caso))]
    pares += [
        (rotulo, identidade.escapar(valor) if valor else traduzir("bl_nao_informado"))
        for rotulo, valor in dossie.dados_do_caso
    ]
    pares += [
        (traduzir("ld_l_registro_examinado"), identidade.escapar(pasta_aquisicao.name)),
        (traduzir("ld_l_data_exame"),
         identidade.escapar(carimbo_legivel(dossie.abertura)) or traduzir("bl_nao_informado")),
        (traduzir("ld_l_operador_exame"), identidade.escapar(blocos.texto_do_operador(dossie))),
        (traduzir("ld_l_examinador_subscreve"),
         identidade.escapar(subscritor.resumo()) if subscritor.declarado
         else traduzir("ld_perfil_nao_preenchido")),
        (traduzir("ld_l_data_emissao"), agora.strftime("%d/%m/%Y %H:%M:%S %z")),
    ]
    return [identidade.tabela_de_pares(pares, largura)]


def _assinatura(subscritor, agora, e, texto_final: str) -> KeepTogether:
    linha = Table([[""]], colWidths=[230])
    linha.setStyle([("LINEABOVE", (0, 0), (-1, -1), 0.9, colors.black)])
    linha.hAlign = "CENTER"
    nome = subscritor.nome.strip() if subscritor.declarado else ""
    complementos = [
        parte.strip() for parte in
        (subscritor.funcao, subscritor.registro_funcional, subscritor.unidade)
        if parte.strip()
    ]
    return KeepTogether([
        Spacer(1, 18),
        Paragraph(texto_final, e["corpo"]),
        Spacer(1, 14),
        Paragraph(_data_por_extenso(agora) + ".", e["assinatura"]),
        Spacer(1, 42),
        linha,
        Spacer(1, 4),
        Paragraph(
            f"<b>{identidade.escapar(nome)}</b>" if nome else traduzir("ld_assinatura_examinador"),
            e["assinatura"],
        ),
        Paragraph(identidade.escapar(" · ".join(complementos)) if complementos else "",
                  e["assinatura"]),
    ])


def _gerar_sem_extracao(
    pasta_aquisicao: Path, exame: dict, dados_form: dict, examinador, destino
) -> DocumentoGerado:
    """
    Laudo do exame em que não houve extração: a peça, o estado declarado, a
    tentativa registrada e a conclusão negativa — que diz que não foi
    possível extrair, e nunca que o aparelho não tem dados.
    """
    try:
        dossie = montar_dossie(pasta_aquisicao)
        subscritor = de_dicionario(examinador or {})
        agora = datetime.now().astimezone()
        e = identidade.estilos()
        largura = identidade.largura_util()
        numero = (dados_form.get("numero") or "").strip()
        subtitulo = traduzir("ld_subtitulo_sem_extracao") + (
            traduzir("ld_subtitulo_numero", numero=identidade.escapar(numero)) if numero else "")
        historia = [
            Spacer(1, 6),
            Paragraph(traduzir("ld_titulo"), e["titulo"]),
            Paragraph(subtitulo, e["subtitulo"]),
        ]

        def acrescentar(titulo, elementos):
            historia.extend(blocos.secao(titulo, elementos))

        acrescentar(traduzir("ld_sec_1"), _preambulo(dossie, pasta_aquisicao, subscritor, agora,
                                                      largura, e))
        acrescentar(traduzir("ld_sec_2"), [_declaracao(
            dados_form.get("objetivo"), traduzir("ld_sem_objetivo"), e,
        )])

        acrescentar(traduzir("ld_sec_3"), blocos.bloco_peca(
            dossie, largura, traduzir("ld_se_sem_caracteristicas"),
        ))
        historia.append(Paragraph(traduzir("ld_sub_fotos"), e["subsecao"]))
        historia.extend(blocos.bloco_fotos(dossie, largura))
        historia.append(Paragraph(traduzir("ld_sub_autorizacao"), e["subsecao"]))
        historia.extend(blocos.bloco_autorizacao(dossie, largura))

        def valor(chave):
            texto = str(exame.get(chave) or "").strip()
            return identidade.escapar(texto) if texto else traduzir("bl_nao_informado")

        acrescentar(traduzir("ld_se_sec_4"), [
            identidade.tabela_de_pares([
                (traduzir("ld_l_liga"), valor("liga")),
                (traduzir("ld_l_estado_recebido"), valor("estado_ao_receber")),
                (traduzir("ld_l_bateria"), valor("bateria")),
                (traduzir("ld_l_isolado"), valor("isolado_da_rede")),
                (traduzir("ld_l_tipo_bloqueio"), valor("tipo_de_bloqueio")),
            ], largura),
            Spacer(1, 3),
            Paragraph(traduzir("ld_estado_nota"), e["nota"]),
        ])

        tentativa = exame.get("tentativa") or {}
        relativo = f"{exame_sem_extracao.PASTA}/{exame_sem_extracao.NOME_TENTATIVA}"
        selado = (dossie.hashes or {}).get(relativo, "")
        registro = [
            Paragraph(traduzir("ld_sub_tent_declaradas"), e["subsecao"]),
            _declaracao(exame.get("tentativas"), traduzir("ld_sem_tentativas"), e),
            Paragraph(traduzir("ld_sub_tent_registrada"), e["subsecao"]),
        ]
        if tentativa.get("realizada"):
            registro.append(identidade.tabela_de_pares([
                (traduzir("ld_l_momento"), identidade.escapar(carimbo_legivel(tentativa.get("momento", "")))
                 or traduzir("bl_nao_informado")),
                (traduzir("ld_l_resultado"), identidade.escapar(tentativa.get("resultado", ""))),
                (traduzir("ld_l_resposta_integral"), identidade.escapar(relativo)
                 + (traduzir("ld_tent_sha", selado=selado) if selado else "")),
            ], largura))
            registro += [Spacer(1, 3), Paragraph(traduzir("ld_tent_nota"), e["nota"])]
        else:
            registro.append(Paragraph(traduzir("ld_tent_nao_realizada"), e["corpo"]))
        acrescentar(traduzir("ld_se_sec_5"), registro)

        acrescentar(traduzir("ld_se_sec_6"), blocos.bloco_integridade(dossie, largura))

        conclusao = [Paragraph(identidade.escapar(exame_sem_extracao.texto_da_conclusao(exame)),
                               e["corpo"])]
        recomendacao = str(exame.get("recomendacao") or "").strip()
        if recomendacao:
            conclusao += [Paragraph(traduzir("ld_sub_recomendacao"), e["subsecao"]),
                          Paragraph(identidade.escapar(recomendacao), e["corpo"])]
        consideracoes = (dados_form.get("consideracoes") or "").strip()
        if consideracoes:
            conclusao += [Paragraph(traduzir("ld_sub_consideracoes"), e["subsecao"]),
                          Paragraph(identidade.escapar(consideracoes), e["corpo"])]
        acrescentar(traduzir("ld_se_sec_7"), conclusao)

        historia.append(_assinatura(subscritor, agora, e, traduzir("ld_se_encerramento")))
        historia.append(PageBreak())
        acrescentar(traduzir("ld_anexo_tempo"), blocos.bloco_linha_do_tempo(dossie, largura))

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho, traduzir("ld_titulo_doc_sem_extracao"), historia,
            rastreio=dossie.rastreio, selo=dossie.sha256_do_manifesto,
            autor=subscritor.nome.strip() if subscritor.declarado else "",
            teste=dossie.de_teste or subscritor.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")
