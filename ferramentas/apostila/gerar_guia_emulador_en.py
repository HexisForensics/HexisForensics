"""
Generates the Hexis Forensics Emulator Practice Guide in English (two pages).

For anyone who wants to practice the tool's workflow without a real device and
with no risk to a case: set up an Android emulator, populate test data, extract
and read the result. The emulator is a practice bench, never proof of a real
case. The program and the documents it generates are in Portuguese; the names
of the buttons are quoted in Portuguese, as they appear in the interface.

    py ferramentas/apostila/gerar_guia_emulador_en.py
"""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ))
from core.versao import VERSAO  # noqa: E402

SAIDA = AQUI / "saida" / "Practice_Guide_Emulator_Hexis_Forensics_EN.pdf"
LOGO = RAIZ / "assets" / "marca" / "logo_claro.png"

AZUL = colors.HexColor("#1f6feb")
ESCURO = colors.HexColor("#0f1b2d")
VERDE = colors.HexColor("#138a76")
VERMELHO = colors.HexColor("#c62828")
FUNDO_ALERTA = colors.HexColor("#fdecea")
FUNDO_DICA = colors.HexColor("#e8f1fe")
LINHA = colors.HexColor("#dddddd")

TITULO = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, textColor=ESCURO, leading=19)
SUB = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, textColor=colors.grey, leading=11)
FAIXA = ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.white,
                       leading=13)
ETAPA = ParagraphStyle("e", fontName="Helvetica-Bold", fontSize=9.2, textColor=ESCURO,
                       leading=11.4, spaceBefore=3, spaceAfter=0.5)
CORPO = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=10.3)
NUMERO = ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=8.5, textColor=AZUL,
                        leading=10.8, alignment=1)
CAIXA = ParagraphStyle("x", parent=CORPO, fontSize=8.1, leading=9.9)
CELA = ParagraphStyle("cel", fontName="Helvetica", fontSize=8, leading=10)
CELA_B = ParagraphStyle("celb", fontName="Helvetica-Bold", fontSize=8, leading=10)

LARGURA = A4[0] - 2.4 * cm
CONTADOR = {"n": 0}


def faixa(texto, cor=ESCURO):
    t = Table([[Paragraph(texto, FAIXA)]], colWidths=[LARGURA])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cor),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return [Spacer(1, 3), t, Spacer(1, 2)]


def etapa(texto):
    return Paragraph(texto, ETAPA)


def passos(lista, reiniciar=False):
    if reiniciar:
        CONTADOR["n"] = 0
    linhas = []
    for texto in lista:
        CONTADOR["n"] += 1
        linhas.append([Paragraph(str(CONTADOR["n"]), NUMERO), Paragraph(texto, CORPO)])
    t = Table(linhas, colWidths=[0.8 * cm, LARGURA - 0.8 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINHA)]))
    return t


def caixa(texto, alerta=False):
    fundo, borda = (FUNDO_ALERTA, VERMELHO) if alerta else (FUNDO_DICA, AZUL)
    t = Table([[Paragraph(texto, CAIXA)]], colWidths=[LARGURA])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fundo),
                           ("LINEBEFORE", (0, 0), (0, -1), 2.5, borda),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return [Spacer(1, 3), t]


def tabela(header, rows, widths):
    dados = [[Paragraph(c, CELA_B) for c in header]]
    dados += [[Paragraph(c, CELA) for c in row] for row in rows]
    t = Table(dados, colWidths=[LARGURA * a for a in widths])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1fb")),
                           ("GRID", (0, 0), (-1, -1), 0.25, LINHA),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    return [Spacer(1, 3), t]


