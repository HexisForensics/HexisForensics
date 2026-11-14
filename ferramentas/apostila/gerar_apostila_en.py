"""
Generates the Hexis Forensics User Manual, in PDF, in English.

This is the English version of `gerar_apostila.py`. It reuses the visual
identity of the suite's documents (`services.identidade_pdf`), the same
screenshots from `capturas/` and the phone screens in `celular/`. The module
tables are read from the code itself: the module names and descriptions appear
in Portuguese, because the program is in Portuguese.

Usage:
    py ferramentas/apostila/gerar_apostila_en.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

from core.versao import identificacao_ferramenta  # noqa: E402
from services import identidade_pdf as identidade  # noqa: E402
from services.extraction_service import listar_extratores  # noqa: E402

AQUI = Path(__file__).resolve().parent
CAPTURAS = AQUI / "capturas"
CELULAR = AQUI / "celular"
SAIDA = AQUI / "saida" / "User_Manual_Hexis_Forensics_EN.pdf"

LARGURA, ALTURA = A4
MARGEM = 2.1 * cm
UTIL = LARGURA - 2 * MARGEM

F = identidade.fontes()
E = identidade.estilos()
MARINHO, AZUL, VERDE = identidade.MARINHO, identidade.AZUL, identidade.VERDE

CORPO = ParagraphStyle("ap_corpo", parent=E["corpo"], fontSize=10.3, leading=15.2, spaceAfter=6)
LISTA = ParagraphStyle("ap_lista", parent=CORPO, alignment=TA_LEFT, spaceAfter=0)
H1 = ParagraphStyle("ap_h1", parent=E["titulo"], fontSize=24, leading=28, alignment=TA_LEFT,
                    textColor=MARINHO, spaceAfter=4)
H2 = ParagraphStyle("ap_h2", parent=E["secao"], fontSize=13.5, leading=17, spaceBefore=14,
                    spaceAfter=6, keepWithNext=1)
H3 = ParagraphStyle("ap_h3", parent=E["subsecao"], fontSize=11, spaceBefore=8)
LEGENDA = ParagraphStyle("ap_legenda", parent=E["nota"], alignment=TA_CENTER, spaceBefore=3,
                         spaceAfter=10)
CAIXA = ParagraphStyle("ap_caixa", parent=CORPO, alignment=TA_LEFT, spaceAfter=0, fontSize=9.8,
                       leading=14)
SUMARIO_1 = ParagraphStyle("ap_sum1", parent=CORPO, fontName=F["negrito"], fontSize=11,
                           leftIndent=0, spaceBefore=6, textColor=MARINHO)
SUMARIO_2 = ParagraphStyle("ap_sum2", parent=CORPO, fontSize=9.6, leftIndent=18, spaceAfter=0,
                           leading=13)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
class Apostila(BaseDocTemplate):
    def __init__(self, caminho: Path):
        super().__init__(str(caminho), pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                         topMargin=2.6 * cm, bottomMargin=2.0 * cm,
                         title="User Manual — Hexis Forensics",
                         author="Hexis Forensics", creator=identificacao_ferramenta())
        moldura = Frame(MARGEM, 2.0 * cm, UTIL, ALTURA - 4.6 * cm, id="texto")
        capa = Frame(0, 0, LARGURA, ALTURA, id="capa", leftPadding=0, rightPadding=0,
                     topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="capa", frames=[capa], onPage=_desenhar_capa),
            PageTemplate(id="conteudo", frames=[moldura], onPage=_moldura),
        ])

    def afterFlowable(self, flowable):
        nivel = getattr(flowable, "_nivel_sumario", None)
        if nivel is not None:
            self.notify("TOCEntry", (nivel, flowable._texto_sumario, self.page))


def _desenhar_capa(tela, _doc) -> None:
    tela.saveState()
    tela.setFillColor(MARINHO)
    tela.rect(0, 0, LARGURA, ALTURA, stroke=0, fill=1)
    tela.setFillColor(colors.HexColor("#16324f"))
    tela.circle(LARGURA * 0.15, ALTURA * 0.92, 260, stroke=0, fill=1)
    tela.setStrokeColor(AZUL)
    tela.setLineWidth(2)
    for raio in (120, 170):
        cx, cy = LARGURA * 0.86, ALTURA * 0.18
        pontos = []
        import math
        for i in range(6):
            angulo = math.radians(60 * i - 90)
            pontos.append((cx + raio * math.cos(angulo), cy + raio * math.sin(angulo)))
        caminho = tela.beginPath()
        caminho.moveTo(*pontos[0])
        for ponto in pontos[1:]:
            caminho.lineTo(*ponto)
        caminho.close()
        tela.setStrokeAlpha(0.35)
        tela.drawPath(caminho, stroke=1, fill=0)
    tela.setStrokeAlpha(1)
    logo = AQUI.parents[1] / "assets" / "marca" / "logo_escuro.png"
    if logo.is_file():
        tela.drawImage(str(logo), MARGEM, ALTURA - 6.2 * cm, width=10.5 * cm,
                       height=10.5 * cm * 256 / 740, mask="auto")
    tela.setFillColor(colors.white)
    tela.setFont(F["negrito"], 34)
    tela.drawString(MARGEM, ALTURA * 0.52, "User Manual")
    tela.setFont(F["texto"], 15)
    tela.setFillColor(colors.HexColor("#8fb4e6"))
    tela.drawString(MARGEM, ALTURA * 0.52 - 30,
                    "Extraction and preservation of digital evidence, step by step")
    tela.setFillColor(VERDE)
    tela.rect(MARGEM, ALTURA * 0.52 - 52, 3.2 * cm, 4, stroke=0, fill=1)
    tela.setFillColor(colors.HexColor("#c8d6e6"))
    tela.setFont(F["texto"], 10.5)
    tela.drawString(MARGEM, 3.4 * cm, identificacao_ferramenta())
    tela.drawString(MARGEM, 2.8 * cm, f"Edition of {date.today():%Y-%m-%d}")
    tela.drawString(MARGEM, 2.2 * cm, "Guided by the ISO/IEC 27037 standard")
    tela.restoreState()


def _moldura(tela, doc) -> None:
    tela.saveState()
    topo = ALTURA - 1.3 * cm
    logo = identidade.caminho_do_logo()
    if logo:
        tela.drawImage(str(logo), MARGEM, topo - 0.75 * cm, height=0.75 * cm,
                       width=0.75 * cm * 740 / 256, mask="auto", preserveAspectRatio=True)
    tela.setFont(F["negrito"], 8)
    tela.setFillColor(MARINHO)
    tela.drawRightString(LARGURA - MARGEM, topo - 0.45 * cm, "USER MANUAL")
    tela.setStrokeColor(AZUL)
    tela.setLineWidth(1.2)
    tela.line(MARGEM, topo - 0.95 * cm, LARGURA - MARGEM, topo - 0.95 * cm)
    tela.setStrokeColor(VERDE)
    tela.line(MARGEM, topo - 0.95 * cm, MARGEM + 2.2 * cm, topo - 0.95 * cm)
    tela.setFillColor(identidade.CINZA_TEXTO)
    tela.setFont(F["texto"], 7.5)
    tela.drawString(MARGEM, 1.1 * cm, f"User Manual — {identificacao_ferramenta()}")
    tela.drawRightString(LARGURA - MARGEM, 1.1 * cm, f"page {doc.page}")
    tela.restoreState()


# ---------------------------------------------------------------------------
# Content pieces
# ---------------------------------------------------------------------------
_figura = [0]


def _marcado(paragrafo: Paragraph, nivel: int, texto: str) -> Paragraph:
    paragrafo._nivel_sumario = nivel
    paragrafo._texto_sumario = texto
    return paragrafo


def capitulo(numero: int, titulo: str, abertura: str) -> list:
    faixa = Table([[Paragraph(f"<font color='#3f8dfd'>{numero:02d}</font>",
                              ParagraphStyle("num", parent=H1, fontSize=40, leading=44)),
                    Paragraph(titulo, H1)]],
                  colWidths=[2.4 * cm, UTIL - 2.4 * cm])
    faixa.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("LINEBELOW", (0, 0), (-1, 0), 1.4, AZUL)]))
    faixa._nivel_sumario = 0
    faixa._texto_sumario = f"{numero}. {titulo}"
    return [PageBreak(), faixa, Spacer(1, 10), Paragraph(abertura, CORPO), Spacer(1, 4)]


def secao(titulo: str):
    """Section title that never ends up alone at the foot of the page."""
    return KeepTogether([CondPageBreak(7 * cm), _marcado(Paragraph(titulo, H2), 1, titulo)])


def sub(titulo: str) -> Paragraph:
    return Paragraph(titulo, H3)


def p(texto: str) -> Paragraph:
    return Paragraph(texto, CORPO)


def itens(lista) -> Table:
    linhas = [[Paragraph("•", LISTA), Paragraph(texto, LISTA)] for texto in lista]
    tabela = Table(linhas, colWidths=[0.5 * cm, UTIL - 0.5 * cm])
    tabela.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                ("TOPPADDING", (0, 0), (-1, -1), 1)]))
    return tabela


def passos(lista) -> Table:
    numero = ParagraphStyle("passo_num", parent=LISTA, fontName=F["negrito"], textColor=colors.white,
                            alignment=TA_CENTER, fontSize=9.5)
    linhas = [[Paragraph(str(i), numero), Paragraph(texto, LISTA)]
              for i, texto in enumerate(lista, 1)]
    tabela = Table(linhas, colWidths=[0.75 * cm, UTIL - 0.75 * cm])
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, -1), 8),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3)]
    for i in range(len(linhas)):
        estilo += [("BACKGROUND", (0, i), (0, i), AZUL)]
    tabela.setStyle(TableStyle(estilo))
    return KeepTogether([tabela, Spacer(1, 6)]) if len(linhas) <= 6 else tabela


def caixa(tipo: str, texto: str):
    cores = {"atencao": ("#fdecea", "#b3261e", "Warning"),
             "dica": ("#e8f8f4", "#19c3a6", "Tip"),
             "nota": ("#eef4fe", "#3f8dfd", "Background")}
    fundo, barra, rotulo = cores[tipo]
    tabela = Table([[Paragraph(f"<b>{rotulo}.</b> {texto}", CAIXA)]], colWidths=[UTIL])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fundo)),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, colors.HexColor(barra)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return KeepTogether([Spacer(1, 4), tabela, Spacer(1, 8)])


def figura(nome: str, legenda: str, largura: float = UTIL, altura_max: float = 11 * cm,
           pasta: Path = CAPTURAS):
    _figura[0] += 1
    caminho = pasta / f"{nome}.png"
    if not caminho.is_file():
        reserva = Table([[Paragraph(f"<i>[screenshot pending: {nome}]</i>", LEGENDA)]],
                        colWidths=[largura], rowHeights=[3 * cm])
        reserva.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, identidade.CINZA_LINHA),
                                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        imagem = reserva
    else:
        imagem = identidade.imagem_ajustada(caminho, largura, altura_max)
        moldura = Table([[imagem]])
        moldura.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, identidade.CINZA_LINHA),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        imagem = moldura
    return KeepTogether([Spacer(1, 4), imagem,
                         Paragraph(f"Figure {_figura[0]} — {legenda}", LEGENDA)])


def par_de_figuras(nome_1: str, legenda_1: str, nome_2: str, legenda_2: str,
                   altura_max: float = 9.5 * cm):
    """Two phone screens side by side, each with its own caption."""
    celulas = []
    for nome, legenda in ((nome_1, legenda_1), (nome_2, legenda_2)):
        _figura[0] += 1
        caminho = CELULAR / f"{nome}.png"
        if caminho.is_file():
            imagem = identidade.imagem_ajustada(caminho, UTIL * 0.46, altura_max)
            moldura = Table([[imagem]])
            moldura.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, identidade.CINZA_LINHA),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                         ("TOPPADDING", (0, 0), (-1, -1), 0),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        else:
            moldura = Paragraph(f"<i>[screenshot pending: {nome}]</i>", LEGENDA)
        celulas.append([moldura, Paragraph(f"Figure {_figura[0]} — {legenda}", LEGENDA)])
    tabela = Table([[celulas[0], celulas[1]]], colWidths=[UTIL / 2, UTIL / 2])
    tabela.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return KeepTogether([Spacer(1, 4), tabela])


def tabela_simples(cabecalho, linhas, larguras):
    return identidade.tabela(cabecalho, [[Paragraph(c, E["celula"]) for c in linha]
                                         for linha in linhas],
                             [UTIL * l for l in larguras])


def tabela_de_modulos(plataforma: str):
    linhas = []
    for classe in listar_extratores(plataforma):
        altera = "yes — " + classe.alteracoes_no_dispositivo[0][0] if classe.alteracoes_no_dispositivo \
            else "no"
        exige = []
        if classe.requer_privilegio_root:
            exige.append(classe.rotulo_privilegio)
        if classe.selecao_expressa:
            exige.append("express selection (starts unchecked)")
        exige.append(f"profile {classe.perfil_minimo.name}")
        linhas.append([f"<b>{identidade.escapar(classe.nome_exibicao)}</b>",
                       identidade.escapar(classe.descricao),
                       identidade.escapar(altera), identidade.escapar("; ".join(exige))])
    return tabela_simples(["Module", "What it does", "Alters the device?", "Requires"], linhas,
                          [0.22, 0.42, 0.2, 0.16])


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
def conteudo() -> list:
    h = []

    # --- Contents
    h += [NextPageTemplate("conteudo"), PageBreak()]
    sumario = TableOfContents()
    sumario.levelStyles = [SUMARIO_1, SUMARIO_2]
    h += [Paragraph("Contents", H1), Spacer(1, 10), sumario]

    # --- Language note + legal notice (before chapter 1). Not in the contents.
    h += [PageBreak(),
          Paragraph("Note — the program is in Portuguese", H2),
          caixa("nota",
                "The <b>program</b> and the <b>documents it generates</b> (reports and the "
                "expert report) are in <b>Portuguese</b>. This English manual explains how to "
                "operate it; the names of buttons and screens are quoted in Portuguese, <b>as "
                "they appear in the interface</b>, so you can find them without hesitation. The "
                "module tables in chapters 4, 6 and 8 also show the names and descriptions in "
                "Portuguese, because they are read from the program itself."),
          Paragraph("Notice — personal data processing", H2),
          caixa("atencao",
                "Extracting and examining data from a device is <b>personal data "
                "processing</b>. Use the tool only with a <b>legal basis</b> (a court order, a "
                "request from a competent authority, or the documented consent of the data "
                "subject) and in accordance with the rules applicable in the country where the "
                "examination is performed. Collect only what is necessary and store it "
                "securely. The lawfulness of the examination is the responsibility of whoever "
                "performs it and whoever authorizes it."),
          ]

    # =====================================================================
    h += capitulo(1, "Introduction",
                  "Hexis Forensics is a free tool for the extraction and preservation of "
                  "digital evidence from Android phones, iPhones and storage media. It was "
                  "built for routine work: collect what answers the examination, record how "
                  "each piece of data was obtained, and deliver documents that stand on their "
                  "own.")
    h += [secao("Why this tool exists"),
          p("Much of the examination work on phones and media is routine and does not need "
            "advanced features. Even so, those who do this work usually run into two bad roads."),
          sub("Paid tools are expensive for routine work"),
          itens([
              "<b>Expensive license.</b> Annual, per-station licenses priced in dollars make "
              "small-scale use unfeasible.",
              "<b>Idle capacity.</b> You pay for advanced features that simple, recurring cases "
              "never use.",
              "<b>Expensive training.</b> Certified training is costly, when most cases call "
              "for solid, elementary training.",
              "<b>Moving the device.</b> The evidence travels to wherever the tool is: more "
              "steps in the chain of custody and more risk to volatile data.",
          ]),
          sub("Free tools are free, but not simple"),
          itens([
              "<b>Hard to operate.</b> Command line, technical environment and little "
              "documentation: not very friendly for the ordinary IT user.",
              "<b>No forensic documentation.</b> In general they do not produce a chain of "
              "custody or an expert report: the examiner builds all of that separately.",
          ]),
          p("In practice, the free tool is cheap to download and expensive to learn: the "
            "complexity of operating it turns into the complexity and cost of training."),
          caixa("nota", "What was missing: a tool that is simple, documented and free of "
                "license cost for routine acquisition."),

          secao("The proposal"),
          p("Routine logical acquisition, simple to operate, with chain of custody, hash "
            "sealing and documents. Each pain has an answer:"),
          tabela_simples(["Pain", "Answer"], [
              ["<b>Expensive license</b>", "No license cost."],
              ["<b>Idle capacity</b>", "Focus on what routine needs: Android, iPhone and media."],
              ["<b>Expensive training</b>", "Guided operation, screen by screen, within reach of "
               "solid, elementary training."],
              ["<b>Moving the device</b>", "Windows 10 or 11 and a USB cable, wherever the "
               "device is."],
              ["<b>Complexity of free tools</b>", "Graphical interface, no command line."],
              ["<b>No forensic documentation</b>", "Chain of custody, hash sealing and expert "
               "report already included."],
          ], [0.32, 0.68]),

          secao("What it does, and how far it goes"),
          p("The reach of each collection depends on the platform and the type of extraction. "
            "The table summarizes what version 1.0 does:"),
          tabela_simples(["Platform", "Logical", "File system", "Physical (bit by bit)"], [
              ["<b>Android</b>", "Yes. On a common device, with no elevated privilege.",
               "Partial. Without root, only the shared storage: the apps' databases do not come.",
               "Only with root. Data partition, DES profile. Without root, it fails explicitly."],
              ["<b>iPhone</b>", "Yes. Common and encrypted backup.",
               "No. It would require jailbreak.",
               "No. It would require exploiting the device's boot."],
              ["<b>USB drives and disks</b>", "Yes. Copy of the user's folders and an index with "
               "hash.",
               "Partial. Index of the whole drive (path, dates and SHA-256), without copying the "
               "content; the copy reaches only the user's folders.",
               "Yes. .img image of the volume; requires Administrator and the DES profile."],
          ], [0.16, 0.26, 0.33, 0.25]),
          Spacer(1, 6),
          p("<b>Focus: routine logical acquisition.</b> Full file system and physical image "
            "only with elevated privilege, never on the iPhone, and declared as such."),

          secao("How it works, in five steps"),
          passos([
              "<b>Connect.</b> Android over USB debugging, iPhone paired, media with a "
              "write blocker.",
              "<b>Declare the method.</b> The Method and limitations screen states what the "
              "collection does not reach.",
              "<b>Identify the item.</b> Case, authorization, make and model, seal and two "
              "photographs.",
              "<b>Extract with hash.</b> A manifest with the SHA-256 of each file: the seal of "
              "the acquisition.",
              "<b>Generate the documents.</b> Reports, selected conversations and the expert "
              "report.",
          ]),

          secao("The documents it generates"),
          p("Each acquisition generates documents that stand on their own:"),
          itens([
              "<b>Extraction Report.</b> Timeline of the procedure, environment, modules, "
              "outcome and the hash manifest.",
              "<b>Content Report.</b> Messages, calls and contacts interpreted, with the origin "
              "of each line.",
              "<b>Selected conversations.</b> In PDF, only the relevant conversations, complete.",
              "<b>Expert Report.</b> The final document, signed by the examiner of the session.",
          ]),
          p("All of them are written <b>outside</b> the sealed acquisition, which is never "
            "altered (chapter 9)."),

          secao("The differentiator: not collected is not does-not-exist"),
          p("Each module ends in one of three states:"),
          tabela_simples(["State", "What it means"], [
              ["<b>Completed</b>", "The module obtained what it set out to."],
              ["<b>Completed with a caveat</b>", "It obtained part, and declared what it did not "
               "reach."],
              ["<b>Obtained no data</b>", "None of that material was acquired, which does not "
               "mean the data does not exist on the device."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          p("In practice:"),
          itens([
              "<b>Query refused by the system:</b> the refusal is preserved and declared; an "
              "empty response is recorded as such.",
              "<b>Encrypted backup not decrypted:</b> “nothing is asserted” about the content.",
              "<b>Locked device:</b> the report says why it did not extract.",
          ]),
          p("<b>Why it matters:</b> the absence of a piece of data in the material is never "
            "presented as the absence of that data on the device."),

          secao("The tool's principles"),
          p("Three ideas guide every screen and every document. Knowing them helps you read "
            "what the tool says — and what it, on purpose, does not say."),
          itens([
              "<b>What is necessary, well recorded.</b> The tool does not measure quality by "
              "volume. It collects what matters to the examination and documents the provenance "
              "of each piece of data: which file it came from, by which route, with which hash.",
              "<b>Never assert what was not verified.</b> When a piece of data is not obtained, "
              "the document says WHY — the system refused, the module was not run, the backup "
              "did not contain it. The absence of data in the material is never presented as "
              "the absence of data on the device.",
              "<b>Every change to the device is recorded and justified.</b> The modules that "
              "touch the device are flagged, start unchecked and leave in the procedure record "
              "what was done and why.",
          ]),
          secao("What the tool does not do"),
          p("Being honest about its reach is part of the method. The tool does <b>not</b> "
            "unlock a device, does not bypass a passcode, does not recover deleted data, does "
            "not extract from the cloud, does not perform physical extraction of an iPhone, "
            "and, on Android, only performs physical extraction with root. It also does not "
            "decode every existing app. For those cases there are specialized tools. Hexis "
            "Forensics covers routine logical acquisition — and what surrounds the extraction: "
            "chain of custody, hash sealing, expert report, examination without extraction and "
            "documented delivery."),
          secao("The DEFR and DES roles"),
          p("The ISO/IEC 27037 standard distinguishes the <b>DEFR</b> (first responder: "
            "identifies, collects and preserves following a procedure) from the <b>DES</b> "
            "(specialist: decides when something falls outside the procedure). Each module "
            "declares the minimum profile it requires. The tool stops no one — it informs, and "
            "the report records it."),
          secao("Compliance and transparency"),
          sub("Compliance"),
          itens([
              "<b>ISO/IEC 27037.</b> Identification, collection, acquisition and preservation.",
              "<b>Chain of custody.</b> Seal, photographs and a record of each step, in "
              "accordance with the law applicable in each country.",
          ]),
          sub("Transparency"),
          itens([
              "<b>Installer with a published hash.</b> The SHA-256 lets you verify the file "
              "before installing (chapter 2).",
              "<b>Tested on real devices.</b> Motorola, Samsung, iPhone 11 and a USB drive, "
              "with what was proven on each one (chapter 11).",
              "<b>Declared limitations.</b> For example: the agent not verified on Xiaomi; the "
              "IMEI not delivered without root from Android 10 on.",
          ]),
          secao("Going further: the Official Training"),
          p("This manual teaches you to operate the tool. The <b>Official Hexis Forensics "
            "Training</b> goes further: it teaches the digital forensics that underpins each "
            "screen — chain of custody, integrity by hash, the limits of each type of "
            "extraction and the writing of the expert report. There is also an offering in "
            "partnership with higher-education institutions, and deployment with team training "
            "for police and forensic agencies."),
          ]

    # =====================================================================
    h += capitulo(2, "Installation and first access",
                  "From the installer to the first session: requirements, creating your "
                  "examiner profile and the recovery code, which is the only way back if you "
                  "forget the password.")
    h += [secao("Requirements"),
          itens([
              "A computer with <b>Windows 10 or 11</b>.",
              "A <b>USB data cable</b> (some cables only charge and will not work).",
              "For <b>iPhone</b>: the <b>Apple Devices</b> app (Microsoft Store) or iTunes, "
              "which install the service that communicates with the device.",
              "For <b>computer disks</b>: a USB dock or adapter and a hardware <b>write "
              "blocker</b> (see chapter 8).",
          ]),
          secao("Verify the installer before installing"),
          p("Along with the installer, its <b>SHA-256 hash</b> is published — the fingerprint "
            "of the file. Verifying it guarantees that the downloaded file is exactly the one "
            "published, without corruption or tampering. It is the same logic as the seal of "
            "the acquisitions."),
          passos([
              "In the folder where the installer is, right-click an empty space and choose "
              "<b>Open in Terminal</b>.",
              "Type <b>Get-FileHash .\\HexisForensics-Setup-1.0.0.exe</b> and press Enter.",
              "Compare the value in the <b>Hash</b> column with the published one. A single "
              "different character means a different file: do not install.",
          ]),
          secao("Installation"),
          p("Run the installer and follow the screens. Check the option <b>Criar atalho na "
            "Área de Trabalho</b> (create a Desktop shortcut). Cases are kept in the "
            "<b>HexisForensics-Casos</b> folder, inside your Windows user folder — outside the "
            "program folder, so that an update never reaches the evidence. To update, just "
            "install the new version over the old one: cases and examiners are preserved."),
          sub("The blue Windows warning"),
          p("The installer is free and has no paid digital signature. For that reason, on the "
            "first run, Windows shows the <b>“Windows protected your PC”</b> screen, with an "
            "unknown publisher. It is a warning, not a virus diagnosis:"),
          passos([
              "Click <b>More info</b>.",
              "Check the file name and click <b>Run anyway</b>.",
          ]),
          caixa("nota", "If <b>Smart App Control</b> on Windows 11 is on, it blocks the "
                "installer without offering the button: it requires a digital signature, which "
                "this version does not have. There is no portable version. The ways out are to "
                "install on another computer, ask your IT department to allow the program, or "
                "<b>run from source</b> (next section)."),
          secao("Alternative: run from source"),
          p("When the installer is blocked and there is no way to allow it, the tool runs "
            "directly from source, like any open-source project — there is no installation, "
            "the same suite is run by Python. It takes a few more steps, but it does not depend "
            "on a digital signature."),
          passos([
              "Install <b>Python 3.13</b> from <b>python.org</b> (under Downloads, choose the "
              "Windows installer for version <b>3.13</b>). <b>Do not use 3.14</b>: one of the "
              "iPhone libraries does not yet have a ready version for it. On the first screen "
              "of the Python installer, check <b>Add python.exe to PATH</b>.",
              "Download the code from the project's <b>Releases page</b>: "
              "<b>github.com/HexisForensics/HexisForensics/releases</b>. On the most recent "
              "version, download <b>Fonte (ZIP)</b> (the source ZIP). Do <b>not</b> use "
              "<b>Code → Download ZIP</b> from the main page — that brings the development "
              "version, with no tagged release.",
              "<b>Verify the ZIP's hash</b>, as with the installer: in the file's folder, "
              "<b>Open in Terminal</b> and "
              "<b>Get-FileHash .\\HexisForensics-1.0.0-fonte.zip</b>. The value must be "
              "identical to the one published in the Release.",
              "Extract the folder. Open it, right-click an empty space and choose <b>Open in "
              "Terminal</b>.",
              "Type <b>py -m pip install -r requirements.txt</b> and press Enter. Wait for the "
              "libraries to install (it takes a while the first time).",
              "Type <b>py main.py</b> and press Enter. The tool opens on the entry screen, just "
              "like the installed version.",
          ]),
          caixa("nota", "Running from source, cases are kept in <b>HexisForensics-Casos</b>, in "
                "your Windows user folder — the same as the installed version, and "
                "<b>outside</b> the program folder, so that updating (downloading the new ZIP) "
                "never reaches the acquisitions. The <b>adb.exe</b> already comes in the ZIP, so "
                "Android extraction works with no extra step; for the iPhone, the Apple Devices "
                "app still applies (Requirements)."),
          secao("First access: your examiner profile"),
          p("The tool opens on the <b>entry screen</b>. Each examiner has their own profile and "
            "password: that is what identifies who performed each extraction and who signs each "
            "expert report."),
          figura("01_entrada", "Entry screen: choose your name and type your password.",
                 altura_max=9 * cm),
          passos([
              "The first time, click <b>Novo examinador</b> (New examiner).",
              "Fill in the <b>name</b> as it should appear in the documents, the "
              "<b>professional registration</b> and the <b>institution or laboratory</b>.",
              "Create a <b>password</b> of at least 6 characters and repeat it.",
              "Click <b>Cadastrar e entrar</b> (Register and enter).",
              "Write down or print the <b>recovery code</b> (next section), check the "
              "confirmation and click <b>Continuar</b> (Continue).",
          ]),
          figura("02_novo_examinador", "Registration of a new examiner.", altura_max=9 * cm),
          secao("The recovery code"),
          p("When you create the password, the tool shows a 16-character code, in four groups. "
            "It appears <b>only once</b>. It is the only way to get in if you forget the "
            "password: no one — not even the maker — can reset it. Once used, the code is "
            "replaced by another, which also appears once."),
          figura("03_codigo_recuperacao", "The recovery code, with the print and copy options.",
                 altura_max=9 * cm),
          caixa("atencao", "Keep the code away from the computer: printed in a folder, in a "
                "password vault, in a sealed envelope. Whoever loses the password <b>and</b> the "
                "code must create a new profile. The old acquisitions stay under their name, "
                "because the name is recorded inside the seal of each one."),
          secao("I forgot my password"),
          passos(["On the entry screen, choose your name and click <b>Esqueci minha senha</b> "
                  "(I forgot my password).",
                  "Type the recovery code (with or without dashes, upper or lower case).",
                  "Choose the new password and click <b>Redefinir e entrar</b> (Reset and "
                  "enter).",
                  "Write down the <b>new</b> code that appears: the old one is no longer valid."]),
          secao("During the session"),
          itens([
              "Your name appears in the <b>footer of the side bar</b>, with the time you "
              "entered.",
              "<b>Trocar examinador</b> (Switch examiner) returns to the entry screen, for "
              "someone else to log in. You cannot switch during an extraction.",
              "After <b>15 minutes of inactivity</b>, the screen locks and asks for the "
              "password again. An extraction in progress <b>keeps running</b> in the "
              "background.",
              "Five wrong passwords in a row lock that examiner for 10 minutes.",
              "In <b>Examinadores</b> (Examiners, in the side bar) you correct your data, change "
              "the password, generate a new recovery code or delete your profile. The <b>Novo "
              "examinador</b> button opens the registration of another person: they create "
              "their own password and receive their own code, and become the session's "
              "examiner. No one sees or alters another examiner's data.",
              "Logins, lockouts, recoveries and deletions are kept in the station's <b>access "
              "log</b>.",
          ]),
          caixa("nota", "The record of each acquisition says: “session opened with the "
                "examiner's password on this station”. The password guarantees <b>authorship</b> "
                "— no one operates in someone else's name by carelessness. It does not prove "
                "identity (a shared password gets in too) and does not protect the case files, "
                "which sit on the disk."),
          ]

    # =====================================================================
    h += capitulo(3, "Preparing the Android phone",
                  "Without elevated privilege, Android extraction is done through ADB, "
                  "Android's own debugging tool. For that, the device has to authorize the "
                  "computer.")
    h += [secao("Step 1 — Enable the Developer options"),
          passos([
              "Open <b>Settings → About phone</b> (on Motorola, <b>Settings → System → About "
              "device</b>; on others: “Software information”).",
              "Scroll to the bottom and tap <b>7 times</b> on <b>Build number</b> (on some "
              "devices: “MIUI version”, “OS version” or “Version number”). The device may ask "
              "for the unlock code.",
              "The message <b>“You are now a developer”</b> appears — or, if it was already on, "
              "“You are already a developer”.",
          ]),
          par_de_figuras("android_02_numero_versao", "Build number: tap 7 times. "
                         "(IMEI and addresses covered in this manual.)",
                         "android_03_desenvolvedor", "The developer-mode confirmation."),
          secao("Step 2 — Turn on USB debugging"),
          passos([
              "Open <b>Settings → System → Advanced → Developer options</b> (on some devices, "
              "under “Additional settings”).",
              "Turn on <b>USB debugging</b>.",
              "Also turn on <b>Stay awake</b>: the screen does not go off while the device is on "
              "the cable, and the connection does not drop in the middle of the extraction.",
          ]),
          par_de_figuras("android_04_depuracao_usb", "USB debugging on.",
                         "android_05_permanecer_ativo", "Stay awake on."),
          secao("Step 3 — Authorize the computer"),
          passos([
              "Connect the data cable. On the device's screen, <b>Allow USB debugging?</b> "
              "appears.",
              "Check <b>Always allow from this computer</b>.",
              "Tap <b>Allow</b>.",
              "In the tool, on the <b>Android</b> page, click <b>Verificar Conexão</b> (Check "
              "connection). The status should say the device is connected and authorized.",
          ]),
          par_de_figuras("android_06_permitir_depuracao", "The authorization prompt "
                         "(reproduction: Android does not allow capturing this screen).",
                         "android_07_modo_usb", "USB preferences, if the connection drops."),
          caixa("dica", "If the prompt does not appear, or the device shows as <b>not "
                "authorized</b>: unlock the screen, tap <b>Revoke USB debugging "
                "authorizations</b> (in Developer options) and reconnect the cable. If the "
                "connection drops during the extraction, open <b>Settings → Connected devices → "
                "USB</b> and choose <b>File transfer</b>."),
          figura("04_janela_android", "Android page: device status, extraction modules and "
                 "console."),
          secao("Manufacturer specifics"),
          sub("Xiaomi (MIUI / HyperOS)"),
          p("Besides USB debugging, turn on <b>Install via USB</b> and <b>USB debugging "
            "(security settings)</b>. Both require a <b>Xiaomi account</b> signed in and, "
            "sometimes, an inserted SIM. Without them, the device refuses the agent app. "
            "<i>In this version, the agent has not yet been verified on a Xiaomi device: if the "
            "install is refused, the tool records the refusal and concludes nothing about the "
            "content.</i>"),
          sub("Samsung"),
          p("The <b>Developer options</b> appear at the end of the Settings list, right below "
            "<b>About phone</b>, after the 7 taps on <b>Software information → Build "
            "number</b>."),
          p("Verified on a <b>Galaxy A22 with Android 13 (One UI 5.1)</b>, factory settings and "
            "with no elevated privilege: the agent app was installed, collected and removed "
            "<b>with no on-screen confirmation</b> — no “Install app?”, no Play Protect, no "
            "permission request. Samsung also delivers the contact list to the common module, "
            "without the agent."),
          p("On other models or versions, <b>Play Protect</b> may ask whether the app is safe. "
            "If the question appears, confirm the install on the device's screen."),
          caixa("atencao", "Turning on USB debugging and authorizing the computer are changes "
                "to the device's configuration. The tool records them in the procedure as a "
                "requirement of the method: without them there is no logical acquisition on a "
                "device with no elevated privilege."),
          ]

    # =====================================================================
    h += capitulo(4, "Android extraction, step by step",
                  "From clicking Iniciar Extração to the sealing of the acquisition. Each step "
                  "exists to record something the expert report will need.")
    h += [secao("Choosing the modules"),
          p("The list of modules appears on the Android page. The common modules come already "
            "checked. Those that alter the device in a relevant way are <b>express "
            "selection</b>: they start unchecked and the <b>Marcar todos</b> (Check all) button "
            "does not reach them — they must be chosen one by one, on purpose."),
          secao("The sequence of screens"),
          passos([
              "Click <b>Iniciar Extração</b> (Start Extraction). The tool asks for confirmation "
              "of the session's examiner (“This extraction will be recorded as performed "
              "by…”).",
              "<b>Method and limitations</b>: what the chosen collection will not reach and what "
              "may be altered on the device. This is the moment to decide — afterward it becomes "
              "a record. Read it and click <b>Ciente — Prosseguir</b> (Understood — Continue).",
              "<b>Case</b>: create a new case or choose an existing one. A case gathers several "
              "devices; each device becomes an acquisition within it.",
              "<b>Authorization</b>: attach the document that authorizes access to the data. "
              "Continuing without attaching is allowed, but it is recorded that there was no "
              "document in sight.",
              "<b>Device and chain of custody</b>: make and model, color, condition, <b>seal "
              "number</b> (required) and at least <b>two photographs</b> of the item (front and "
              "back).",
              "The extraction begins. Follow it through the console and the status column of "
              "each module.",
          ]),
          figura("07_metodo", "Method and limitations: what the collection does not reach, "
                 "before starting.", altura_max=10 * cm),
          figura("08_caso", "New or existing case.", altura_max=8 * cm),
          figura("10_dispositivo", "Item, seal and photographs.", largura=UTIL * 0.6,
                 altura_max=10 * cm),
          secao("How to read the result"),
          p("Each module ends in one of three states, and they are not interchangeable:"),
          tabela_simples(["State", "Means"], [
              ["<b>Completed</b>", "The module obtained what it set out to."],
              ["<b>Completed with a caveat</b>", "It obtained part, and declared what it did not "
               "reach (for example, a query refused by the system)."],
              ["<b>Obtained no data</b>", "None of that material was acquired. This does "
               "<b>not</b> mean the data does not exist on the device."],
          ], [0.28, 0.72]),
          Spacer(1, 8),
          p("At the end, the tool generates the <b>hash manifest</b> (the seal of the "
            "acquisition): the SHA-256 of each acquired file. It also checks whether the device "
            "connected at the end is the same as at the start."),
          caixa("atencao", "Do not close the tool during an extraction: the acquisition would "
                "be left without a seal. If you need to stop, use <b>Cancelar</b> (Cancel) and "
                "wait for the extraction-finished message."),
          secao("The available modules"),
          p("The table below is generated from the tool's own code; the module names and "
            "descriptions appear in Portuguese, as in the program."),
          tabela_de_modulos("Android"),
          ]

    # =====================================================================
    h += capitulo(5, "WhatsApp, step by step",
                  "Without elevated privilege, the WhatsApp message database sits in a private "
                  "area of the app, out of reach. The route is WhatsApp's own local backup, "
                  "protected with a 64-digit key that the examiner knows. The screens in this "
                  "chapter are from a real device; the key appears covered.")
    h += [secao("Why this is the route"),
          p("WhatsApp writes encrypted local backups (<b>msgstore.db.crypt15</b>) in a folder "
            "the tool can copy. When the backup is protected by a <b>64-digit key</b> — and not "
            "by a password or a passkey —, whoever has the key can decrypt it. The tool "
            "decrypts it, checks the authenticity of the content and reads the conversations."),
          caixa("atencao", "Touching the backup's protection and telling WhatsApp to make the "
                "backup are <b>changes to the examined device</b>, made by the examiner. When "
                "it decrypts, the tool records them in the case addendum, together with the "
                "key."),
          secao("Step 1 — See how the backup is protected"),
          p("In WhatsApp, open <b>Settings → Chats → Chat backup</b> and scroll to "
            "<b>End-to-end encrypted backup</b>. What is written beneath it decides the route:"),
          tabela_simples(["What appears", "What to do"], [
              ["<b>Off</b>", "Go to Step 2."],
              ["<b>On · Password</b> or <b>On · Passkey</b>",
               "No good: the tool decrypts only with the 64-digit key. Tap the option, tap "
               "<b>Turn off</b>, enter the backup password and confirm. Then, Step 2."],
              ["<b>On · 64-digit key</b>",
               "Good, if someone has the key written down. WhatsApp only shows the key when it "
               "is created: without it written down, turn off and create a new one (Step 2)."],
          ], [0.4, 0.6]),
          Spacer(1, 6),
          par_de_figuras("whatsapp_02_criptografado", "On · Password: no good.",
                         "whatsapp_03_tela_criptografia", "Backup protected with a password: "
                         "tap Turn off."),
          par_de_figuras("whatsapp_04_desativado", "Confirm turning it off.",
                         "whatsapp_05_apos_desativar", "Now: Off."),
          secao("Step 2 — Turn it on with the 64-digit key"),
          passos([
              "Tap <b>End-to-end encrypted backup</b>.",
              "<b>DO NOT tap the green “Use passkey” button.</b> Tap <b>More options</b>.",
              "Choose <b>64-digit encryption key</b> (not “Password”).",
              "Tap <b>Generate your 64-digit key</b>.",
              "The key appears: 16 groups of 4 characters. <b>Write it down</b> — or read it "
              "over the cable (see tip). Tap <b>Continue</b>.",
              "WhatsApp shows the key again for checking. Tap <b>I saved my 64-digit key</b>.",
              "Tap <b>Create</b>. The process finishes in the background.",
          ]),
          par_de_figuras("whatsapp_06_ativar", "The trap: the green button is no good. Tap "
                         "More options.",
                         "whatsapp_07_mais_opcoes", "Choose the 64-digit key."),
          par_de_figuras("whatsapp_08_gerar_chave", "Generate the key.",
                         "whatsapp_09_chave", "The key (covered in this manual)."),
          par_de_figuras("whatsapp_10_confirmar_chave", "Check and confirm you saved it.",
                         "whatsapp_11_criar", "Create the protected backup."),
          caixa("dica", "With the cable connected, the key can be read from the screen by ADB, "
                "with no typing error: the screen text is obtained with <b>uiautomator dump</b>. "
                "When in doubt, photograph the key screen and add the photo to the case."),
          secao("Step 3 — Make the backup ON THE DEVICE"),
          passos([
              "In <b>Chat backup</b>, check that <b>Google Account</b> is <b>None</b> and "
              "<b>Back up automatically</b> is <b>Off</b> (in older versions: <b>Back up to "
              "Google Drive</b> set to <b>Never</b>).",
              "Tap <b>Back up</b> and wait for it to finish.",
              "Check the <b>Local:</b> line — it should show the current time.",
          ]),
          par_de_figuras("whatsapp_12_ativado_chave", "Protected with the 64-digit key.",
                         "whatsapp_13_backup_feito", "Local backup done: check the time under "
                         "“Local”."),
          caixa("atencao", "Make the backup <b>on the day of the examination</b>, after turning "
                "on the key. An old backup — or one made with a password — does not open with "
                "the new key and does not bring the recent messages."),
          secao("Step 4 — In the tool: extract"),
          p("Run the extraction normally (chapter 4), with the module <b>WhatsApp — Mídia e "
            "Backups</b> checked. It copies the media and the encrypted backups and records, by "
            "asking the device itself, <b>when each backup was written</b>."),
          secao("Step 5 — In the tool: decrypt"),
          passos([
              "Open <b>Casos e Documentos</b> (Cases and Documents), choose the case and the "
              "acquisition.",
              "Click <b>Decifrar backup</b> (Decrypt backup).",
              "Type the key into the 16 fields (or paste the whole key into any field).",
              "Click <b>Decifrar</b> (Decrypt). The decrypted backup goes to the case's "
              "<b>decifrados</b> folder, <b>outside</b> the sealed acquisition, with its "
              "provenance alongside. The key is recorded in the case addendum, so that another "
              "examiner can repeat the decryption.",
              "Next, the <b>Content Report</b> is generated, with the conversations.",
          ]),
          figura("18_chave_whatsapp", "The 64-digit key, in 16 groups, in the tool.",
                 largura=UTIL * 0.6, altura_max=9 * cm),
          secao("Step 6 — Read and select the conversations"),
          p("The Content Report brings the spreadsheet (CSV) and the HTML notebook with the "
            "full text. Very long conversations appear in the PDF as an index, so the document "
            "does not run to thousands of pages. For the expert report, use <b>PDF de conversas "
            "selecionadas</b> (PDF of selected conversations): check the relevant conversations "
            "and the tool generates the PDF of just those, complete, with the origin of each "
            "message."),
          figura("17_conversas", "Choosing the conversations that go into the PDF."),
          secao("The backup date in the documents"),
          p("The decrypted content portrays the device <b>on the date the backup was "
            "written</b>, not on the day of the examination. For that reason the report and the "
            "expert report carry the <b>Source note</b>: the backup date (reported by the "
            "device itself and recorded in the seal), the most recent message it contains and "
            "the warning that later messages are not in the material."),
          secao("When the backup does not open"),
          itens([
              "<b>Key typed wrong</b>: nothing is decrypted. Check it group by group.",
              "<b>Backup protected by a password or passkey</b>: it does not open with any key. "
              "Redo steps 1 to 3 and extract again.",
              "<b>Backup made before turning on the key</b>: it does not open with it. Make a "
              "new backup (step 3) and extract again.",
              "<b>.crypt14 or earlier backup</b>: it does not open with the 64-digit key.",
              "<b>No backup on the device</b>: the module says it only found media. This does "
              "not mean an absence of messages.",
          ]),
          ]

    # =====================================================================
    h += capitulo(6, "iPhone",
                  "Without jailbreak, the route is the iPhone's local backup — the same one "
                  "iTunes would make —, obtained after the device trusts the computer.")
    h += [secao("Before you start: the computer"),
          passos([
              "Install the <b>Apple Devices</b> app (Microsoft Store) or iTunes. It installs "
              "the Windows service that talks to the iPhone. You do not need to open it or sync "
              "anything — and <b>do not</b> sync: syncing writes to the device.",
              "If the iPhone was already on the cable during the install, <b>disconnect and "
              "connect it again</b>: the service only sees the device connected after it has "
              "started running.",
          ]),
          secao("Before you start: the iPhone"),
          passos([
              "The iPhone must have <b>finished the initial setup</b>. On a restored device, "
              "iOS refuses the backup until then (the tool shows “initial setup not completed — "
              "code 212”). The <b>Apple account</b> screen can be skipped: tap <b>Forgot "
              "password or don't have an Apple Account?</b> and choose to set it up later. You "
              "do not need to create an account for the examination.",
              "Unlock the screen, connect the cable and tap <b>Trust</b> when <b>Trust This "
              "Computer?</b> appears. The iPhone asks for the unlock code.",
              "In the tool, on the <b>iPhone</b> page, click <b>Verificar Conexão</b> (Check "
              "connection).",
          ]),
          figura("05_janela_iphone", "iPhone page."),
          caixa("atencao", "During the backup, the iPhone must stay <b>unlocked</b>. With "
                "<b>Low Power Mode</b> on, auto-lock is stuck at 30 seconds. Prefer to keep the "
                "screen active by tapping it. If you need to change <b>Auto-Lock</b> or turn "
                "off Low Power Mode, that is a change made to the examined device: record it in "
                "the examination notes."),
          secao("The modules"),
          tabela_de_modulos("iOS"),
          Spacer(1, 8),
          secao("Common backup or encrypted backup"),
          p("The common backup does not touch the device's configuration and brings iMessage "
            "and SMS, the address book, the camera roll photos and app data (WhatsApp "
            "included). But iOS only includes the <b>call log</b> and other sensitive data in "
            "the <b>encrypted</b> backup. The temporary-password module sets a password "
            "generated by the tool, makes the encrypted backup and <b>removes the password</b> "
            "at the end, verifying the removal."),
          tabela_simples(["Comparison", "Common backup", "Encrypted backup (temporary password)"],
                         [
              ["Alters the device?", "No (only the pairing, which every backup requires)",
               "Yes: sets and removes a backup password, with a record"],
              ["Messages, address book, WhatsApp", "Yes, read directly", "Yes, after decrypting"],
              ["Call log", "<b>No</b> — iOS does not include it", "Yes, after decrypting"],
              ["Photos and their GPS", "Yes", "Not read in this version"],
              ["Code on the iPhone screen", "Once (trust)", "Up to three times"],
          ], [0.28, 0.33, 0.39]),
          Spacer(1, 8),
          p("Both can be checked together: each backup goes to its folder (<b>backup_ios</b> "
            "and <b>backup_ios_cifrado</b>), and the content is copied twice. In the encrypted "
            "backup, the iPhone asks for the code <b>up to three times</b>: to accept the "
            "temporary password, sometimes during the backup and to remove it. Keep the device "
            "at hand."),
          caixa("atencao", "If the owner has already set a backup password, the "
                "temporary-password module <b>does not run</b> — changing the owner's password "
                "would be an irreversible change. Use the common backup: it comes out encrypted "
                "with the owner's password, and the content can only be read with it (Decifrar "
                "backup button)."),
          secao("Decrypt the backup"),
          passos([
              "Open <b>Casos e Documentos</b> (Cases and Documents), choose the case and the "
              "iPhone's acquisition.",
              "Click <b>Decifrar backup</b> (Decrypt backup).",
              "When the backup was made with the temporary password, the password <b>comes "
              "already filled in</b>: the tool reads it from the acquisition's "
              "<b>senha_do_backup.txt</b> file, and only if it matches the seal. Confirm.",
              "The decrypted databases go to the case's <b>decifrados</b> folder, outside the "
              "sealed acquisition, each with its provenance alongside. The password is recorded "
              "in the case addendum, so that another examiner can repeat the decryption.",
          ]),
          p("The password also appears in the collection outcome and in the console. If the "
            "backup was encrypted with the owner's password, that is the one you type."),
          secao("What appears in the Content Report"),
          itens([
              "Each block says which backup it came from: <b>common iPhone backup</b> or "
              "<b>encrypted iPhone backup, decrypted</b>.",
              "An encrypted backup not yet decrypted: the report says that <b>nothing is "
              "asserted</b> about the content — not that it is empty.",
              "A file iOS did not put in the backup (the calls, in the common backup): the "
              "report says the backup does not contain it, and that this does not prove its "
              "absence.",
              "<b>WhatsApp</b>: texts, photos, audio, groups and shared locations, with the "
              "coordinates and the <b>open on the map</b> link. Records that WhatsApp itself "
              "generates — the encryption notice, the creation of a group — appear with the "
              "<b>System</b> sense and the note “not a typed message”. A type of record the tool "
              "does not know appears as <b>not recognized</b>, with no guess about what it is.",
              "<b>Photo locations</b>: the camera-roll photos with GPS (see chapter 9).",
          ]),
          ]

    # =====================================================================
    h += capitulo(7, "Examination without extraction",
                  "A device locked by a credential, that does not turn on or that is damaged: "
                  "the examination exists even without extraction, and the negative expert "
                  "report needs the same chain of custody.")
    h += [passos([
              "On the Android or iPhone page, click <b>Exame sem extração</b> (Examination "
              "without extraction).",
              "Follow the same case, authorization, item, seal and photograph screens.",
              "On the form, state whether the device turns on, the condition in which it was "
              "received, the battery, whether it was isolated from the network, the <b>type of "
              "lock</b> and what was attempted. The recommendation comes already filled in.",
              "If the device turns on, the tool <b>attempts the connection without altering "
              "it</b> and keeps the response as evidence: on Android, the ADB listing (for "
              "example, “NOT AUTHORIZED”); on iPhone, a session with no pairing request.",
              "Generate the <b>Expert Report</b> in Cases and Documents: the “Examination "
              "without Extraction” version comes out.",
          ]),
          figura("11_exame_sem_extracao", "Device condition and attempts.", largura=UTIL * 0.6,
                 altura_max=10 * cm),
          p("The conclusion states that extraction was not possible, and why — and that this "
            "<b>does not</b> allow any conclusion about the content of the device."),
          ]

    # =====================================================================
    h += capitulo(8, "Disks and USB drives",
                  "The Storage platform examines drives connected to the computer: USB drives, "
                  "external disks and the disk removed from a computer under examination.")
    h += [caixa("atencao", "The disk of a computer under examination is <b>removed</b> and "
                "connected to the station through a dock or adapter, with a hardware <b>write "
                "blocker</b> between the two. The tool does not replace the blocker. The "
                "examiner's own station appears in the list, identified, so it is not chosen by "
                "mistake."),
          figura("06_janela_armazenamento", "Storage page: choosing the drive."),
          tabela_de_modulos("Computador"),
          Spacer(1, 8),
          p("The <b>Volume Image</b> requires opening the tool as Administrator. A volume "
            "encrypted with BitLocker is detected and reported."),
          ]

    # =====================================================================
    h += capitulo(9, "Cases and Documents",
                  "Everything you do after the extraction: documents, examination of the "
                  "material, delivery and organization of the cases — without having to open "
                  "the folders in Windows.")
    h += [figura("12_casos_ficha", "Cases and Documents: cases, record, devices and actions."),
          secao("The documents"),
          tabela_simples(["Document", "What it is for"], [
              ["<b>Extraction Report</b>", "Timeline of the procedure, environment, modules, "
               "outcome and the hash manifest."],
              ["<b>Content Report</b>", "The messages, calls and contacts interpreted: CSV "
               "spreadsheets, HTML notebook and PDF, with the origin of each line."],
              ["<b>PDF of selected conversations</b>", "Only the relevant conversations, "
               "complete."],
              ["<b>Expert Report</b>", "The final document, signed by the session's examiner."],
          ], [0.3, 0.7]),
          Spacer(1, 8),
          p("The documents open in the <b>tool's viewer</b> (pages, zoom, print, save a copy) "
            "and are listed on the <b>Documentos</b> (Documents) tab. They are written "
            "<b>outside</b> the sealed acquisition, which is never altered."),
          figura("15_visualizador", "PDF viewer.", altura_max=10 * cm),
          figura("22_laudo_pagina", "The first page of an expert report.", largura=UTIL * 0.6,
                 altura_max=12 * cm),
          secao("Photo locations"),
          p("The Content Report brings the section <b>Photo locations (GPS recorded in the "
            "images)</b>: one line per photo that has coordinates in the EXIF — the data the "
            "camera records inside the file. It applies to Android JPEG and iPhone HEIC."),
          tabela_simples(["Column", "What it is"], [
              ["Date and time", "That of the <b>clock of the device</b> that took the photo."],
              ["GPS time (UTC)", "That of the <b>satellites</b>, recorded with the coordinate. "
               "It does not depend on the device's clock: if it was wrong, this is the "
               "reference."],
              ["Latitude, longitude, altitude", "Where the photo was taken, according to the "
               "EXIF."],
              ["Camera", "Maker and model recorded in the file."],
              ["Map", "<b>Open on the map</b> link, clickable in the PDF."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          itens([
              "Only photos that <b>match the seal</b> are included. A photo altered after the "
              "acquisition is rejected, with the reason.",
              "The photographs the examiner takes of the item (front and back) are <b>not</b> "
              "included: the examination table is not a place where the device has been.",
              "The same photo copied by two modules counts only once.",
              "A <b>0,0</b> coordinate — typical of a camera with no GPS signal — does not "
              "become a location: it goes to the discards, with the reason.",
          ]),
          caixa("atencao", "The coordinate says where the <b>photo</b> was taken, not where the "
                "device was. The EXIF is editable, and a photo received from someone else "
                "carries the location of their device. Messaging apps usually strip the EXIF: a "
                "photo with no GPS does not prove the device does not record location."),
          secao("PDF of conversations"),
          p("The <b>PDF de conversas selecionadas</b> (PDF of selected conversations) button "
            "uses the acquisition marked in the list. The window title shows the case and the "
            "acquisition: if the list comes up empty, first check that it is the right "
            "acquisition."),
          secao("Examine the material: the Material tab"),
          p("The <b>Material</b> tab shows the acquisition's folders and files, with the "
            "preview (photo, text, spreadsheet, PDF, database tables) and the <b>check of the "
            "SHA-256 against the seal</b>: matches, DIVERGES or not listed. Everything is "
            "read-only."),
          figura("14_casos_material", "Material tab."),
          caixa("dica", "Prefer the Material tab to Windows Explorer. While browsing, Explorer "
                "can create hidden files (Thumbs.db, desktop.ini) inside the sealed folder, and "
                "the check then flags an added file."),
          secao("Deliver: Export for delivery"),
          passos([
              "On the Documents tab, select documents — or, on the Material tab, files and "
              "folders (Ctrl and Shift for several).",
              "Click <b>Exportar para entrega</b> (Export for delivery) or <b>Exportar "
              "selecionados</b> (Export selected).",
              "Choose the destination (USB drive, folder) and write the purpose or the "
              "recipient.",
              "The tool copies, checks each copy by its SHA-256 and generates the <b>delivery "
              "receipt</b> (PDF and text), with signature fields. The delivery is recorded in "
              "the case.",
          ]),
          figura("16_entrega", "Export for delivery.", largura=UTIL * 0.8, altura_max=6 * cm),
          secao("Amend, attach, delete"),
          itens([
              "<b>Retificar Dados do Caso</b> (Amend Case Data) and <b>Anexar Autorização</b> "
              "(Attach Authorization) enter as a case <b>addendum</b>: the original is "
              "preserved and what changed is recorded.",
              "<b>Excluir caso</b> (Delete case) requires the case name to be typed, refuses a "
              "case with an acquisition still unsealed, and sends everything to the "
              "<b>Windows Recycle Bin</b> (restorable). The deletion is kept in the access log.",
          ]),
          ]

    # =====================================================================
    h += capitulo(10, "Chain of custody and integrity",
                  "How the tool proves the material has not changed since collection.")
    h += [secao("The seal of each acquisition"),
          p("At the end of the extraction, the <b>manifesto_hashes.txt</b> file receives the "
            "SHA-256 of each acquired file. The hash of the manifest itself appears in the "
            "footer of every page of the documents. Altering any file, or the manifest, changes "
            "that number."),
          secao("Check the integrity"),
          p("In the side bar, <b>Cadeia de Custódia</b> (Chain of Custody) checks an "
            "acquisition against its manifest and records the result of the check (no check "
            "erases another)."),
          figura("21_cadeia_custodia", "Integrity check.", altura_max=9 * cm),
          secao("Where each thing lives"),
          tabela_simples(["Case folder", "Content"], [
              ["<b>&lt;platform&gt;_&lt;date&gt;_&lt;time&gt;</b>", "The sealed acquisition. "
               "Never rewritten."],
              ["<b>documentos</b>", "Extraction Report, Expert Report, Conversations."],
              ["<b>relatorios</b>", "Content Reports (CSV, HTML, PDF)."],
              ["<b>decifrados</b>", "Decrypted backups, with their provenance."],
              ["<b>complementos</b>", "Amendments, authorizations, decryptions, deliveries."],
          ], [0.38, 0.62]),
          ]

    # =====================================================================
    h += capitulo(11, "Tested devices and limitations",
                  "The tool states what it verified and what it did not verify — including "
                  "about itself. This is the list of devices on which version 1.0 was proven, "
                  "and of the known limitations.")
    h += [secao("Where version 1.0 was proven"),
          tabela_simples(["Device", "System", "What was proven"], [
              ["Motorola moto x4", "Android 9", "Full extraction, WhatsApp via the 64-digit "
               "key, photos with GPS"],
              ["Samsung Galaxy A22", "Android 13 (One UI 5.1)", "Full extraction, agent app, "
               "shifted-clock alert"],
              ["Android emulator", "Android 13, with elevated privilege", "Modules that require "
               "elevated privilege, WhatsApp"],
              ["iPhone 11", "iOS 18.6.2", "Common and encrypted backup, decryption, WhatsApp, "
               "photos with GPS"],
              ["USB drive (7.28 GiB)", "Windows 11", "All four modules, including the volume "
               "image"],
          ], [0.24, 0.26, 0.5]),
          Spacer(1, 8),
          p("Other models and versions tend to work by the same route, but were not verified. "
            "When a module fails on a device, the tool records the refusal and concludes "
            "nothing about the content."),
          secao("Known limitations"),
          itens([
              "<b>Xiaomi, Redmi and POCO (MIUI / HyperOS)</b>: the agent app was not verified. "
              "These devices usually require “Install via USB” and a Xiaomi account; the "
              "install may be refused. The limitation is stated in the module itself.",
              "<b>Android 8 or earlier</b>: out of scope for this version. On a Galaxy J5 Prime "
              "with Android 7, the File System Dump stopped early in the copy of the internal "
              "storage and still showed “Completed”; WhatsApp Business in the old location is "
              "not searched. On a device like that, check each module's reconciliation or use "
              "another tool.",
              "<b>Android 12 onward</b> no longer has the system backup: SMS and calls are read "
              "directly; when the system refuses that reading, they come in through the agent "
              "app, which is express selection.",
              "<b>IMEI</b>: from Android 10 onward, the system does not deliver it without "
              "elevated privilege. The tool records each route attempted and declares that it "
              "did not obtain it.",
              "<b>WhatsApp on Android</b>: only the backup protected by the 64-digit key "
              "(crypt15) is decrypted. The WhatsApp downgrade module has not yet been tested on "
              "a real device.",
              "<b>iPhone</b>: the photos from the encrypted backup are not read in this version "
              "(those from the common backup, yes). With a backup password set by the owner, "
              "only the common backup, decrypted with the owner's password.",
              "<b>Out of reach</b>: device unlocking, passcode bypass, physical extraction of a "
              "phone without elevated privilege and recovery of deleted data.",
          ]),
          ]

    # =====================================================================
    h += capitulo(12, "Common problems", "What to do when something does not go as expected.")
    for titulo, texto in (
        ("The device shows as “not authorized”",
         "Unlock the screen and accept <b>Allow USB debugging</b>. If the question does not "
         "appear, turn USB debugging off and on, or revoke the authorizations in the Developer "
         "options and connect again."),
        ("No device responds",
         "Change the cable (it may be charge-only), set the USB mode to “File transfer” and "
         "check that USB debugging is on."),
        ("The device refused the agent app",
         "See whether there is a confirmation on the device's screen (Play Protect). On Xiaomi, "
         "turn on “Install via USB”."),
        ("The console warns that the device's clock is shifted",
         "The device was showing a different date and time (common on a device with no SIM or "
         "no internet). Do not correct the clock: the measured offset is recorded, and the "
         "Extraction Report and the expert report warn that the dates recorded by the device "
         "should be read with that correction."),
        ("Windows showed “Windows protected your PC”",
         "It is the warning for a program with no paid digital signature. Check the installer's "
         "hash, click <b>More info</b> and <b>Run anyway</b> (chapter 2). If there is no "
         "button, Smart App Control is on and requires a digital signature: install on another "
         "computer, ask your IT department to allow the program, or run from source "
         "(chapter 2)."),
        ("The tool does not find the iPhone",
         "Check that the Apple Devices app (or iTunes) is installed, <b>disconnect and connect "
         "the cable again</b>, unlock the screen and tap <b>Trust</b>."),
        ("The iPhone refused the backup (code 212)",
         "The device's initial setup was not completed. Finish it — the Apple account can be "
         "skipped — and try again (chapter 6)."),
        ("The iPhone backup stopped halfway",
         "The screen locked or the cable moved. Keep the iPhone unlocked (watch out for Low "
         "Power Mode) and type the code whenever it asks."),
        ("The conversation list came up empty",
         "Check, in the window title, that the acquisition is the right one. If it is, the "
         "Content Report says why there is no interpreted conversation."),
        ("The report says “the provider responded and returned no record”",
         "Android itself answered the query that the source is empty — for example, SMS on a "
         "device with no SIM. It is not a read failure. Deleted records do not appear by this "
         "route."),
        ("A file appears with “(nome alterado 1)” (name altered 1)",
         "Windows does not accept the name the file has on the device (two names that differ "
         "only in case, or a trailing dot). The content is the same, checked by the hash, and "
         "the correspondence is in the reconciliation report."),
        ("WhatsApp shows “On · Password”",
         "The backup is protected by a password, and the tool decrypts only with the 64-digit "
         "key. Turn off the protection and turn it on again with the key (chapter 5, steps 1 "
         "and 2)."),
        ("The recent WhatsApp messages do not appear",
         "The backup predates them. See the “Source note” in the report and make a new backup "
         "before extracting."),
        ("I forgot the password and the code",
         "Create a new profile. The old acquisitions stay under your name."),
    ):
        h += [sub(titulo), p(texto)]

    # =====================================================================
    h += capitulo(13, "Glossary", "Terms used in the tool and in this manual.")
    h += [tabela_simples(["Term", "Meaning"], [
        ["ADB", "Android Debug Bridge, Android's debugging tool."],
        ["Acquisition", "An extraction from a device, written to a sealed folder inside the "
         "case."],
        ["Case", "The set of acquisitions of a single examination."],
        ["Addendum", "Information added to the case later, without rewriting the acquisition."],
        ["Encrypted backup (iPhone)", "A local backup protected by a password; it is the only "
         "one in which iOS includes the call log."],
        ["crypt15", "The format of WhatsApp's encrypted backup."],
        ["EXIF", "Data the camera records inside the photo: date, camera and, sometimes, GPS."],
        ["GPS (UTC)", "The time of the satellites recorded with the coordinate; independent of "
         "the device's clock."],
        ["DEFR / DES", "First responder and specialist, in ISO/IEC 27037."],
        ["Hash (SHA-256)", "A file's fingerprint: any change alters the value."],
        ["Seal (manifest)", "The list of hashes of all the acquisition's files."],
        ["Express selection", "A module that alters the device and only runs if chosen one by "
         "one."],
        ["Caveat", "What the module did not reach, declared alongside what it obtained."],
    ], [0.25, 0.75])]
    return h


def main() -> None:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    documento = Apostila(SAIDA)
    documento.multiBuild(conteudo())
    print(f"Manual generated: {SAIDA}")


if __name__ == "__main__":
    main()
