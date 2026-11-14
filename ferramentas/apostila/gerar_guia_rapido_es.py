"""
Genera la Guía de Extracción Rápida del Hexis Forensics en español (dos
páginas, anverso y reverso).

Versión en español del guía de referencia rápida. El programa y los
documentos generados están en portugués; los nombres de los botones se
citan en portugués, como aparecen en la interfaz.

    py ferramentas/apostila/gerar_guia_rapido_es.py
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

SAIDA = AQUI / "saida" / "Guia_Extraccion_Rapida_Hexis_Forensics_ES.pdf"
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
    cab = Table([[Paragraph("Guía de Extracción Rápida", TITULO), logo]],
                colWidths=[LARGURA - 4.6 * cm, 4.6 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [cab, Paragraph(sub_titulo, SUB),
            Paragraph(f"Hexis Forensics {VERSAO} — Guía de Extracción Rápida — los detalles de "
                      "cada paso están en el Manual del Usuario", SUB), Spacer(1, 2)]


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
    # ---------------- PÁGINA 1 ----------------
    h += cabecalho("Página 1 — INSTALAR y ANDROID, con WhatsApp · reverso: iPhone y después de la extracción")
    h += caixa("<b>AVISO — TRATAMIENTO DE DATOS PERSONALES.</b> Extraer y examinar datos de un "
               "dispositivo es tratamiento de datos personales. Use la herramienta solo con base "
               "legal (orden judicial, requerimiento de autoridad competente o consentimiento "
               "documentado del titular) y conforme a las normas aplicables de su jurisdicción. "
               "Recolecte solo lo necesario y guárdelo con seguridad. La legalidad del examen es "
               "responsabilidad de quien lo ejecuta y de quien lo autoriza.", alerta=True)

    h += faixa("INSTALAR LA HERRAMIENTA — una vez por computadora", AZUL)
    h.append(etapa("A. Por el instalador (camino normal) (manual, cap. 2)"))
    h.append(passos([
        "Verifique el hash: en la carpeta del instalador, clic derecho en un espacio vacío → "
        "<b>Abrir en la Terminal</b> → escriba <b>Get-FileHash .\\HexisForensics-Setup-1.0.0.exe</b> "
        "y Enter. El valor debe ser idéntico al publicado. Distinto: no instale.",
        "Ejecute el instalador y marque <b>Criar atalho na Área de Trabalho</b> (crear acceso "
        "directo). Si aparece «Windows protegió su PC»: <b>Más información → Ejecutar de todas "
        "formas</b>.",
    ], reiniciar=True))
    h.append(etapa("B. Por el código fuente de GitHub — solo si Windows bloquea el instalador sin ofrecer el botón (Control Inteligente de Aplicaciones)"))
    h.append(passos([
        "Instale <b>Python 3.13</b> de python.org (<b>no</b> use la 3.14). En la primera pantalla "
        "del instalador de Python, marque <b>Add python.exe to PATH</b>.",
        "En <b>github.com/HexisForensics/HexisForensics/releases</b>, en la versión más reciente, "
        "descargue el <b>Fuente (ZIP)</b>. No use el «Code → Download ZIP» de la página principal.",
        "Verifique el hash: en la carpeta del archivo, Abrir en la Terminal → "
        "<b>Get-FileHash .\\HexisForensics-1.0.0-fonte.zip</b>. Debe ser idéntico al publicado en la Release.",
        "Extraiga la carpeta → ábrala → Abrir en la Terminal → escriba "
        "<b>py -m pip install -r requirements.txt</b> (tarda la primera vez) → luego <b>py main.py</b>. "
        "La herramienta abre en la pantalla de entrada.",
    ]))
    h += caixa("En ambos caminos, los casos quedan en <b>HexisForensics-Casos</b>, en su carpeta de "
               "usuario de Windows: actualizar la herramienta nunca alcanza las adquisiciones. En el "
               "primer inicio, cree su perfil de examinador y guarde el código de recuperación.")
    h += caixa("<b>Tenga a mano antes de empezar:</b> cable USB de datos (un cable solo de carga no "
               "sirve) · número del precinto (lacre) · el dispositivo para dos fotos (frente y dorso) · "
               "el documento de autorización escaneado · su perfil de examinador creado en la herramienta.")

    h += faixa("ANDROID")
    h.append(etapa("A. Preparar el dispositivo (manual, cap. 3)"))
    h.append(passos([
        "<b>Configuraciones → Acerca del teléfono</b> → toque 7 veces en <b>Número de la versión</b> "
        "(«Número de compilación») hasta que aparezca «Ahora eres desarrollador».",
        "<b>Opciones de desarrollador</b>: active <b>Depuración USB</b> y <b>Permanecer activo</b>.",
        "Conecte el cable → marque <b>Permitir siempre desde esta computadora</b> → <b>Permitir</b>.",
        "En la herramienta, página <b>Android → Verificar Conexão</b> (verificar conexión): el "
        "dispositivo debe aparecer conectado y autorizado.",
    ], reiniciar=True))
    h.append(etapa("B. WhatsApp: generar la copia con la CLAVE DE 64 DÍGITOS (cap. 5) — omita si no hay WhatsApp"))
    h.append(passos([
        "En el teléfono: WhatsApp → <b>Ajustes → Chats → Copia de seguridad → Copia cifrada de "
        "extremo a extremo</b>. Si está en <b>Activado · Contraseña</b> o <b>Clave de acceso</b>: "
        "<b>Desactivar</b> (pide la contraseña de la copia).",
        "Activar → <b>NO</b> toque el botón verde «Usar clave de acceso» → <b>Más opciones</b> → "
        "<b>Clave de cifrado de 64 dígitos</b> → <b>Generar</b>.",
        "Anote o fotografíe la clave (16 grupos de 4) → «Anoté mi clave» → <b>Crear</b>.",
        "Cuenta de Google: <b>Ninguna</b> → Copia automática: <b>Desactivada</b> → <b>Hacer copia</b>. "
        "Verifique la línea <b>Local:</b> con la hora de ahora.",
    ]))
    h.append(etapa("C. Extraer (cap. 4)"))
    h.append(passos([
        "Verifique los módulos: los comunes ya vienen marcados (WhatsApp — Mídia e Backups entre "
        "ellos). Los que alteran el dispositivo comienzan sin marcar: márquelos solo si los necesita.",
        "<b>Iniciar Extração</b> (iniciar extracción) → confirme el examinador → lea <b>Método e "
        "limitações</b> → <b>Ciente — Prosseguir</b>.",
        "Caso: nuevo o existente (un caso reúne varios dispositivos) → Autorización: adjunte el "
        "documento → Dispositivo: marca, modelo, precinto y las dos fotos.",
        "Espere hasta el mensaje de extracción finalizada. No cierre la herramienta en el medio: la "
        "adquisición quedaría sin precinto. Para detener, use <b>Cancelar</b>.",
    ]))
    h.append(etapa("D. Descifrar el WhatsApp (cap. 5)"))
    h.append(passos([
        "<b>Casos e Documentos</b> → caso → adquisición → <b>Decifrar backup</b> → escriba o pegue "
        "la clave de 64 dígitos → <b>Decifrar</b>. Luego, siga el reverso («Después de la extracción»).",
    ]))
    h += caixa("<b>ATENCIÓN.</b> Activar la depuración USB, tocar la protección de la copia de WhatsApp "
               "y mandar hacer la copia son alteraciones en el dispositivo, impuestas por el método: la "
               "herramienta lo registra, y la clave queda en el complemento del caso. Haga la copia el "
               "día del examen: una copia antigua o hecha con contraseña no abre con la clave nueva y no "
               "trae los mensajes recientes.", alerta=True)

    # ---------------- PÁGINA 2 ----------------
    h.append(PageBreak())
    h += cabecalho("Página 2 — iPHONE y DESPUÉS DE LA EXTRACCIÓN (Android y iPhone)")
    h += faixa("iPHONE — el WhatsApp viene dentro de la copia del iPhone", AZUL)
    h.append(etapa("A. Preparar (cap. 6)"))
    h.append(passos([
        "En la computadora: app <b>Dispositivos Apple</b> (Microsoft Store) o iTunes instalado. No "
        "lo abra ni sincronice. Si el iPhone ya estaba en el cable, desconecte y conecte de nuevo.",
        "iPhone con la configuración inicial concluida (la cuenta Apple puede saltarse), "
        "desbloqueado → <b>Confiar</b> → código de desbloqueo.",
        "Página <b>iPhone → Verificar Conexão</b>.",
    ], reiniciar=True))
    h.append(etapa("B. Elegir la copia y extraer"))
    h += tabla(["", "Copia común", "Copia cifrada (contraseña temporal)"], [
        ["Trae", "Mensajes, agenda, WhatsApp, fotos y su GPS",
         "Todo lo de la común (menos las fotos) + registro de llamadas"],
        ["¿Altera el dispositivo?", "No (solo el emparejamiento)",
         "Sí: define y retira una contraseña de copia, con registro"],
        ["Código en el iPhone", "Una vez", "Hasta tres veces: quédese con el dispositivo a mano"],
    ], [0.22, 0.34, 0.44])
    h.append(passos([
        "Marque una o las dos → <b>Iniciar Extração</b> → las mismas pantallas de Android (método, "
        "caso, autorización, precinto y fotos). Mantenga el iPhone desbloqueado durante la copia "
        "(cuidado con el Modo de Bajo Consumo).",
        "¿Hizo la cifrada? <b>Casos e Documentos</b> → adquisición → <b>Decifrar backup</b>: la "
        "contraseña ya viene rellenada → <b>Decifrar</b>.",
    ]))

    h += faixa("DESPUÉS DE LA EXTRACCIÓN — en Casos e Documentos → caso → adquisición", VERDE)
    h += tabla(["Documento / acción", "Qué es"], [
        ["Relatório de Conteúdo (Informe de Contenido)",
         "Mensajes, WhatsApp, llamadas, contactos y ubicaciones de las fotos, con el origen de cada línea (CSV + PDF)."],
        ["PDF de conversas selecionadas",
         "Clic en las conversaciones relevantes → Gerar PDF das selecionadas. Verifique en el título de la ventana que la adquisición sea la correcta."],
        ["Relatório de Extração (Informe de Extracción)",
         "El procedimiento: pieza, fotos, método, desenlace de cada módulo y hashes."],
        ["Laudo Pericial (Informe Pericial)",
         "El documento final, a nombre del examinador de la sesión."],
        ["Conferir Integridade (Verificar Integridad)",
         "Recalcula el hash de cada archivo y lo compara con el precinto. Hágalo antes de entregar."],
        ["Exportar para entrega",
         "Reúne los documentos para entrega, fuera de la adquisición sellada."],
    ], [0.34, 0.66])
    h += caixa("El programa y los documentos generados están en <b>portugués</b>. Esta guía explica "
               "cómo operarlo; los nombres de los botones aparecen en portugués, como en la interfaz.")
    return h


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            title="Guía de Extracción Rápida — Hexis Forensics")
    doc.build(contenido())
    print("Guía (ES) generada:", SAIDA)


if __name__ == "__main__":
    main()