def cabecalho(sub_titulo):
    logo = Image(str(LOGO), width=4.2 * cm, height=4.2 * cm * 256 / 740) if LOGO.is_file() \
        else Spacer(1, 1)
    cab = Table([[Paragraph("Emulator Practice Guide", TITULO), logo]],
                colWidths=[LARGURA - 4.4 * cm, 4.4 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [cab, Paragraph(sub_titulo, SUB),
            Paragraph(f"Hexis Forensics {VERSAO} — Emulator Practice Guide — the real-examination "
                      "step-by-step is in the User Manual", SUB), Spacer(1, 2)]


def content():
    h = []
    # ---------------- PAGE 1 ----------------
    h += cabecalho("Page 1 · SET UP THE EMULATOR (practice bench) · back: extract and read the "
                   "result")
    h += caixa("<b>PRACTICE ONLY.</b> The emulator is for learning to operate Hexis Forensics "
               "without a real device and with no risk to a case. It <b>is not a real device</b>: "
               "it has no real IMEI or baseband, the data partition is different, and it comes "
               "with <b>elevated privilege (root)</b>, which a common phone does not have. For "
               "that reason, <b>never</b> use the emulator to claim that an extraction will work "
               "on a real phone, nor as a basis for an expert report. It is a lab, not proof.",
               alerta=True)

    h += faixa("1. INSTALL ANDROID STUDIO AND CREATE THE EMULATOR", AZUL)
    h.append(etapa("A. Android Studio and the right image"))
    h.append(passos([
        "Download and install <b>Android Studio</b> (developer.android.com/studio). It is free "
        "and runs on Windows. Accept the standard components during installation.",
        "Open the <b>Device Manager</b> (phone icon on the right) > <b>Create device</b> > pick a "
        "<b>Pixel</b> > <b>Next</b>.",
        "<b>System Image:</b> pick <b>Android 13 (API 33)</b> in a version <b>without Google "
        "Play</b> — the label should read “Google APIs” or “AOSP”, <b>not</b> “Google Play”. The "
        "Google Play image <b>blocks root</b> and is less useful for practice. Download the image.",
        "<b>Finish</b> to create the emulator. Give it a name that signals practice, e.g. "
        "<b>Practice-Bench</b>.",
    ], reiniciar=True))

    h.append(etapa("B. Start it and confirm elevated privilege (root)"))
    h.append(passos([
        "In the Device Manager, click <b>Play</b> to start the emulator and wait for the Android "
        "home screen to open.",
        "On the computer, open the Terminal in the <b>adb</b> folder (or with adb on the PATH) "
        "and type <b>adb devices</b>: it should list something like <b>emulator-5554 device</b>. "
        "The emulator comes authorized — there is no cable and no RSA fingerprint.",
        "Type <b>adb root</b>: it should answer “restarting adbd as root”. That privilege — which "
        "a common phone does not have — is what lets the emulator run the modules that require "
        "root.",
    ]))

    h += faixa("2. POPULATE TEST DATA")
    h.append(etapa("C. Contacts, SMS and WhatsApp"))
    h.append(passos([
        "<b>Contacts:</b> open the emulator's Contacts app and create a few, with name and number.",
        "<b>SMS:</b> on the emulator's side bar, <b>Extended controls</b> (the three-dots button "
        "“...”) > <b>Phone</b> > type a number and a message > <b>Send message</b>: a test SMS "
        "arrives on the emulator.",
        "<b>WhatsApp:</b> download the <b>APK from the website</b> (whatsapp.com/android — there "
        "is no Play Store on the emulator) and <b>drag the .apk file onto the emulator window</b> "
        "to install. Set it up with a number whose SMS you can receive and exchange a few "
        "messages to have content.",
    ]))
    h += caixa("<b>Gmail does not run</b> on the emulator without Google Play — this is expected, "
               "not a defect. Practice here covers contacts, SMS, media and WhatsApp, which is "
               "what the tool extracts on Android.")

    # ---------------- PAGE 2 ----------------
    h.append(PageBreak())
    h += cabecalho("Page 2 · EXTRACT AND READ THE RESULT")

    h += faixa("3. EXTRACT WITH HEXIS", AZUL)
    h.append(etapa("D. Connect and open a practice case  "
                   "<font color='grey' size='7.5'>(manual, ch. 3–4)</font>"))
    h.append(passos([
        "With the emulator open, in the tool: <b>Android</b> page > <b>Verificar Conexão</b> "
        "(check connection). The emulator shows up connected and authorized, with no cable.",
        "<b>Iniciar Extração</b> (start extraction) > confirm the examiner > read <b>Método e "
        "limitações</b> > <b>Ciente — Prosseguir</b>.",
        "<b>Case:</b> create a new case and make <b>practice</b> explicit in the name (e.g. "
        "PRACTICE-001). <b>Never mix it with a real case.</b> Fill device, seal and the photos "
        "with fictitious data.",
    ], reiniciar=True))

    h.append(etapa("E. Select the modules and extract"))
    h.append(passos([
        "The common modules are already ticked. Since the emulator has <b>elevated privilege</b>, "
        "you may also tick the <b>express-selection</b> ones (those that alter the device / "
        "require root) to see how the tool runs and records them.",
        "To practice WhatsApp, follow the <b>64-digit key</b> as in the Quick Extraction Guide "
        "(Android, step B).",
        "<b>Iniciar</b> (start) and wait for the extraction-finished message. Do not close the "
        "tool midway: the acquisition would be left without a seal.",
    ]))

    h += faixa("4. READ THE RESULT · Casos e Documentos > case > acquisition", VERDE)
    h += tabela(["Document / action", "What it is"], [
        ["Relatório de Extração (Extraction Report)",
         "The procedure: method, outcome of each module and hashes."],
        ["Relatório de Conteúdo (Content Report)",
         "Messages, WhatsApp, contacts and photo locations, with the origin of each line "
         "(CSV + PDF)."],
        ["Decifrar backup (Decrypt backup)", "Handle WhatsApp with the 64-digit key you generated."],
        ["Conferir Integridade (Check Integrity)",
         "Recomputes the hash of each file and compares it with the seal — practice this step too."],
    ], [0.34, 0.66])

    h += faixa("HOW TO READ EACH MODULE'S RESULT")
    h += tabela(["Result", "What it means"], [
        ["Concluído (Completed)", "Obtained what it set out to."],
        ["Concluído com ressalva (Completed with caveat)",
         "Obtained part and declared what it did not reach."],
        ["Não obteve dado (No data obtained)",
         "Nothing was acquired. It does <b>not</b> mean the data does not exist on the device."],
    ], [0.34, 0.66])

    h += caixa("<b>WHAT THE EMULATOR DOES NOT TEACH.</b> Because it has root, the emulator shows "
               "extractions that <b>would not happen on a common phone without root</b>. Do not "
               "conclude that “it worked on the emulator” means “it works on device X”. The "
               "emulator trains the <b>operator</b> and the <b>workflow</b>; proof that a method "
               "works on a real model only comes from testing the real model.", alerta=True)
    h += caixa("<b>Golden rule:</b> what was not obtained is not what does not exist. The tool "
               "never asserts what it did not verify — and neither should you, while practicing.")
    return h


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            title="Emulator Practice Guide — Hexis Forensics")
    doc.build(content())
    print("Emulator guide (EN) generated:", SAIDA)


if __name__ == "__main__":
    main()
