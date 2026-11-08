"""
Identidade visual dos documentos em PDF do Hexis Forensics.

Um lugar só para o que todo documento da suíte tem em comum: o logo no
cabeçalho, a paleta, os estilos de texto, o desenho das tabelas e o rodapé.

O rodapé não é ornamento. Cada página traz a aquisição de origem e o
SHA-256 do manifesto que a sela — uma página solta, fotocopiada ou
juntada a outro documento, continua dizendo de que coleta saiu e contra
qual selo pode ser conferida. E traz "página N de M": sem o total, não há
como saber se o documento em mãos está inteiro.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as ImagemPDF
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from core.instalacao import raiz_da_instalacao
from core.versao import identificacao_ferramenta

MARINHO = colors.HexColor("#0f1b2d")
AZUL = colors.HexColor("#3f8dfd")
VERDE = colors.HexColor("#19c3a6")
CINZA_TEXTO = colors.HexColor("#5b6675")
CINZA_LINHA = colors.HexColor("#c9d1db")
CINZA_FUNDO = colors.HexColor("#f3f6fa")
VERMELHO = colors.HexColor("#b3261e")
TARJA_DE_TESTE = "DOCUMENTO DE TESTE — SEM VALOR PERICIAL (conta Forensic Admin)"
AMBAR = colors.HexColor("#9a6700")

MARGEM = 2 * cm
ALTURA_CABECALHO = 1.6 * cm
ALTURA_RODAPE = 1.4 * cm

NOME_DA_MARCA = "Hexis Forensics"

# Fonte com cobertura ampla, quando a estação a tem. As fontes embutidas do
# PDF só cobrem o alfabeto latino ocidental: um nome de contato em cirílico
# ou árabe sairia como quadrados, e o leitor não saberia se o dado está
# corrompido na evidência ou só no papel.
_FONTES_DO_SISTEMA = (
    ("FE-Texto", "segoeui.ttf"),
    ("FE-Texto-Bold", "segoeuib.ttf"),
    ("FE-Texto-Italic", "segoeuii.ttf"),
    ("FE-Mono", "consola.ttf"),
)
_fontes: Optional[dict] = None


def fontes() -> dict:
    """Nomes das fontes a usar: as do sistema, se registráveis; senão as embutidas."""
    global _fontes
    if _fontes is not None:
        return _fontes
    padrao = {
        "texto": "Helvetica",
        "negrito": "Helvetica-Bold",
        "italico": "Helvetica-Oblique",
        "mono": "Courier",
    }
    pasta = Path("C:/Windows/Fonts")
    try:
        for nome, arquivo in _FONTES_DO_SISTEMA:
            pdfmetrics.registerFont(TTFont(nome, str(pasta / arquivo)))
        pdfmetrics.registerFontFamily(
            "FE-Texto", normal="FE-Texto", bold="FE-Texto-Bold",
            italic="FE-Texto-Italic", boldItalic="FE-Texto-Bold",
        )
        _fontes = {
            "texto": "FE-Texto", "negrito": "FE-Texto-Bold",
            "italico": "FE-Texto-Italic", "mono": "FE-Mono",
        }
    except Exception:
        _fontes = padrao
    return _fontes


def caminho_do_logo() -> Optional[Path]:
    caminho = raiz_da_instalacao() / "assets" / "marca" / "logo_claro.png"
    return caminho if caminho.is_file() else None


def escapar(valor) -> str:
    """Texto seguro para `Paragraph`. Vazio vira travessão, nunca célula em branco."""
    texto = str(valor).strip() if valor is not None else ""
    if not texto:
        return "—"
    return html.escape(texto).replace("\n", "<br/>")


def estilos() -> dict:
    f = fontes()
    base = ParagraphStyle(
        "corpo", fontName=f["texto"], fontSize=10, leading=14.5,
        alignment=TA_JUSTIFY, textColor=colors.black,
    )
    return {
        "corpo": base,
        "esquerda": ParagraphStyle("esquerda", parent=base, alignment=TA_LEFT),
        "celula": ParagraphStyle("celula", parent=base, fontSize=8.5, leading=11, alignment=TA_LEFT),
        "celula_cabecalho": ParagraphStyle(
            "celula_cabecalho", parent=base, fontName=f["negrito"], fontSize=8.5,
            leading=11, alignment=TA_LEFT, textColor=colors.white,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base, fontName=f["italico"], fontSize=8.5, leading=12,
            textColor=CINZA_TEXTO,
        ),
        "mono": ParagraphStyle(
            "mono", parent=base, fontName=f["mono"], fontSize=8, leading=10.5,
            alignment=TA_LEFT,
        ),
        "mono_pequeno": ParagraphStyle(
            "mono_pequeno", parent=base, fontName=f["mono"], fontSize=6.3, leading=8,
            alignment=TA_LEFT,
        ),
        "titulo": ParagraphStyle(
            "titulo", parent=base, fontName=f["negrito"], fontSize=17, leading=21,
            alignment=TA_CENTER, textColor=MARINHO, spaceAfter=4,
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo", parent=base, fontSize=10.5, leading=14, alignment=TA_CENTER,
            textColor=CINZA_TEXTO, spaceAfter=14,
        ),
        "secao": ParagraphStyle(
            "secao", parent=base, fontName=f["negrito"], fontSize=12.5, leading=16,
            alignment=TA_LEFT, textColor=MARINHO, spaceBefore=16, spaceAfter=7,
            borderPadding=(0, 0, 3, 0),
        ),
        "subsecao": ParagraphStyle(
            "subsecao", parent=base, fontName=f["negrito"], fontSize=10.5, leading=14,
            alignment=TA_LEFT, textColor=MARINHO, spaceBefore=9, spaceAfter=4,
            # Um subtítulo nunca fica sozinho no pé da página, longe do que anuncia.
            keepWithNext=1,
        ),
        "alerta": ParagraphStyle(
            "alerta", parent=base, fontName=f["negrito"], fontSize=9.5, leading=13,
            alignment=TA_LEFT, textColor=VERMELHO,
        ),
        "assinatura": ParagraphStyle(
            "assinatura", parent=base, fontSize=10, leading=13.5, alignment=TA_CENTER,
        ),
    }


def tabela(cabecalho, linhas, larguras, estilo_celula=None, repetir_cabecalho=True) -> Table:
    """
    Tabela no desenho da suíte: cabeçalho marinho, linhas zebradas.

    As células chegam como texto e são embrulhadas em `Paragraph` aqui, para
    que quebrem linha dentro da coluna em vez de transbordar a página.
    Quem quiser marcação própria numa célula passa um `Paragraph` pronto.
    """
    e = estilos()
    estilo_celula = estilo_celula or e["celula"]

    def celula(valor, estilo):
        return valor if not isinstance(valor, str) else Paragraph(valor, estilo)

    dados = [[celula(escapar(c), e["celula_cabecalho"]) for c in cabecalho]]
    for linha in linhas:
        dados.append([celula(valor, estilo_celula) for valor in linha])

    t = Table(dados, colWidths=larguras, repeatRows=1 if repetir_cabecalho else 0)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MARINHO),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_FUNDO]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
        ("BOX", (0, 0), (-1, -1), 0.6, CINZA_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def tabela_de_pares(pares, largura_util: float, proporcao: float = 0.32) -> Table:
    """Tabela de duas colunas, rótulo e valor, sem linha de cabeçalho."""
    e = estilos()
    rotulo = ParagraphStyle("rotulo_par", parent=e["celula"], fontName=fontes()["negrito"])
    dados = [
        [Paragraph(escapar(chave), rotulo),
         valor if not isinstance(valor, str) else Paragraph(valor, e["celula"])]
        for chave, valor in pares
    ]
    t = Table(dados, colWidths=[largura_util * proporcao, largura_util * (1 - proporcao)])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CINZA_FUNDO),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
        ("BOX", (0, 0), (-1, -1), 0.6, CINZA_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def imagem_ajustada(caminho: Path, largura_maxima: float, altura_maxima: float):
    """A imagem dentro da caixa dada, na proporção real. `None` se ilegível."""
    try:
        imagem = ImagemPDF(str(caminho))
        fator = min(largura_maxima / imagem.drawWidth, altura_maxima / imagem.drawHeight)
        imagem.drawWidth *= fator
        imagem.drawHeight *= fator
        return imagem
    except Exception:
        return None


class _TelaNumerada(canvas.Canvas):
    """
    Canvas que só desenha o rodapé depois de saber quantas páginas há.

    "Página 3" não diz se existe uma página 4. "Página 3 de 3" diz.
    """

    desenhar_moldura = None  # definido por `montar_documento`

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            if self.desenhar_moldura:
                self.desenhar_moldura(self, total)
            super().showPage()
        super().save()


def montar_documento(
    caminho_pdf: Path,
    titulo_do_documento: str,
    historia: list,
    rastreio: str = "",
    selo: str = "",
    paisagem: bool = False,
    autor: str = "",
    teste: bool = False,
) -> None:
    """
    Constrói o PDF com a moldura da suíte em todas as páginas.

    `rastreio` é o que identifica a origem (caso e aquisição); `selo` é o
    SHA-256 do manifesto. Os dois vão em cada página. `selo=None` é para o
    documento que cobre o caso inteiro e não tem UM selo a citar; vazio
    significa aquisição sem manifesto, e o rodapé diz isso.

    `teste=True` (aquisição ou laudo da conta Forensic Admin) põe em TODA
    página a tarja "DOCUMENTO DE TESTE — SEM VALOR PERICIAL" e uma marca
    d'água: um teste impresso não pode passar por exame.
    """
    tamanho = (A4[1], A4[0]) if paisagem else A4
    largura, altura = tamanho
    f = fontes()
    logo = caminho_do_logo()
    gerado_em = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S %z")

    def moldura(tela, total_de_paginas):
        tela.saveState()
        # --- cabeçalho
        topo = altura - 0.9 * cm
        if logo:
            altura_logo = 0.95 * cm
            tela.drawImage(
                str(logo), MARGEM, topo - altura_logo, height=altura_logo,
                width=altura_logo * 740 / 256, mask="auto", preserveAspectRatio=True,
            )
        else:
            tela.setFont(f["negrito"], 11)
            tela.setFillColor(MARINHO)
            tela.drawString(MARGEM, topo - 0.6 * cm, NOME_DA_MARCA.upper())
        tela.setFont(f["negrito"], 8.5)
        tela.setFillColor(MARINHO)
        tela.drawRightString(largura - MARGEM, topo - 0.42 * cm, titulo_do_documento.upper())
        tela.setFont(f["texto"], 7.5)
        tela.setFillColor(CINZA_TEXTO)
        tela.drawRightString(largura - MARGEM, topo - 0.82 * cm, rastreio)
        tela.setStrokeColor(AZUL)
        tela.setLineWidth(1.4)
        tela.line(MARGEM, topo - 1.12 * cm, largura - MARGEM, topo - 1.12 * cm)
        tela.setStrokeColor(VERDE)
        tela.line(MARGEM, topo - 1.12 * cm, MARGEM + 2.2 * cm, topo - 1.12 * cm)

        # --- rodapé
        base = 0.85 * cm
        tela.setStrokeColor(CINZA_LINHA)
        tela.setLineWidth(0.5)
        tela.line(MARGEM, base + 0.62 * cm, largura - MARGEM, base + 0.62 * cm)
        tela.setFillColor(CINZA_TEXTO)
        tela.setFont(f["texto"], 7)
        tela.drawString(
            MARGEM, base + 0.3 * cm, f"{identificacao_ferramenta()}  ·  gerado em {gerado_em}"
        )
        tela.drawRightString(
            largura - MARGEM, base + 0.3 * cm,
            f"Página {tela.getPageNumber()} de {total_de_paginas}",
        )
        if teste:
            tela.saveState()
            tela.setFillColor(VERMELHO)
            tela.rect(MARGEM, topo - 1.62 * cm, largura - 2 * MARGEM, 0.42 * cm, stroke=0, fill=1)
            tela.setFillColor(colors.white)
            tela.setFont(f["negrito"], 8)
            tela.drawCentredString(largura / 2, topo - 1.5 * cm, TARJA_DE_TESTE)
            tela.setFillColor(VERMELHO, alpha=0.08)
            tela.setFont(f["negrito"], 60)
            tela.translate(largura / 2, altura / 2)
            tela.rotate(35)
            tela.drawCentredString(0, 0, "TESTE")
            tela.restoreState()
            tela.setFillColor(VERMELHO)
            tela.setFont(f["negrito"], 7)
            tela.drawCentredString(largura / 2, base - 0.42 * cm, TARJA_DE_TESTE)
        tela.setFillColor(CINZA_TEXTO)
        tela.setFont(f["mono"], 6.3)
        if selo is not None:
            tela.drawString(
                MARGEM, base,
                f"SHA-256 do manifesto: {selo}" if selo
                else "Aquisição SEM manifesto de integridade — nada se afirma sobre a preservação.",
            )
        tela.restoreState()

    tela_do_documento = type("TelaDoDocumento", (_TelaNumerada,), {"desenhar_moldura": staticmethod(moldura)})

    documento = SimpleDocTemplate(
        str(caminho_pdf),
        pagesize=tamanho,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=MARGEM + ALTURA_CABECALHO * 0.55,
        bottomMargin=MARGEM + ALTURA_RODAPE * 0.3,
        title=titulo_do_documento,
        author=autor or NOME_DA_MARCA,
        creator=identificacao_ferramenta(),
        subject=rastreio,
    )
    documento.build(historia, canvasmaker=tela_do_documento)


def largura_util(paisagem: bool = False) -> float:
    return (A4[1] if paisagem else A4[0]) - 2 * MARGEM
