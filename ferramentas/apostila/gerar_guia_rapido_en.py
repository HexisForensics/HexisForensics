"""
Generates the Hexis Forensics Quick Extraction Guide in English (two pages,
front and back).

English version of the quick-reference guide. The program and the documents it
generates are in Portuguese; the names of the buttons are quoted in Portuguese,
as they appear in the interface.

    py ferramentas/apostila/gerar_guia_rapido_en.py
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

SAIDA = AQUI / "saida" / "Quick_Extraction_Guide_Hexis_Forensics_EN.pdf"
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
CORPO = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=10.1)
NUMERO = ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=8.5, textColor=AZUL,
                        leading=10.8, alignment=1)
CAIXA = ParagraphStyle("x", parent=CORPO, fontSize=8.1, leading=9.8)
CELDA = ParagraphStyle("cel", fontName="Helvetica", fontSize=8, leading=10)
CELDA_B = ParagraphStyle("celb", fontName="Helvetica-Bold", fontSize=8, leading=10)

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
                           ("TOPPADDING", (0, 0), (-1, -1), 0.9),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9),
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


def cabecalho(sub_titulo):
    logo = Image(str(LOGO), width=4.4 * cm, height=1.18 * cm) if LOGO.is_file() else Spacer(1, 1)
    cab = Table([[Paragraph("Quick Extraction Guide", TITULO), logo]],
                colWidths=[LARGURA - 4.6 * cm, 4.6 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [cab, Paragraph(sub_titulo, SUB),
            Paragraph(f"Hexis Forensics {VERSAO} — Quick Extraction Guide — the details of each "
                      "step are in the User Manual", SUB), Spacer(1, 2)]


def tabla(cabecera, filas, anchos):
    datos = [[Paragraph(c, CELDA_B) for c in cabecera]]
    datos += [[Paragraph(c, CELDA) for c in fila] for fila in filas]
    t = Table(datos, colWidths=[LARGURA * a for a in anchos])
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1fb")),
              ("GRID", (0, 0), (-1, -1), 0.25, LINHA),
              ("TOPPADDING", (0, 0), (-1, -1), 2.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
              ("LEFTPADDING", (0, 0), (-1, -1), 4)]
    t.setStyle(TableStyle(estilo))
    return [Spacer(1, 3), t]


def contenido():
    h = []
    # ---------------- PAGE 1 ----------------
    h += cabecalho("Page 1 — INSTALL and ANDROID, with WhatsApp · back: iPhone and after the extraction")
    h += caixa("<b>NOTICE — PERSONAL DATA PROCESSING.</b> Extracting and examining data from a "
               "device is personal data processing. Use the tool only with a legal basis (a "
               "court order, a request from a competent authority, or the documented consent of "
               "the data subject) and in accordance with the rules applicable in your "
               "jurisdiction. Collect only what is necessary and store it securely. The "
               "lawfulness of the examination is the responsibility of whoever performs it and "
               "whoever authorizes it.", alerta=True)

    h += faixa("INSTALL THE TOOL — once per computer", AZUL)
    h.append(etapa("A. Via the installer (the normal route) (manual, ch. 2)"))
    h.append(passos([
        "Verify the hash: in the installer's folder, right-click an empty space → <b>Open in "
        "Terminal</b> → type <b>Get-FileHash .\\HexisForensics-Setup-1.0.0.exe</b> and Enter. The "
        "value must be identical to the published one. Different: do not install.",
        "Run the installer and check <b>Criar atalho na Área de Trabalho</b> (create a "
        "shortcut). If “Windows protected your PC” appears: <b>More info → Run anyway</b>.",
    ], reiniciar=True))
    h.append(etapa("B. From the GitHub source — only if Windows blocks the installer without offering the button (Smart App Control)"))
    h.append(passos([
        "Install <b>Python 3.13</b> from python.org (<b>do not</b> use 3.14). On the first "
        "screen of the Python installer, check <b>Add python.exe to PATH</b>.",
        "At <b>github.com/HexisForensics/HexisForensics/releases</b>, on the most recent "
        "version, download <b>Fonte (ZIP)</b> (the source ZIP). Do not use “Code → Download "
        "ZIP” from the main page.",
        "Verify the hash: in the file's folder, Open in Terminal → "
        "<b>Get-FileHash .\\HexisForensics-1.0.0-fonte.zip</b>. It must be identical to the one "
        "published in the Release.",
        "Extract the folder → open it → Open in Terminal → type "
        "<b>py -m pip install -r requirements.txt</b> (it takes a while the first time) → then "
        "<b>py main.py</b>. The tool opens on the entry screen.",
    ]))
    h += caixa("On both routes, cases are kept in <b>HexisForensics-Casos</b>, in your Windows "
               "user folder: updating the tool never reaches the acquisitions. On the first run, "
               "create your examiner profile and save the recovery code.")
    h += caixa("<b>Have at hand before you start:</b> a USB data cable (a charge-only cable will "
               "not work) · the seal number · the device for two photos (front and back) · the "
               "scanned authorization document · your examiner profile created in the tool.")

    h += faixa("ANDROID")
    h.append(etapa("A. Prepare the device (manual, ch. 3)"))
    h.append(passos([
        "<b>Settings → About phone</b> → tap 7 times on <b>Build number</b> until “You are now "
        "a developer” appears.",
        "<b>Developer options</b>: turn on <b>USB debugging</b> and <b>Stay awake</b>.",
        "Connect the cable → check <b>Always allow from this computer</b> → <b>Allow</b>.",
        "In the tool, page <b>Android → Verificar Conexão</b> (check connection): the device "
        "must show as connected and authorized.",
    ], reiniciar=True))
    h.append(etapa("B. WhatsApp: make the backup with the 64-DIGIT KEY (ch. 5) — skip if there is no WhatsApp"))
    h.append(passos([
        "On the phone: WhatsApp → <b>Settings → Chats → Chat backup → End-to-end encrypted "
        "backup</b>. If it is <b>On · Password</b> or <b>Passkey</b>: <b>Turn off</b> (it asks "
        "for the backup password).",
        "Turn on → <b>DO NOT</b> tap the green “Use passkey” button → <b>More options</b> → "
        "<b>64-digit encryption key</b> → <b>Generate</b>.",
        "Write down or photograph the key (16 groups of 4) → “I saved my key” → <b>Create</b>.",
        "Google Account: <b>None</b> → Back up automatically: <b>Off</b> → <b>Back up</b>. "
        "Check the <b>Local:</b> line with the current time.",
    ]))
    h.append(etapa("C. Extract (ch. 4)"))
    h.append(passos([
        "Check the modules: the common ones come already checked (WhatsApp — Mídia e Backups "
        "among them). Those that alter the device start unchecked: check them only if you need "
        "them.",
        "<b>Iniciar Extração</b> (start extraction) → confirm the examiner → read <b>Método e "
        "limitações</b> → <b>Ciente — Prosseguir</b>.",
        "Case: new or existing (a case gathers several devices) → Authorization: attach the "
        "document → Device: make, model, seal and the two photos.",
        "Wait for the extraction-finished message. Do not close the tool in the middle: the "
        "acquisition would be left without a seal. To stop, use <b>Cancelar</b>.",
    ]))
    h.append(etapa("D. Decrypt WhatsApp (ch. 5)"))
    h.append(passos([
        "<b>Casos e Documentos</b> → case → acquisition → <b>Decifrar backup</b> → type or "
        "paste the 64-digit key → <b>Decifrar</b>. Then follow the back (“After the "
        "extraction”).",
    ]))
    h += caixa("<b>WARNING.</b> Turning on USB debugging, touching the WhatsApp backup's "
               "protection and ordering the backup are changes to the device, imposed by the "
               "method: the tool records them, and the key is kept in the case addendum. Make "
               "the backup on the day of the examination: an old backup, or one made with a "
               "password, does not open with the new key and does not bring the recent "
               "messages.", alerta=True)

    # ---------------- PAGE 2 ----------------
    h.append(PageBreak())
    h += cabecalho("Page 2 — iPHONE and AFTER THE EXTRACTION (Android and iPhone)")
    h += faixa("iPHONE — WhatsApp comes inside the iPhone backup", AZUL)
    h.append(etapa("A. Prepare (ch. 6)"))
    h.append(passos([
        "On the computer: the <b>Apple Devices</b> app (Microsoft Store) or iTunes installed. "
        "Do not open it or sync. If the iPhone was already on the cable, disconnect and connect "
        "again.",
        "iPhone with the initial setup completed (the Apple account can be skipped), unlocked → "
        "<b>Trust</b> → unlock code.",
        "Page <b>iPhone → Verificar Conexão</b>.",
    ], reiniciar=True))
    h.append(etapa("B. Choose the backup and extract"))
    h += tabla(["", "Common backup", "Encrypted backup (temporary password)"], [
        ["Brings", "Messages, address book, WhatsApp, photos and their GPS",
         "Everything the common one has (minus the photos) + the call log"],
        ["Alters the device?", "No (only the pairing)",
         "Yes: sets and removes a backup password, with a record"],
        ["Code on the iPhone", "Once", "Up to three times: keep the device at hand"],
    ], [0.22, 0.34, 0.44])
    h.append(passos([
        "Check one or both → <b>Iniciar Extração</b> → the same Android screens (method, case, "
        "authorization, seal and photos). Keep the iPhone unlocked during the backup (watch out "
        "for Low Power Mode).",
        "Did you make the encrypted one? <b>Casos e Documentos</b> → acquisition → <b>Decifrar "
        "backup</b>: the password comes already filled in → <b>Decifrar</b>.",
    ]))

    h += faixa("AFTER THE EXTRACTION — in Casos e Documentos → case → acquisition", VERDE)
    h += tabla(["Document / action", "What it is"], [
        ["Relatório de Conteúdo (Content Report)",
         "Messages, WhatsApp, calls, contacts and photo locations, with the origin of each line (CSV + PDF)."],
        ["PDF de conversas selecionadas",
         "Click the relevant conversations → Gerar PDF das selecionadas. Check in the window title that the acquisition is the right one."],
        ["Relatório de Extração (Extraction Report)",
         "The procedure: item, photos, method, outcome of each module and hashes."],
        ["Laudo Pericial (Expert Report)",
         "The final document, under the name of the session's examiner."],
        ["Conferir Integridade (Check Integrity)",
         "Recomputes the hash of each file and compares it with the seal. Do it before delivering."],
        ["Exportar para entrega (Export for delivery)",
         "Gathers the documents for delivery, outside the sealed acquisition."],
    ], [0.34, 0.66])
    h += caixa("The program and the documents it generates are in <b>Portuguese</b>. This guide "
               "explains how to operate it; the names of the buttons appear in Portuguese, as in "
               "the interface.")
    return h


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            title="Quick Extraction Guide — Hexis Forensics")
    doc.build(contenido())
    print("Guide (EN) generated:", SAIDA)


if __name__ == "__main__":
    main()
