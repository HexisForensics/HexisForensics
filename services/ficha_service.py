"""
Ficha do Aparelho em PDF: a capa de leitura rápida da aquisição.

Mesma mecânica do Relatório de Extração — documento DERIVADO, emitido
depois do selo, gravado FORA da aquisição, em `<caso>/documentos/` — mas
curto: responde, num golpe de vista, as primeiras perguntas de uma
investigação (chegou bloqueado? que aparelho e que linha? o que foi
obtido?). A doutrina e a montagem dos campos ficam em `core.ficha`; aqui só
se desenha.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from reportlab.platypus import Paragraph, Spacer

from core.ficha import montar_ficha
from core.desfecho import rotulo_de_ressalva
from core.idioma import traduzir
from services import blocos_pdf as blocos
from services import identidade_pdf as identidade
from services.dossie_service import montar_dossie
from services.relatorio_extracao_service import (
    DocumentoGerado,
    destino_livre,
    pasta_de_documentos,
)

PREFIXO = "Ficha_do_Aparelho"


def _valor_html(campo) -> str:
    """Valor do campo + a fonte, como um parágrafo só. NÃO APURADO sai em âmbar."""
    if campo.apurado:
        corpo = identidade.escapar(campo.valor)
    else:
        corpo = f'<font color="#9a6700"><b>{identidade.escapar(campo.valor)}</b></font>'
    if campo.fonte:
        corpo += (
            f'<br/><font size="6.5" color="#5b6675">{traduzir("fha_rotulo_fonte")}'
            f"{identidade.escapar(campo.fonte)}</font>"
        )
    return corpo


def gerar(pasta_aquisicao: Path, destino: Optional[Path] = None) -> DocumentoGerado:
    """Gera a Ficha do Aparelho da aquisição e devolve onde ficou."""
    pasta_aquisicao = Path(pasta_aquisicao)
    try:
        ficha = montar_ficha(pasta_aquisicao)
        dossie = montar_dossie(pasta_aquisicao)

        e = identidade.estilos()
        largura = identidade.largura_util()

        historia = [
            Spacer(1, 6),
            Paragraph(traduzir("fha_titulo_pdf"), e["titulo"]),
            Paragraph(
                traduzir(
                    "fha_subtitulo",
                    caso=identidade.escapar(dossie.caso),
                    aquisicao=identidade.escapar(pasta_aquisicao.name),
                ),
                e["subtitulo"],
            ),
            Paragraph(traduzir("fha_nota_pdf"), e["nota"]),
            Spacer(1, 10),
        ]

        pares = [
            (campo.rotulo, Paragraph(_valor_html(campo), e["celula"]))
            for campo in ficha.campos
        ]
        historia.append(identidade.tabela_de_pares(pares, largura, proporcao=0.34))

        if ficha.ressalvas:
            historia.append(Spacer(1, 12))
            historia.append(Paragraph(traduzir("fha_ressalvas_pdf"), e["subsecao"]))
            for nome, chaves in ficha.ressalvas:
                motivos = ", ".join(rotulo_de_ressalva(c) for c in chaves)
                historia.append(
                    Paragraph(
                        f"• {identidade.escapar(nome)}: "
                        f"{identidade.escapar(motivos)}",
                        e["esquerda"],
                    )
                )

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao), f"{PREFIXO}_{pasta_aquisicao.name}"
        )
        identidade.montar_documento(
            caminho,
            traduzir("fha_titulo_doc"),
            historia,
            rastreio=dossie.rastreio,
            selo=dossie.sha256_do_manifesto,
            autor=blocos.texto_do_operador(dossie),
            teste=dossie.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")
