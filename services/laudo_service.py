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

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
    "setembro", "outubro", "novembro", "dezembro",
)


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
        return (
            "Não foi possível reproduzir o desfecho desta coleta a partir do que foi "
            "selado na aquisição. Este laudo não afirma completude nem incompletude do "
            "material: o registro necessário para tanto não está disponível."
        )

    if desfecho.integral:
        return (
            f"{desfecho.resumo} Todos os módulos empregados concluíram sem ressalva, e o "
            "material adquirido está preservado sob o selo de integridade descrito na "
            "seção 7. As limitações do método constam da seção 5 e delimitam o que esta "
            "coleta alcança."
        )

    partes = [desfecho.resumo]
    if desfecho.cancelada:
        partes.append(
            "A execução foi interrompida antes de percorrer todos os módulos previstos, "
            "de modo que o material adquirido é PARCIAL em relação ao que fora planejado."
        )
    if desfecho.falharam:
        partes.append(
            "Houve módulo que não obteve dado. A ausência do material correspondente "
            "decorre disso, e NÃO autoriza concluir que o dado inexista no dispositivo."
        )
    if desfecho.com_ressalva:
        partes.append(
            "Houve módulo concluído com ressalva, isto é, que obteve parte do material e "
            "declarou o que não alcançou. A seção 6 identifica quais."
        )
    partes.append(
        "O material efetivamente adquirido está preservado sob o selo descrito na seção 7, "
        "e as limitações do método constam da seção 5."
    )
    return " ".join(partes)


