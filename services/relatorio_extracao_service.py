"""
Relatório de Extração: o documento técnico de UMA aquisição, em PDF.

É emitido pelo examinador, no gerenciador de casos, sem perguntar nada
a ninguém, porque tudo o que ele diz já está gravado: quem executou, em que estação, com
que método, o que cada módulo obteve, o que foi alterado no dispositivo e
qual é o selo. É o retrato da coleta — o que se entrega junto com a mídia.

Não é o Laudo Pericial. O laudo é ato de quem o assina e traz o objetivo
do exame, as declarações do examinador e a conclusão; este relatório não
conclui nada: registra.

**Fica FORA da aquisição selada**, em `<caso>/documentos/`. Ele é impresso
depois do manifesto (precisa do hash dele), e gravá-lo dentro da pasta
selada faria a conferência acusar o próprio relatório como arquivo
acrescentado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.platypus import PageBreak, Paragraph, Spacer

from core.case import pasta_do_caso
from core.normalizacao import nome_do_fuso
from services import blocos_pdf as blocos
from services import identidade_pdf as identidade
from services.dossie_service import montar_dossie
from services.relatorio_service import levantar_artefatos

PASTA_DOCUMENTOS = "documentos"
PREFIXO = "Relatorio_de_Extracao"


@dataclass
class DocumentoGerado:
    caminho: Optional[Path] = None
    erro: str = ""


def destino_livre(pasta: Path, nome_base: str) -> Path:
    """
    Caminho para gravar o documento sem apagar uma emissão anterior.

    Reemitir é legítimo (o caso ganhou uma conferência, o perfil foi
    preenchido), mas a emissão de ontem pode já ter sido entregue: ela
    fica, e a nova ganha o carimbo da hora.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{nome_base}.pdf"
    if caminho.exists():
        caminho = pasta / f"{nome_base}_emitido_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return caminho


def pasta_de_documentos(pasta_aquisicao: Path) -> Path:
    """
    Onde ficam os documentos derivados desta aquisição: `<caso>/documentos/`.

    Nunca dentro da própria aquisição. Uma pasta que não segue o padrão de
    nome de aquisição (as mais antigas não seguem) faz `pasta_do_caso`
    devolver ela mesma — e o relatório iria parar dentro do que acabou de
    ser selado, aparecendo na conferência como arquivo acrescentado. Nesse
    caso os documentos vão para uma pasta irmã.
    """
    pasta_aquisicao = Path(pasta_aquisicao).resolve()
    caso = pasta_do_caso(pasta_aquisicao)
    if caso == pasta_aquisicao:
        return pasta_aquisicao.parent / f"{pasta_aquisicao.name}_{PASTA_DOCUMENTOS}"
    return caso / PASTA_DOCUMENTOS


def fuso_da_estacao():
    return datetime.now().astimezone().tzinfo


def gerar(pasta_aquisicao: Path, destino: Optional[Path] = None, fuso="estacao") -> DocumentoGerado:
    """
    Gera o Relatório de Extração da aquisição e devolve onde ficou.

    `fuso` converte as datas do conteúdo. Por padrão é o da estação, e o
    documento DECLARA qual foi usado; `None` mantém UTC.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    if fuso == "estacao":
        fuso = fuso_da_estacao()

    try:
        dossie = montar_dossie(pasta_aquisicao)
        try:
            artefatos = levantar_artefatos(pasta_aquisicao, fuso)
            erro_do_conteudo = ""
        except Exception as erro:  # o conteúdo não pode custar o relatório da coleta
            artefatos, erro_do_conteudo = [], str(erro)

        e = identidade.estilos()
        largura = identidade.largura_util()
        historia = [
            Spacer(1, 6),
            Paragraph("RELATÓRIO DE EXTRAÇÃO", e["titulo"]),
            Paragraph(
                f"Caso {identidade.escapar(dossie.caso)} — aquisição "
                f"{identidade.escapar(pasta_aquisicao.name)}",
                e["subtitulo"],
            ),
        ]

        def acrescentar(titulo, elementos):
            historia.extend(blocos.secao(titulo, elementos))

        acrescentar("1. Identificação", blocos.bloco_identificacao(dossie, largura))
        acrescentar("2. Dispositivo examinado", blocos.bloco_peca(dossie, largura))
        acrescentar("3. Fotografias da peça", blocos.bloco_fotos(dossie, largura))
        acrescentar("4. Ambiente da aquisição", blocos.bloco_ambiente(dossie, largura))
        acrescentar("5. Autorização de acesso aos dados", blocos.bloco_autorizacao(dossie, largura))
        acrescentar("6. Método empregado", blocos.bloco_metodo(dossie, largura))
        acrescentar("7. Limitações do método", blocos.bloco_limitacoes(dossie, largura))
        acrescentar(
            "8. Alterações e decisões registradas",
            blocos.bloco_alteracoes_ocorridas(dossie, largura),
        )
        acrescentar("9. Desfecho por módulo", blocos.bloco_desfecho(dossie, largura))

        if erro_do_conteudo:
            conteudo = [Paragraph(
                "O conteúdo desta aquisição NÃO pôde ser interpretado para este relatório "
                f"({identidade.escapar(erro_do_conteudo)}). O material bruto permanece na "
                "aquisição; nada se afirma aqui sobre o que ele contém.",
                e["alerta"],
            )]
        else:
            conteudo = blocos.bloco_conteudo(artefatos, largura, nome_do_fuso(fuso))
        acrescentar("10. Conteúdo interpretado — resumo", conteudo)

        acrescentar(
            "11. Arquivos adquiridos, por categoria",
            blocos.bloco_arquivos_por_categoria(dossie, largura),
        )
        acrescentar("12. Inventário do material adquirido", blocos.bloco_inventario(dossie, largura))
        acrescentar("13. Integridade", blocos.bloco_integridade(dossie, largura))
        acrescentar(
            "14. Requisitos da norma verificados pela ferramenta",
            blocos.bloco_protocolos_da_ferramenta(dossie, largura),
        )

        historia.append(PageBreak())
        acrescentar(
            "Anexo A — Linha do tempo do procedimento",
            blocos.bloco_linha_do_tempo(dossie, largura),
        )
        historia.append(PageBreak())
        acrescentar("Anexo B — Manifesto de hashes", blocos.bloco_manifesto(dossie, largura))

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho,
            "Relatório de Extração",
            historia,
            rastreio=dossie.rastreio,
            selo=dossie.sha256_do_manifesto,
            autor=blocos.texto_do_operador(dossie),
            teste=dossie.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")
