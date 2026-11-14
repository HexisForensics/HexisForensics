"""
Genera la Guía de Práctica con Emulador del Hexis Forensics en español (dos
páginas).

Para quien quiere practicar el flujo de la herramienta sin dispositivo real y
sin riesgo a un caso: montar un emulador Android, poblar datos de prueba,
extraer y leer el resultado. El emulador es banco de práctica, nunca prueba de
un caso real. El programa y los documentos generados están en portugués; los
nombres de los botones se citan en portugués, como aparecen en la interfaz.

    py ferramentas/apostila/gerar_guia_emulador_es.py
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

SAIDA = AQUI / "saida" / "Guia_Practica_Emulador_Hexis_Forensics_ES.pdf"
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


def tabela(cabecera, filas, larguras):
    dados = [[Paragraph(c, CELA_B) for c in cabecera]]
    dados += [[Paragraph(c, CELA) for c in fila] for fila in filas]
    t = Table(dados, colWidths=[LARGURA * a for a in larguras])
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
    cab = Table([[Paragraph("Guía de Práctica con Emulador", TITULO), logo]],
                colWidths=[LARGURA - 4.4 * cm, 4.4 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [cab, Paragraph(sub_titulo, SUB),
            Paragraph(f"Hexis Forensics {VERSAO} — Guía de Práctica con Emulador — el paso a paso "
                      "del examen real está en el Manual del Usuario", SUB), Spacer(1, 2)]


def contenido():
    h = []
    # ---------------- PÁGINA 1 ----------------
    h += cabecalho("Página 1 · MONTAR EL EMULADOR (banco de práctica) · reverso: extraer y leer "
                   "el resultado")
    h += caixa("<b>SOLO PARA PRÁCTICA.</b> El emulador sirve para aprender a operar el Hexis "
               "Forensics sin dispositivo real y sin riesgo a un caso. <b>No es un dispositivo de "
               "verdad</b>: no tiene IMEI ni banda base reales, la partición de datos es distinta "
               "y ya viene con <b>privilegio elevado (root)</b>, que un teléfono común no tiene. "
               "Por eso, <b>nunca</b> use el emulador para afirmar que una extracción funcionará "
               "en un teléfono real, ni como base de informe pericial. Es laboratorio, no prueba.",
               alerta=True)

    h += faixa("1. INSTALAR ANDROID STUDIO Y CREAR EL EMULADOR", AZUL)
    h.append(etapa("A. Android Studio y la imagen correcta"))
    h.append(passos([
        "Descargue e instale <b>Android Studio</b> (developer.android.com/studio). Es gratuito y "
        "corre en Windows. Acepte los componentes estándar en la instalación.",
        "Abra el <b>Device Manager</b> (icono de teléfono a la derecha) > <b>Create device</b> > "
        "elija un <b>Pixel</b> > <b>Next</b>.",
        "<b>System Image:</b> elija <b>Android 13 (API 33)</b> en una versión <b>sin Google "
        "Play</b> — la etiqueta debe ser “Google APIs” o “AOSP”, <b>no</b> “Google Play”. La "
        "imagen con Google Play <b>bloquea el root</b> y sirve menos para la práctica. Descargue "
        "la imagen.",
        "<b>Finish</b> para crear el emulador. Déle un nombre que recuerde la práctica, p. ej. "
        "<b>Banco-Practica</b>.",
    ], reiniciar=True))

    h.append(etapa("B. Encender y verificar el privilegio elevado (root)"))
    h.append(passos([
        "En el Device Manager, pulse <b>Play</b> para iniciar el emulador y espere a que abra la "
        "pantalla inicial de Android.",
        "En la computadora, abra la Terminal en la carpeta del <b>adb</b> (o con el adb en el "
        "PATH) y escriba <b>adb devices</b>: debe listar algo como <b>emulator-5554 device</b>. "
        "El emulador ya viene autorizado — no hay cable ni huella RSA.",
        "Escriba <b>adb root</b>: debe responder “restarting adbd as root”. Ese privilegio — que "
        "el teléfono común no tiene — es el que deja al emulador correr los módulos que exigen "
        "root.",
    ]))

    h += faixa("2. POBLAR DATOS DE PRUEBA")
    h.append(etapa("C. Contactos, SMS y WhatsApp"))
    h.append(passos([
        "<b>Contactos:</b> abra la app Contactos del emulador y cree algunos, con nombre y número.",
        "<b>SMS:</b> en la barra lateral del emulador, <b>Extended controls</b> (el botón de tres "
        "puntos “...”) > <b>Phone</b> > escriba un número y un mensaje > <b>Send message</b>: "
        "llega un SMS de prueba al emulador.",
        "<b>WhatsApp:</b> descargue el <b>APK del sitio</b> (whatsapp.com/android — en el "
        "emulador no hay Play Store) y <b>arrastre el archivo .apk a la ventana del emulador</b> "
        "para instalar. Configúrelo con un número cuyo SMS pueda recibir e intercambie algunos "
        "mensajes para tener contenido.",
    ]))
    h += caixa("<b>Gmail no corre</b> en el emulador sin Google Play — es esperado, no es un "
               "defecto. La práctica aquí cubre contactos, SMS, medios y WhatsApp, que es lo que "
               "la herramienta extrae en Android.")

    # ---------------- PÁGINA 2 ----------------
    h.append(PageBreak())
    h += cabecalho("Página 2 · EXTRAER Y LEER EL RESULTADO")

    h += faixa("3. EXTRAER CON EL HEXIS", AZUL)
    h.append(etapa("D. Conectar y abrir un caso de práctica  "
                   "<font color='grey' size='7.5'>(manual, cap. 3–4)</font>"))
    h.append(passos([
        "Con el emulador abierto, en la herramienta: página <b>Android</b> > <b>Verificar "
        "Conexão</b> (verificar conexión). El emulador aparece conectado y autorizado, sin cable.",
        "<b>Iniciar Extração</b> (iniciar extracción) > confirme el examinador > lea <b>Método e "
        "limitações</b> > <b>Ciente — Prosseguir</b>.",
        "<b>Caso:</b> cree un caso nuevo y deje <b>práctica</b> explícito en el nombre (p. ej. "
        "PRACTICA-001). <b>Nunca lo mezcle con un caso real.</b> Complete dispositivo, precinto y "
        "las fotos con datos ficticios.",
    ], reiniciar=True))

    h.append(etapa("E. Marcar los módulos y extraer"))
    h.append(passos([
        "Los módulos comunes ya vienen marcados. Como el emulador tiene <b>privilegio "
        "elevado</b>, puede marcar también los de <b>selección expresa</b> (los que alteran el "
        "dispositivo / exigen root) para ver cómo la herramienta los conduce y registra.",
        "Para practicar el WhatsApp, siga la <b>clave de 64 dígitos</b> como en la Guía de "
        "Extracción Rápida (etapa B de Android).",
        "<b>Iniciar</b> y espere el mensaje de extracción finalizada. No cierre la herramienta en "
        "el medio: la adquisición quedaría sin precinto.",
    ]))

    h += faixa("4. LEER EL RESULTADO · Casos e Documentos > caso > adquisición", VERDE)
    h += tabela(["Documento / acción", "Qué es"], [
        ["Relatório de Extração (Informe de Extracción)",
         "El procedimiento: método, desenlace de cada módulo y hashes."],
        ["Relatório de Conteúdo (Informe de Contenido)",
         "Mensajes, WhatsApp, contactos y ubicaciones de las fotos, con el origen de cada línea "
         "(CSV + PDF)."],
        ["Decifrar backup", "Trate el WhatsApp con la clave de 64 dígitos que generó."],
        ["Conferir Integridade (Verificar Integridad)",
         "Recalcula el hash de cada archivo y lo compara con el precinto — practique también este "
         "paso."],
    ], [0.34, 0.66])

    h += faixa("CÓMO LEER EL RESULTADO DE CADA MÓDULO")
    h += tabela(["Resultado", "Qué significa"], [
        ["Concluído (Concluido)", "Obtuvo lo que se proponía."],
        ["Concluído com ressalva (Concluido con salvedad)",
         "Obtuvo parte y declaró lo que no alcanzó."],
        ["Não obteve dado (No obtuvo dato)",
         "Nada fue adquirido. <b>No</b> significa que el dato no exista en el dispositivo."],
    ], [0.34, 0.66])

    h += caixa("<b>LO QUE EL EMULADOR NO ENSEÑA.</b> Por tener root, el emulador muestra "
               "extracciones que en un <b>teléfono común sin root no ocurrirían</b>. No concluya "
               "que “funcionó en el emulador” significa “funciona en el equipo X”. El emulador "
               "entrena al <b>operador</b> y al <b>flujo</b>; la prueba de que un método funciona "
               "en un modelo real solo viene probando el modelo real.", alerta=True)
    h += caixa("<b>Regla de oro:</b> lo que no se obtuvo no es lo que no existe. La herramienta "
               "nunca afirma lo que no verificó — y usted, practicando, tampoco.")
    return h


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            title="Guía de Práctica con Emulador — Hexis Forensics")
    doc.build(contenido())
    print("Guía del emulador (ES) generada:", SAIDA)


if __name__ == "__main__":
    main()