def _data_por_extenso(momento: datetime) -> str:
    return f"{momento.day} de {MESES[momento.month - 1]} de {momento.year}"


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

        historia = [
            Spacer(1, 6),
            Paragraph("LAUDO PERICIAL", e["titulo"]),
            Paragraph(
                "Exame de extração de dados em dispositivo"
                + (f" — Laudo n.º {identidade.escapar(numero)}" if numero else ""),
                e["subtitulo"],
            ),
        ]

        def acrescentar(titulo, elementos):
            historia.extend(blocos.secao(titulo, elementos))

        # --- 1. PREÂMBULO -------------------------------------------------
        pares = [("Caso", identidade.escapar(dossie.caso))]
        pares += [
            (rotulo, identidade.escapar(valor) if valor else blocos.NAO_INFORMADO)
            for rotulo, valor in dossie.dados_do_caso
        ]
        pares += [
            ("Aquisição examinada", identidade.escapar(pasta_aquisicao.name)),
            ("Data da aquisição",
             identidade.escapar(carimbo_legivel(dossie.abertura)) or blocos.NAO_INFORMADO),
            ("Operador da aquisição", identidade.escapar(blocos.texto_do_operador(dossie))),
            ("Examinador que subscreve",
             identidade.escapar(subscritor.resumo()) if subscritor.declarado
             else "<i>perfil do examinador não preenchido</i>"),
            ("Data de emissão do laudo", agora.strftime("%d/%m/%Y %H:%M:%S %z")),
        ]
        acrescentar("1. Preâmbulo", [
            identidade.tabela_de_pares(pares, largura),
            Spacer(1, 3),
            Paragraph(
                "O operador da aquisição é o que ficou gravado, sob o selo, no dia da "
                "coleta. O examinador que subscreve é quem emite este laudo. "
                + ("Ambos abriram a sessão com a própria senha nesta estação; a senha não "
                   "prova identidade, e a ferramenta não a confere além disso."
                   if dossie.operador is not None and dossie.operador.autenticacao.strip()
                   else "Os dois dados são declarados; a ferramenta não confere identidade."),
                e["nota"],
            ),
        ])

        # --- 2. OBJETIVO --------------------------------------------------
        acrescentar("2. Objetivo do exame", [_declaracao(
            dados_form.get("objetivo"),
            "O examinador não informou o objetivo do exame nem quesitos.", e,
        )])

        # --- 3. MATERIAL EXAMINADO ---------------------------------------
        acrescentar("3. Material examinado", blocos.bloco_peca(dossie, largura))
        historia.append(Paragraph("Fotografias da peça", e["subsecao"]))
        historia.extend(blocos.bloco_fotos(dossie, largura))
        historia.append(Paragraph("Autorização de acesso aos dados", e["subsecao"]))
        historia.extend(blocos.bloco_autorizacao(dossie, largura))

        # --- 4. METODOLOGIA ----------------------------------------------
        metodologia = [
            Paragraph(
                "A aquisição seguiu as diretrizes da ABNT NBR ISO/IEC 27037:2013 "
                "(identificação, coleta, aquisição e preservação de evidência digital). "
                "O hash de cada arquivo foi calculado no encerramento da aquisição, e "
                "toda saída de comando foi preservada como parte do material.",
                e["corpo"],
            ),
            Spacer(1, 5),
            identidade.tabela_de_pares([
                ("Modalidade de acesso",
                 identidade.escapar(dados_form.get("tipo_extracao"))
                 if (dados_form.get("tipo_extracao") or "").strip()
                 else "<i>não descrita pelo examinador</i>"),
            ], largura),
            Paragraph("Módulos empregados", e["subsecao"]),
        ]
        metodologia += blocos.bloco_metodo(dossie, largura)
        metodologia.append(Paragraph("Ambiente da aquisição", e["subsecao"]))
        metodologia += blocos.bloco_ambiente(dossie, largura)
        metodologia += blocos.bloco_alteracoes_ocorridas(dossie, largura)
        metodologia.append(Paragraph("Requisitos verificados pela ferramenta", e["subsecao"]))
        metodologia += blocos.bloco_protocolos_da_ferramenta(dossie, largura)
        metodologia.append(Paragraph("Circunstâncias declaradas pelo examinador", e["subsecao"]))
        metodologia += blocos.bloco_protocolos_do_examinador(
            dados_form.get("protocolos") or [], dados_form.get("observacoes", ""), largura
        )
        acrescentar("4. Metodologia", metodologia)

        # --- 5. LIMITAÇÕES -----------------------------------------------
        acrescentar("5. Limitações do método", blocos.bloco_limitacoes(dossie, largura))

        # --- 6. EXAMES E RESULTADOS --------------------------------------
        resultados = [Paragraph("Desfecho da coleta, por módulo", e["subsecao"])]
        resultados += blocos.bloco_desfecho(dossie, largura)
        resultados.append(Paragraph("Conteúdo interpretado", e["subsecao"]))
        if erro_do_conteudo:
            resultados.append(Paragraph(
                "O conteúdo desta aquisição NÃO pôde ser interpretado para este laudo "
                f"({identidade.escapar(erro_do_conteudo)}). Nada se afirma aqui sobre o que "
                "o material contém.",
                e["alerta"],
            ))
        else:
            resultados += blocos.bloco_conteudo(artefatos, largura, nome_do_fuso(fuso))
            resultados.append(Paragraph("Comunicações: volume e interlocutores", e["subsecao"]))
            resultados += blocos.bloco_analise_do_conteudo(artefatos, largura)
        resultados.append(Paragraph("Arquivos adquiridos, por categoria", e["subsecao"]))
        resultados += blocos.bloco_arquivos_por_categoria(dossie, largura)
        resultados.append(Paragraph("Inventário do material adquirido", e["subsecao"]))
        resultados += blocos.bloco_inventario(dossie, largura)
        acrescentar("6. Exames realizados e resultados", resultados)

        # --- 7. CADEIA DE CUSTÓDIA E INTEGRIDADE -------------------------
        acrescentar(
            "7. Cadeia de custódia e integridade", blocos.bloco_integridade(dossie, largura)
        )

        # --- 8. CONCLUSÃO -------------------------------------------------
        conclusao = [Paragraph(identidade.escapar(texto_da_conclusao(dossie.desfecho)), e["corpo"])]
        consideracoes = (dados_form.get("consideracoes") or "").strip()
        if consideracoes:
            conclusao += [
                Paragraph("Considerações do examinador", e["subsecao"]),
                Paragraph(identidade.escapar(consideracoes), e["corpo"]),
            ]
        acrescentar("8. Conclusão", conclusao)

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
            Paragraph(
                "Este laudo é acompanhado do Relatório de Extração da mesma aquisição, "
                "que traz a linha do tempo do procedimento e a reprodução do manifesto de "
                "hashes. A numeração de páginas e o hash do manifesto constam do rodapé.",
                e["corpo"],
            ),
            Spacer(1, 14),
            Paragraph(_data_por_extenso(agora) + ".", e["assinatura"]),
            Spacer(1, 42),
            linha,
            Spacer(1, 4),
            Paragraph(
                f"<b>{identidade.escapar(nome)}</b>" if nome else "<b>Examinador</b>",
                e["assinatura"],
            ),
            Paragraph(identidade.escapar(" · ".join(complementos)) if complementos else "",
                      e["assinatura"]),
        ]))

        historia.append(PageBreak())
        acrescentar(
            "Anexo — Linha do tempo do procedimento",
            blocos.bloco_linha_do_tempo(dossie, largura),
        )

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho,
            "Laudo Pericial",
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
    pares = [("Caso", identidade.escapar(dossie.caso))]
    pares += [
        (rotulo, identidade.escapar(valor) if valor else blocos.NAO_INFORMADO)
        for rotulo, valor in dossie.dados_do_caso
    ]
    pares += [
        ("Registro examinado", identidade.escapar(pasta_aquisicao.name)),
        ("Data do exame",
         identidade.escapar(carimbo_legivel(dossie.abertura)) or blocos.NAO_INFORMADO),
        ("Operador do exame", identidade.escapar(blocos.texto_do_operador(dossie))),
        ("Examinador que subscreve",
         identidade.escapar(subscritor.resumo()) if subscritor.declarado
         else "<i>perfil do examinador não preenchido</i>"),
        ("Data de emissão do laudo", agora.strftime("%d/%m/%Y %H:%M:%S %z")),
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
            f"<b>{identidade.escapar(nome)}</b>" if nome else "<b>Examinador</b>",
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
        historia = [
            Spacer(1, 6),
            Paragraph("LAUDO PERICIAL", e["titulo"]),
            Paragraph(
                "Exame sem Extração"
                + (f" — Laudo n.º {identidade.escapar(numero)}" if numero else ""),
                e["subtitulo"],
            ),
        ]

        def acrescentar(titulo, elementos):
            historia.extend(blocos.secao(titulo, elementos))

        acrescentar("1. Preâmbulo", _preambulo(dossie, pasta_aquisicao, subscritor, agora,
                                               largura, e))
        acrescentar("2. Objetivo do exame", [_declaracao(
            dados_form.get("objetivo"),
            "O examinador não informou o objetivo do exame nem quesitos.", e,
        )])

        acrescentar("3. Material examinado", blocos.bloco_peca(
            dossie, largura,
            "Nenhuma característica foi lida do próprio dispositivo: não houve extração, e a "
            "tentativa de conexão (seção 5) não obteve dele identificação alguma. A "
            "descrição da peça é a declarada acima, no cadastro.",
        ))
        historia.append(Paragraph("Fotografias da peça", e["subsecao"]))
        historia.extend(blocos.bloco_fotos(dossie, largura))
        historia.append(Paragraph("Autorização de acesso aos dados", e["subsecao"]))
        historia.extend(blocos.bloco_autorizacao(dossie, largura))

        def valor(chave):
            texto = str(exame.get(chave) or "").strip()
            return identidade.escapar(texto) if texto else blocos.NAO_INFORMADO

        acrescentar("4. Estado do aparelho", [
            identidade.tabela_de_pares([
                ("O aparelho liga", valor("liga")),
                ("Estado em que foi recebido", valor("estado_ao_receber")),
                ("Bateria", valor("bateria")),
                ("Isolado da rede", valor("isolado_da_rede")),
                ("Tipo de bloqueio", valor("tipo_de_bloqueio")),
            ], largura),
            Spacer(1, 3),
            Paragraph(
                "Declarado pelo examinador no ato do exame. A ferramenta não verifica o "
                "estado físico do aparelho.", e["nota"],
            ),
        ])

        tentativa = exame.get("tentativa") or {}
        relativo = f"{exame_sem_extracao.PASTA}/{exame_sem_extracao.NOME_TENTATIVA}"
        selado = (dossie.hashes or {}).get(relativo, "")
        registro = [
            Paragraph("Declaradas pelo examinador", e["subsecao"]),
            _declaracao(exame.get("tentativas"), "O examinador não descreveu tentativas.", e),
            Paragraph("Registrada pela ferramenta", e["subsecao"]),
        ]
        if tentativa.get("realizada"):
            registro.append(identidade.tabela_de_pares([
                ("Momento", identidade.escapar(carimbo_legivel(tentativa.get("momento", "")))
                 or blocos.NAO_INFORMADO),
                ("Resultado", identidade.escapar(tentativa.get("resultado", ""))),
                ("Resposta integral", identidade.escapar(relativo)
                 + (f"<br/>SHA-256 {selado}" if selado else "")),
            ], largura))
            registro += [Spacer(1, 3), Paragraph(
                "A tentativa não altera o aparelho: no Android, a listagem de dispositivos do "
                "ADB; no iPhone, uma sessão sem pedido de pareamento. A resposta integral do "
                "aparelho está preservada na aquisição, sob o selo da seção 6.", e["nota"],
            )]
        else:
            registro.append(Paragraph(
                "Tentativa de conexão não realizada: o examinador declarou que o aparelho "
                "não liga.", e["corpo"],
            ))
        acrescentar("5. Tentativas realizadas", registro)

        acrescentar("6. Cadeia de custódia e integridade",
                    blocos.bloco_integridade(dossie, largura))

        conclusao = [Paragraph(identidade.escapar(exame_sem_extracao.texto_da_conclusao(exame)),
                               e["corpo"])]
        recomendacao = str(exame.get("recomendacao") or "").strip()
        if recomendacao:
            conclusao += [Paragraph("Recomendação", e["subsecao"]),
                          Paragraph(identidade.escapar(recomendacao), e["corpo"])]
        consideracoes = (dados_form.get("consideracoes") or "").strip()
        if consideracoes:
            conclusao += [Paragraph("Considerações do examinador", e["subsecao"]),
                          Paragraph(identidade.escapar(consideracoes), e["corpo"])]
        acrescentar("7. Conclusão", conclusao)

        historia.append(_assinatura(
            subscritor, agora, e,
            "A numeração de páginas e o hash do manifesto da aquisição constam do rodapé.",
        ))
        historia.append(PageBreak())
        acrescentar("Anexo — Linha do tempo do procedimento",
                    blocos.bloco_linha_do_tempo(dossie, largura))

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho, "Laudo Pericial — Exame sem Extração", historia,
            rastreio=dossie.rastreio, selo=dossie.sha256_do_manifesto,
            autor=subscritor.nome.strip() if subscritor.declarado else "",
            teste=dossie.de_teste or subscritor.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")
