"""
Genera el Manual del Usuario del Hexis Forensics, en PDF, en español.

Es la versión en español de `gerar_apostila.py`. Reutiliza la identidad
visual de los documentos de la suite (`services.identidade_pdf`), las mismas
capturas de `capturas/` y las del teléfono en `celular/`. Las tablas de
módulos se leen del propio código: los nombres y descripciones de los módulos
aparecen como en el programa (en portugués), porque el programa es en portugués.

Uso:
    py ferramentas/apostila/gerar_apostila_es.py
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
SAIDA = AQUI / "saida" / "Manual_Usuario_Hexis_Forensics_ES.pdf"

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
# Documento
# ---------------------------------------------------------------------------
class Apostila(BaseDocTemplate):
    def __init__(self, caminho: Path):
        super().__init__(str(caminho), pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                         topMargin=2.6 * cm, bottomMargin=2.0 * cm,
                         title="Manual del Usuario — Hexis Forensics",
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
    tela.drawString(MARGEM, ALTURA * 0.52, "Manual del Usuario")
    tela.setFont(F["texto"], 15)
    tela.setFillColor(colors.HexColor("#8fb4e6"))
    tela.drawString(MARGEM, ALTURA * 0.52 - 30,
                    "Extracción y preservación de evidencia digital, paso a paso")
    tela.setFillColor(VERDE)
    tela.rect(MARGEM, ALTURA * 0.52 - 52, 3.2 * cm, 4, stroke=0, fill=1)
    tela.setFillColor(colors.HexColor("#c8d6e6"))
    tela.setFont(F["texto"], 10.5)
    tela.drawString(MARGEM, 3.4 * cm, identificacao_ferramenta())
    tela.drawString(MARGEM, 2.8 * cm, f"Edición de {date.today():%d/%m/%Y}")
    tela.drawString(MARGEM, 2.2 * cm, "Orientado por la norma ISO/IEC 27037")
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
    tela.drawRightString(LARGURA - MARGEM, topo - 0.45 * cm, "MANUAL DEL USUARIO")
    tela.setStrokeColor(AZUL)
    tela.setLineWidth(1.2)
    tela.line(MARGEM, topo - 0.95 * cm, LARGURA - MARGEM, topo - 0.95 * cm)
    tela.setStrokeColor(VERDE)
    tela.line(MARGEM, topo - 0.95 * cm, MARGEM + 2.2 * cm, topo - 0.95 * cm)
    tela.setFillColor(identidade.CINZA_TEXTO)
    tela.setFont(F["texto"], 7.5)
    tela.drawString(MARGEM, 1.1 * cm, f"Manual del Usuario — {identificacao_ferramenta()}")
    tela.drawRightString(LARGURA - MARGEM, 1.1 * cm, f"página {doc.page}")
    tela.restoreState()


# ---------------------------------------------------------------------------
# Piezas de contenido
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
    """Título de sección que nunca queda solo al pie de la página."""
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
    cores = {"atencao": ("#fdecea", "#b3261e", "Atención"),
             "dica": ("#e8f8f4", "#19c3a6", "Consejo"),
             "nota": ("#eef4fe", "#3f8dfd", "Para entender")}
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
        reserva = Table([[Paragraph(f"<i>[captura pendiente: {nome}]</i>", LEGENDA)]],
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
                         Paragraph(f"Figura {_figura[0]} — {legenda}", LEGENDA)])


def par_de_figuras(nome_1: str, legenda_1: str, nome_2: str, legenda_2: str,
                   altura_max: float = 9.5 * cm):
    """Dos pantallas de teléfono una al lado de la otra, cada una con su leyenda."""
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
            moldura = Paragraph(f"<i>[captura pendiente: {nome}]</i>", LEGENDA)
        celulas.append([moldura, Paragraph(f"Figura {_figura[0]} — {legenda}", LEGENDA)])
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
        altera = "sí — " + classe.alteracoes_no_dispositivo[0][0] if classe.alteracoes_no_dispositivo \
            else "no"
        exige = []
        if classe.requer_privilegio_root:
            exige.append(classe.rotulo_privilegio)
        if classe.selecao_expressa:
            exige.append("selección expresa (empieza sin marcar)")
        exige.append(f"perfil {classe.perfil_minimo.name}")
        linhas.append([f"<b>{identidade.escapar(classe.nome_exibicao)}</b>",
                       identidade.escapar(classe.descricao),
                       identidade.escapar(altera), identidade.escapar("; ".join(exige))])
    return tabela_simples(["Módulo", "Qué hace", "¿Altera el dispositivo?", "Requiere"], linhas,
                          [0.22, 0.42, 0.2, 0.16])


# ---------------------------------------------------------------------------
# Contenido
# ---------------------------------------------------------------------------
def conteudo() -> list:
    h = []

    # --- Sumario
    h += [NextPageTemplate("conteudo"), PageBreak()]
    sumario = TableOfContents()
    sumario.levelStyles = [SUMARIO_1, SUMARIO_2]
    h += [Paragraph("Índice", H1), Spacer(1, 10), sumario]

    # --- Nota de idioma + aviso legal (antes del capítulo 1). No entra en el índice.
    h += [PageBreak(),
          Paragraph("Nota — el programa está en portugués", H2),
          caixa("nota",
                "El <b>programa</b> y los <b>documentos que genera</b> (informes y laudo) están "
                "en <b>portugués</b>. Este manual en español explica cómo operarlo; los nombres "
                "de los botones y de las pantallas se citan en portugués, <b>tal como aparecen "
                "en la interfaz</b>, para que usted los encuentre sin dudar. Las tablas de "
                "módulos de los capítulos 4, 6 y 8 también muestran los nombres y las "
                "descripciones en portugués, porque se leen del propio programa."),
          Paragraph("Aviso — tratamiento de datos personales", H2),
          caixa("atencao",
                "Extraer y examinar datos de un dispositivo es <b>tratamiento de datos "
                "personales</b>. Use la herramienta solo con <b>base legal</b> (orden judicial, "
                "requerimiento de autoridad competente o consentimiento documentado del "
                "titular) y conforme a las normas aplicables del país donde se realiza el "
                "examen. Recoja solo lo necesario y guárdelo con seguridad. La legalidad del "
                "examen es responsabilidad de quien lo ejecuta y de quien lo autoriza."),
          ]

    # =====================================================================
    h += capitulo(1, "Presentación",
                  "El Hexis Forensics es una herramienta gratuita de extracción y preservación "
                  "de evidencia digital para teléfonos Android, iPhone y medios de "
                  "almacenamiento. Fue hecha para el procedimiento de rutina: recolectar lo que "
                  "responde al examen, registrar cómo se obtuvo cada dato y entregar documentos "
                  "que se sostienen por sí solos.")
    h += [secao("Por qué existe esta herramienta"),
          p("Buena parte de los exámenes en teléfonos y medios es de rutina y no necesita "
            "recursos avanzados. Aun así, quien hace ese trabajo suele tropezar con dos "
            "caminos malos."),
          sub("Las herramientas de pago son caras para la rutina"),
          itens([
              "<b>Licencia cara.</b> Las licencias anuales, por estación y cotizadas en dólares "
              "hacen inviable el uso a menor escala.",
              "<b>Capacidad ociosa.</b> Se paga por recursos avanzados que los casos simples y "
              "recurrentes no usan.",
              "<b>Formación cara.</b> La formación certificada es cara, cuando la mayoría de los "
              "casos pide una formación elemental y sólida.",
              "<b>Desplazamiento del dispositivo.</b> La evidencia viaja hasta donde hay "
              "herramienta: más etapas en la cadena de custodia y más riesgo para los datos "
              "volátiles.",
          ]),
          sub("Las herramientas libres son gratuitas, pero no simples"),
          itens([
              "<b>Complejas de operar.</b> Línea de comandos, entorno técnico y poca "
              "documentación: poco amigables para el usuario común de TI.",
              "<b>Sin documentación pericial.</b> En general, no generan cadena de custodia ni "
              "laudo: el examinador lo arma todo aparte.",
          ]),
          p("En la práctica, la herramienta libre es barata para descargar y cara para "
            "aprender: la complejidad de operación se vuelve complejidad y costo de formación."),
          caixa("nota", "Lo que faltaba: una herramienta simple, documentada y sin costo de "
                "licencia para la adquisición de rutina."),

          secao("La propuesta"),
          p("Adquisición lógica de rutina, simple de operar, con cadena de custodia, sellado "
            "por hash y documentos. Cada dolor tiene una respuesta:"),
          tabela_simples(["Dolor", "Respuesta"], [
              ["<b>Licencia cara</b>", "Sin costo de licencia."],
              ["<b>Capacidad ociosa</b>", "Foco en lo que pide la rutina: Android, iPhone y medios."],
              ["<b>Formación cara</b>", "Operación guiada, pantalla a pantalla, al alcance de una "
               "formación elemental y sólida."],
              ["<b>Desplazamiento del dispositivo</b>", "Windows 10 u 11 y un cable USB, donde "
               "esté el dispositivo."],
              ["<b>Complejidad de las libres</b>", "Interfaz gráfica, sin línea de comandos."],
              ["<b>Sin documentación pericial</b>", "Cadena de custodia, sellado por hash y laudo "
               "ya incluidos."],
          ], [0.32, 0.68]),

          secao("Qué hace y hasta dónde llega"),
          p("El alcance de cada recolección depende de la plataforma y del tipo de extracción. "
            "El cuadro resume lo que hace la versión 1.0:"),
          tabela_simples(["Plataforma", "Lógica", "Sistema de archivos", "Física (bit a bit)"], [
              ["<b>Android</b>", "Hace. En un dispositivo común, sin privilegios elevados.",
               "Parcial. Sin root, solo el almacenamiento compartido: las bases de datos de las "
               "aplicaciones no vienen.",
               "Solo con root. Partición de datos, perfil DES. Sin root, falla de forma explícita."],
              ["<b>iPhone</b>", "Hace. Copia de seguridad común y cifrada.",
               "No hace. Exigiría jailbreak.",
               "No hace. Exigiría explotar el arranque del dispositivo."],
              ["<b>Memorias USB y discos</b>", "Hace. Copia de las carpetas del usuario e índice "
               "con hash.",
               "Parcial. Índice de toda la unidad (ruta, fechas y SHA-256), sin copiar el "
               "contenido; la copia alcanza solo las carpetas del usuario.",
               "Hace. Imagen .img del volumen; exige Administrador y perfil DES."],
          ], [0.16, 0.26, 0.33, 0.25]),
          Spacer(1, 6),
          p("<b>Foco: adquisición lógica de rutina.</b> Sistema de archivos completo e imagen "
            "física solo con privilegios elevados, nunca en el iPhone, y declarados como tales."),

          secao("Cómo funciona, en cinco pasos"),
          passos([
              "<b>Conectar.</b> Android por la depuración USB, iPhone emparejado, medio con "
              "bloqueador de escritura.",
              "<b>Declarar el método.</b> La pantalla Método y limitaciones dice lo que la "
              "recolección no alcanza.",
              "<b>Identificar la pieza.</b> Caso, autorización, marca y modelo, sello y dos "
              "fotografías.",
              "<b>Extraer con hash.</b> Manifiesto con el SHA-256 de cada archivo: el sello de "
              "la adquisición.",
              "<b>Generar los documentos.</b> Informes, conversaciones seleccionadas y laudo.",
          ]),

          secao("Los documentos que genera"),
          p("Cada adquisición genera documentos que se sostienen por sí solos:"),
          itens([
              "<b>Informe de Extracción.</b> Línea de tiempo del procedimiento, entorno, "
              "módulos, desenlace y manifiesto de hashes.",
              "<b>Informe de Contenido.</b> Mensajes, llamadas y contactos interpretados, con "
              "el origen de cada línea.",
              "<b>Conversaciones seleccionadas.</b> En PDF, solo las conversaciones relevantes, "
              "completas.",
              "<b>Laudo Pericial.</b> El documento final, firmado por el examinador de la sesión.",
          ]),
          p("Todos se graban <b>fuera</b> de la adquisición sellada, que nunca se altera "
            "(capítulo 9)."),

          secao("El diferencial: no recolectado no es no existe"),
          p("Cada módulo termina en uno de tres estados:"),
          tabela_simples(["Estado", "Qué significa"], [
              ["<b>Concluido</b>", "El módulo obtuvo lo que se proponía."],
              ["<b>Concluido con salvedad</b>", "Obtuvo parte y declaró lo que no alcanzó."],
              ["<b>No obtuvo datos</b>", "No se adquirió nada de ese material, lo que no "
               "significa que el dato no exista en el dispositivo."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          p("En la práctica:"),
          itens([
              "<b>Consulta rechazada por el sistema:</b> el rechazo se preserva y se declara; "
              "una respuesta vacía se registra como tal.",
              "<b>Copia de seguridad cifrada no descifrada:</b> “nada se afirma” sobre el "
              "contenido.",
              "<b>Dispositivo bloqueado:</b> el laudo dice por qué no se extrajo.",
          ]),
          p("<b>Por qué importa:</b> la ausencia de un dato en el material nunca se presenta "
            "como ausencia del dato en el dispositivo."),

          secao("Los principios de la herramienta"),
          p("Tres ideas orientan cada pantalla y cada documento. Conocerlas ayuda a leer lo "
            "que la herramienta dice — y lo que, a propósito, no dice."),
          itens([
              "<b>Lo necesario, bien registrado.</b> La herramienta no mide la calidad por el "
              "volumen. Recolecta lo que interesa al examen y documenta la procedencia de cada "
              "dato: de qué archivo vino, por qué vía, con qué hash.",
              "<b>Nunca afirmar lo que no se verificó.</b> Cuando un dato no se obtiene, el "
              "documento dice POR QUÉ — el sistema rechazó, el módulo no se ejecutó, la copia de "
              "seguridad no lo contenía. La ausencia de un dato en el material nunca se presenta "
              "como ausencia del dato en el dispositivo.",
              "<b>Toda alteración en el dispositivo se registra y se justifica.</b> Los módulos "
              "que modifican el dispositivo están marcados, empiezan sin marcar y dejan en el "
              "registro del procedimiento lo que se hizo y por qué.",
          ]),
          secao("Lo que la herramienta no hace"),
          p("Ser honesto sobre el alcance es parte del método. La herramienta <b>no</b> "
            "desbloquea dispositivos, no sortea contraseñas, no recupera datos borrados, no "
            "extrae de la nube, no hace extracción física de iPhone y, en Android, solo hace "
            "extracción física con root. Tampoco decodifica todas las aplicaciones existentes. "
            "Para esos casos existen herramientas especializadas. El Hexis Forensics cubre la "
            "adquisición lógica de rutina — y lo que rodea a la extracción: cadena de custodia, "
            "sellado por hash, laudo, examen sin extracción y entrega documentada."),
          secao("Los roles DEFR y DES"),
          p("La norma ISO/IEC 27037 distingue al <b>DEFR</b> (primer respondedor: identifica, "
            "recolecta y preserva siguiendo un procedimiento) del <b>DES</b> (especialista: "
            "decide ante lo que escapa del procedimiento). Cada módulo declara el perfil mínimo "
            "que exige. La herramienta no impide a nadie — informa, y el laudo lo registra."),
          secao("Conformidad y transparencia"),
          sub("Conformidad"),
          itens([
              "<b>ISO/IEC 27037.</b> Identificación, recolección, adquisición y preservación.",
              "<b>Cadena de custodia.</b> Sello, fotografías y registro de cada etapa, conforme "
              "a la legislación aplicable en cada país.",
          ]),
          sub("Transparencia"),
          itens([
              "<b>Instalador con hash publicado.</b> El SHA-256 permite verificar el archivo "
              "antes de instalar (capítulo 2).",
              "<b>Probada en dispositivos reales.</b> Motorola, Samsung, iPhone 11 y memoria "
              "USB, con lo que se probó en cada uno (capítulo 11).",
              "<b>Limitaciones declaradas.</b> Por ejemplo: agente no verificado en Xiaomi; "
              "IMEI no entregado sin root a partir de Android 10.",
          ]),
          secao("Para ir más allá: el Entrenamiento Oficial"),
          p("Este manual enseña a operar la herramienta. El <b>Entrenamiento Oficial Hexis "
            "Forensics</b> va más allá: enseña la computación forense que sostiene cada pantalla "
            "— cadena de custodia, integridad por hash, los límites de cada tipo de extracción y "
            "la redacción del laudo. También hay oferta en alianza con instituciones de "
            "enseñanza superior e implantación con entrenamiento de equipos para policías y "
            "órganos de pericia."),
          ]

    # =====================================================================
    h += capitulo(2, "Instalación y primer acceso",
                  "Del instalador a la primera sesión: requisitos, creación de su perfil de "
                  "examinador y el código de recuperación, que es la única forma de volver si "
                  "se olvida la contraseña.")
    h += [secao("Requisitos"),
          itens([
              "Computadora con <b>Windows 10 u 11</b>.",
              "<b>Cable USB de datos</b> (algunos cables solo cargan y no sirven).",
              "Para <b>iPhone</b>: la aplicación <b>Dispositivos Apple</b> (Microsoft Store) o "
              "iTunes, que instalan el servicio de comunicación con el dispositivo.",
              "Para <b>discos de computadora</b>: dock o adaptador USB y un <b>bloqueador de "
              "escritura</b> de hardware (ver capítulo 8).",
          ]),
          secao("Verificar el instalador antes de instalar"),
          p("Junto con el instalador se publica su <b>hash SHA-256</b> — la huella digital del "
            "archivo. Verificarlo garantiza que el archivo descargado es exactamente el "
            "publicado, sin corrupción ni adulteración. Es la misma lógica del sello de las "
            "adquisiciones."),
          passos([
              "En la carpeta donde está el instalador, haga clic derecho en un espacio vacío y "
              "elija <b>Abrir en la Terminal</b>.",
              "Escriba <b>Get-FileHash .\\HexisForensics-Setup-1.0.0.exe</b> y pulse Enter.",
              "Compare el valor de la columna <b>Hash</b> con el publicado. Un solo carácter "
              "diferente significa un archivo diferente: no lo instale.",
          ]),
          secao("Instalación"),
          p("Ejecute el instalador y siga las pantallas. Marque la opción <b>Crear acceso "
            "directo en el Escritorio</b>. Los casos quedan en la carpeta "
            "<b>HexisForensics-Casos</b>, dentro de la carpeta de su usuario de Windows — fuera "
            "de la carpeta del programa, para que una actualización nunca alcance la evidencia. "
            "Para actualizar, basta con instalar la versión nueva encima: casos y examinadores "
            "se preservan."),
          sub("El aviso azul de Windows"),
          p("El instalador es gratuito y no tiene firma digital pagada. Por eso, en la primera "
            "ejecución, Windows muestra la pantalla <b>«Windows protegió su PC»</b>, con editor "
            "desconocido. Es un aviso, no un diagnóstico de virus:"),
          passos([
              "Haga clic en <b>Más información</b>.",
              "Verifique el nombre del archivo y haga clic en <b>Ejecutar de todas formas</b>.",
          ]),
          caixa("nota", "Si el <b>Control Inteligente de Aplicaciones</b> de Windows 11 está "
                "activado, bloquea el instalador sin ofrecer el botón: exige firma digital, que "
                "esta versión no tiene. No hay versión portátil. Las salidas son instalar en "
                "otra computadora, pedir al área de TI que autorice el programa, o <b>ejecutar "
                "desde el código fuente</b> (sección siguiente)."),
          secao("Alternativa: ejecutar desde el código fuente"),
          p("Cuando el instalador se bloquea y no hay forma de autorizarlo, la herramienta se "
            "ejecuta directamente desde el código fuente, como cualquier proyecto de código "
            "abierto — no hay instalación, la misma suite la ejecuta Python. Exige algunos "
            "pasos más, pero no depende de firma digital."),
          passos([
              "Instale <b>Python 3.13</b> desde <b>python.org</b> (en Downloads, elija el "
              "instalador de Windows de la versión <b>3.13</b>). <b>No use el 3.14</b>: una de "
              "las bibliotecas del iPhone aún no tiene una versión lista para él. En la primera "
              "pantalla del instalador de Python, marque <b>Add python.exe to PATH</b>.",
              "Descargue el código desde la <b>página de versiones (Releases)</b> del proyecto: "
              "<b>github.com/HexisForensics/HexisForensics/releases</b>. En la versión más "
              "reciente, descargue el <b>Fuente (ZIP)</b>. <b>No</b> use el <b>Code → Download "
              "ZIP</b> de la página principal — ese trae la versión en desarrollo, sin versión "
              "etiquetada.",
              "<b>Verifique el hash del ZIP</b>, como en el instalador: en la carpeta del "
              "archivo, <b>Abrir en la Terminal</b> y "
              "<b>Get-FileHash .\\HexisForensics-1.0.0-fonte.zip</b>. El valor tiene que ser "
              "idéntico al publicado en la Release.",
              "Extraiga la carpeta. Ábrala, haga clic derecho en un espacio vacío y elija "
              "<b>Abrir en la Terminal</b>.",
              "Escriba <b>py -m pip install -r requirements.txt</b> y pulse Enter. Espere la "
              "instalación de las bibliotecas (tarda la primera vez).",
              "Escriba <b>py main.py</b> y pulse Enter. La herramienta abre en la pantalla de "
              "entrada, igual que la versión instalada.",
          ]),
          caixa("nota", "Ejecutando desde el código fuente, los casos quedan en "
                "<b>HexisForensics-Casos</b>, en su carpeta de usuario de Windows — la misma de "
                "la versión instalada, y <b>fuera</b> de la carpeta del programa, para que "
                "actualizar (descargar el ZIP nuevo) nunca alcance las adquisiciones. El "
                "<b>adb.exe</b> ya viene en el ZIP, así que la extracción de Android funciona "
                "sin paso extra; para el iPhone, sigue valiendo la aplicación Dispositivos "
                "Apple (Requisitos)."),
          secao("Primer acceso: su perfil de examinador"),
          p("La herramienta abre en la <b>pantalla de entrada</b>. Cada examinador tiene perfil "
            "y contraseña propios: es eso lo que identifica quién hizo cada extracción y quién "
            "firma cada laudo."),
          figura("01_entrada", "Pantalla de entrada: elija su nombre y escriba su contraseña.",
                 altura_max=9 * cm),
          passos([
              "La primera vez, haga clic en <b>Novo examinador</b> (Nuevo examinador).",
              "Complete el <b>nombre</b> tal como debe constar en los documentos, el "
              "<b>registro profesional</b> y la <b>institución o laboratorio</b>.",
              "Cree una <b>contraseña</b> de al menos 6 caracteres y repítala.",
              "Haga clic en <b>Cadastrar e entrar</b> (Registrar y entrar).",
              "Anote o imprima el <b>código de recuperación</b> (sección siguiente), marque la "
              "confirmación y haga clic en <b>Continuar</b>.",
          ]),
          figura("02_novo_examinador", "Registro de un nuevo examinador.", altura_max=9 * cm),
          secao("El código de recuperación"),
          p("Al crear la contraseña, la herramienta muestra un código de 16 caracteres, en "
            "cuatro grupos. Aparece <b>una sola vez</b>. Es la única forma de entrar si olvida "
            "la contraseña: nadie — ni el fabricante — puede restablecerla. Una vez usado, el "
            "código se cambia por otro, que también aparece una vez."),
          figura("03_codigo_recuperacao", "El código de recuperación, con las opciones de "
                 "imprimir y copiar.", altura_max=9 * cm),
          caixa("atencao", "Guarde el código lejos de la computadora: impreso en una carpeta, "
                "en un gestor de contraseñas, en un sobre sellado. Quien pierde la contraseña "
                "<b>y</b> el código tiene que crear un perfil nuevo. Las adquisiciones antiguas "
                "siguen a su nombre, porque el nombre está grabado dentro del sello de cada una."),
          secao("Olvidé mi contraseña"),
          passos(["En la pantalla de entrada, elija su nombre y haga clic en <b>Esqueci minha "
                  "senha</b> (Olvidé mi contraseña).",
                  "Escriba el código de recuperación (con o sin guiones, mayúsculas o "
                  "minúsculas).",
                  "Elija la nueva contraseña y haga clic en <b>Redefinir e entrar</b> "
                  "(Restablecer y entrar).",
                  "Anote el <b>nuevo</b> código que aparece: el antiguo dejó de valer."]),
          secao("Durante la sesión"),
          itens([
              "Su nombre aparece en el <b>pie de la barra lateral</b>, con la hora de entrada.",
              "<b>Trocar examinador</b> (Cambiar examinador) devuelve a la pantalla de entrada, "
              "para que entre otra persona. No es posible cambiar durante una extracción.",
              "Después de <b>15 minutos sin uso</b>, la pantalla se bloquea y pide la contraseña "
              "de nuevo. Una extracción en curso <b>sigue ejecutándose</b> por detrás.",
              "Cinco contraseñas erradas seguidas bloquean a ese examinador por 10 minutos.",
              "En <b>Examinadores</b> (barra lateral) usted corrige sus datos, cambia la "
              "contraseña, genera un código de recuperación nuevo o elimina su perfil. El botón "
              "<b>Novo examinador</b> abre el registro de otra persona: ella misma crea la "
              "contraseña y recibe su código, y pasa a ser el examinador de la sesión. Nadie ve "
              "ni altera los datos de otro examinador.",
              "Entradas, bloqueos, recuperaciones y eliminaciones quedan en el <b>registro de "
              "accesos</b> de la estación.",
          ]),
          caixa("nota", "El registro de cada adquisición dice: “sesión abierta con la "
                "contraseña del examinador en esta estación”. La contraseña garantiza la "
                "<b>autoría</b> — nadie opera en nombre de otro por descuido. No prueba la "
                "identidad (una contraseña prestada también entra) y no protege los archivos "
                "del caso, que quedan en el disco."),
          ]

    # =====================================================================
    h += capitulo(3, "Preparando el teléfono Android",
                  "Sin privilegios elevados, la extracción de Android se hace por el ADB, la "
                  "herramienta de depuración del propio Android. Para ello, el dispositivo "
                  "necesita autorizar la computadora.")
    h += [secao("Etapa 1 — Activar las Opciones de desarrollador"),
          passos([
              "Abra <b>Configuración → Acerca del teléfono</b> (en Motorola, <b>Configuración → "
              "Sistema → Acerca del dispositivo</b>; en otros: «Información del software»).",
              "Baje hasta el final y toque <b>7 veces</b> en <b>Número de compilación</b> (en "
              "algunos dispositivos: «Versión de MIUI», «Versión del SO» o «Número de "
              "versión»). El dispositivo puede pedir el código de desbloqueo.",
              "Aparece el mensaje <b>«Ahora eres desarrollador»</b> — o, si ya estaba activo, "
              "«Ya eres desarrollador».",
          ]),
          par_de_figuras("android_02_numero_versao", "Número de compilación: toque 7 veces. "
                         "(IMEI y direcciones cubiertos en este manual.)",
                         "android_03_desenvolvedor", "La confirmación del modo desarrollador."),
          secao("Etapa 2 — Activar la depuración USB"),
          passos([
              "Abra <b>Configuración → Sistema → Avanzado → Opciones de desarrollador</b> (en "
              "algunos dispositivos, en «Configuración adicional»).",
              "Active <b>Depuración USB</b>.",
              "Active también <b>Permanecer activo</b>: la pantalla no se apaga mientras el "
              "dispositivo está en el cable, y la conexión no se cae en medio de la extracción.",
          ]),
          par_de_figuras("android_04_depuracao_usb", "Depuración USB activada.",
                         "android_05_permanecer_ativo", "Permanecer activo activado."),
          secao("Etapa 3 — Autorizar la computadora"),
          passos([
              "Conecte el cable de datos. En la pantalla del dispositivo aparece <b>¿Permitir "
              "la depuración USB?</b>.",
              "Marque <b>Permitir siempre desde esta computadora</b>.",
              "Toque en <b>Permitir</b>.",
              "En la herramienta, página <b>Android</b>, haga clic en <b>Verificar Conexão</b> "
              "(Verificar conexión). El estado debe decir que el dispositivo está conectado y "
              "autorizado.",
          ]),
          par_de_figuras("android_06_permitir_depuracao", "El aviso de autorización "
                         "(reproducción: Android no permite capturar esta pantalla).",
                         "android_07_modo_usb", "Preferencias de USB, si la conexión se cae."),
          caixa("dica", "Si el aviso no aparece, o el dispositivo figura como <b>no "
                "autorizado</b>: desbloquee la pantalla, toque en <b>Revocar autorizaciones de "
                "depuración USB</b> (en las Opciones de desarrollador) y reconecte el cable. Si "
                "la conexión se cae durante la extracción, abra <b>Configuración → Dispositivos "
                "conectados → USB</b> y elija <b>Transferencia de archivos</b>."),
          figura("04_janela_android", "Página Android: estado del dispositivo, módulos de "
                 "extracción y consola."),
          secao("Particularidades por fabricante"),
          sub("Xiaomi (MIUI / HyperOS)"),
          p("Además de la depuración USB, active <b>Instalar vía USB</b> y <b>Depuración USB "
            "(ajustes de seguridad)</b>. Las dos exigen una <b>cuenta Xiaomi</b> con sesión "
            "iniciada y, a veces, un chip insertado. Sin ellas, el dispositivo rechaza la "
            "aplicación agente. <i>En esta versión, el agente aún no se ha verificado en "
            "dispositivos Xiaomi: si se rechaza la instalación, la herramienta registra el "
            "rechazo y no concluye nada sobre el contenido.</i>"),
          sub("Samsung"),
          p("Las <b>Opciones de desarrollador</b> aparecen al final de la lista de "
            "Configuración, justo debajo de <b>Acerca del teléfono</b>, tras los 7 toques en "
            "<b>Información del software → Número de compilación</b>."),
          p("Verificado en un <b>Galaxy A22 con Android 13 (One UI 5.1)</b>, de fábrica y sin "
            "privilegios elevados: la aplicación agente se instaló, recolectó y se eliminó "
            "<b>sin ninguna confirmación en pantalla</b> — ni «¿Instalar app?», ni Play "
            "Protect, ni pedido de permiso. Samsung también entrega la agenda de contactos al "
            "módulo común, sin el agente."),
          p("En otros modelos o versiones, <b>Play Protect</b> puede preguntar si la aplicación "
            "es segura. Si la pregunta aparece, confirme la instalación en la pantalla del "
            "dispositivo."),
          caixa("atencao", "Activar la depuración USB y autorizar la computadora son "
                "alteraciones de configuración del dispositivo. La herramienta las registra en "
                "el procedimiento como imposición del método: sin ellas no existe adquisición "
                "lógica en un dispositivo sin privilegios elevados."),
          ]

    # =====================================================================
    h += capitulo(4, "Extracción Android, paso a paso",
                  "Del clic en Iniciar Extracción al sellado de la adquisición. Cada etapa "
                  "existe para registrar algo que el laudo va a necesitar.")
    h += [secao("Elegir los módulos"),
          p("La lista de módulos aparece en la página Android. Los módulos comunes ya vienen "
            "marcados. Los que alteran el dispositivo de forma relevante son de <b>selección "
            "expresa</b>: empiezan sin marcar y el botón <b>Marcar todos</b> no los alcanza — "
            "hay que elegirlos uno a uno, a propósito."),
          secao("La secuencia de pantallas"),
          passos([
              "Haga clic en <b>Iniciar Extração</b> (Iniciar Extracción). La herramienta pide "
              "la confirmación del examinador de la sesión («Esta extracción se registrará como "
              "hecha por…»).",
              "<b>Método y limitaciones</b>: lo que la recolección elegida no va a alcanzar y "
              "lo que puede alterarse en el dispositivo. Es el momento de decidir — después se "
              "vuelve registro. Lea y haga clic en <b>Ciente — Prosseguir</b> (Enterado — "
              "Continuar).",
              "<b>Caso</b>: cree un caso nuevo o elija uno existente. Un caso reúne varios "
              "dispositivos; cada dispositivo se vuelve una adquisición dentro de él.",
              "<b>Autorización</b>: adjunte el documento que autoriza el acceso a los datos. "
              "Continuar sin adjuntar está permitido, pero queda registrado que no había "
              "documento a la vista.",
              "<b>Dispositivo y cadena de custodia</b>: marca y modelo, color, estado, "
              "<b>número del sello</b> (obligatorio) y al menos <b>dos fotografías</b> de la "
              "pieza (anverso y reverso).",
              "La extracción comienza. Siga por la consola y por la columna de estado de cada "
              "módulo.",
          ]),
          figura("07_metodo", "Método y limitaciones: lo que la recolección no alcanza, antes "
                 "de empezar.", altura_max=10 * cm),
          figura("08_caso", "Caso nuevo o existente.", altura_max=8 * cm),
          figura("10_dispositivo", "Pieza, sello y fotografías.", largura=UTIL * 0.6,
                 altura_max=10 * cm),
          secao("Cómo leer el resultado"),
          p("Cada módulo termina en uno de tres estados, y no son intercambiables:"),
          tabela_simples(["Estado", "Significa"], [
              ["<b>Concluido</b>", "El módulo obtuvo lo que se proponía."],
              ["<b>Concluido con salvedad</b>", "Obtuvo parte, y declaró lo que no alcanzó (por "
               "ejemplo, una consulta rechazada por el sistema)."],
              ["<b>No obtuvo datos</b>", "No se adquirió nada de ese material. Esto <b>no</b> "
               "significa que el dato no exista en el dispositivo."],
          ], [0.28, 0.72]),
          Spacer(1, 8),
          p("Al final, la herramienta genera el <b>manifiesto de hashes</b> (el sello de la "
            "adquisición): el SHA-256 de cada archivo adquirido. También verifica si el "
            "dispositivo conectado al final es el mismo del inicio."),
          caixa("atencao", "No cierre la herramienta durante una extracción: la adquisición "
                "quedaría sin sello. Si necesita detenerla, use <b>Cancelar</b> y espere el "
                "mensaje de extracción finalizada."),
          secao("Los módulos disponibles"),
          p("La tabla de abajo se genera del propio código de la herramienta; los nombres y las "
            "descripciones de los módulos aparecen en portugués, como en el programa."),
          tabela_de_modulos("Android"),
          ]

    # =====================================================================
    h += capitulo(5, "WhatsApp, paso a paso",
                  "Sin privilegios elevados, la base de mensajes de WhatsApp queda en un área "
                  "privada de la aplicación, inaccesible. El camino es la propia copia de "
                  "seguridad local de WhatsApp, protegida con una clave de 64 dígitos que el "
                  "examinador conoce. Las pantallas de este capítulo son de un dispositivo "
                  "real; la clave aparece cubierta.")
    h += [secao("Por qué este es el camino"),
          p("WhatsApp graba copias de seguridad locales cifradas "
            "(<b>msgstore.db.crypt15</b>) en una carpeta que la herramienta puede copiar. "
            "Cuando la copia está protegida por una <b>clave de 64 dígitos</b> — y no por "
            "contraseña ni por clave de acceso —, quien tiene la clave puede descifrarla. La "
            "herramienta descifra, verifica la autenticidad del contenido y lee las "
            "conversaciones."),
          caixa("atencao", "Tocar la protección de la copia de seguridad y ordenar a WhatsApp "
                "que haga la copia son <b>alteraciones en el dispositivo examinado</b>, hechas "
                "por el examinador. Al descifrar, la herramienta las registra en el complemento "
                "del caso, junto con la clave."),
          secao("Etapa 1 — Ver cómo está protegida la copia de seguridad"),
          p("En WhatsApp, abra <b>Ajustes → Chats → Copia de seguridad</b> y baje hasta "
            "<b>Copia de seguridad cifrada de extremo a extremo</b>. Lo que está escrito debajo "
            "decide el camino:"),
          tabela_simples(["Lo que aparece", "Qué hacer"], [
              ["<b>Desactivado</b>", "Vaya a la Etapa 2."],
              ["<b>Activado · Contraseña</b> o <b>Activado · Clave de acceso</b>",
               "No sirve: la herramienta descifra solo con la clave de 64 dígitos. Toque en la "
               "opción, en <b>Desactivar</b>, informe la contraseña de la copia y confirme. "
               "Después, Etapa 2."],
              ["<b>Activado · Clave de 64 dígitos</b> (en algunas versiones, en inglés: "
               "<b>On · 64-digit key</b>)",
               "Sirve, si alguien tiene la clave anotada. WhatsApp solo muestra la clave al "
               "crearla: sin ella anotada, desactive y cree una nueva (Etapa 2)."],
          ], [0.4, 0.6]),
          Spacer(1, 6),
          par_de_figuras("whatsapp_02_criptografado", "Activado · Contraseña: no sirve.",
                         "whatsapp_03_tela_criptografia", "Copia protegida con contraseña: "
                         "toque en Desactivar."),
          par_de_figuras("whatsapp_04_desativado", "Confirme la desactivación.",
                         "whatsapp_05_apos_desativar", "Ahora: Desactivado."),
          secao("Etapa 2 — Activar con la clave de 64 dígitos"),
          passos([
              "Toque en <b>Copia de seguridad cifrada de extremo a extremo</b>.",
              "<b>NO toque el botón verde «Usar clave de acceso».</b> Toque en <b>Más "
              "opciones</b>.",
              "Elija <b>Clave de cifrado de 64 dígitos</b> (y no «Contraseña»).",
              "Toque en <b>Generar clave de 64 dígitos</b>.",
              "La clave aparece: 16 grupos de 4 caracteres. <b>Anótela</b> — o léala por el "
              "cable (ver consejo). Toque en <b>Continuar</b>.",
              "WhatsApp muestra la clave de nuevo para verificación. Toque en <b>Anoté mi clave "
              "de 64 dígitos</b>.",
              "Toque en <b>Crear</b>. El proceso termina en segundo plano.",
          ]),
          par_de_figuras("whatsapp_06_ativar", "La trampa: el botón verde no sirve. Toque en "
                         "Más opciones.",
                         "whatsapp_07_mais_opcoes", "Elija la clave de 64 dígitos."),
          par_de_figuras("whatsapp_08_gerar_chave", "Generar la clave.",
                         "whatsapp_09_chave", "La clave (cubierta en este manual)."),
          par_de_figuras("whatsapp_10_confirmar_chave", "Verificar y confirmar que la anotó.",
                         "whatsapp_11_criar", "Crear la copia de seguridad protegida."),
          caixa("dica", "Con el cable conectado, la clave puede leerse de la pantalla por el "
                "ADB, sin error de tipeo: el texto de la pantalla se obtiene por <b>uiautomator "
                "dump</b>. En la duda, fotografíe la pantalla de la clave y adjunte la foto al "
                "caso."),
          secao("Etapa 3 — Grabar la copia de seguridad EN EL DISPOSITIVO"),
          passos([
              "En <b>Copia de seguridad</b>, verifique que <b>Cuenta de Google</b> esté en "
              "<b>Ninguna</b> y <b>Copia automática</b> en <b>Desactivado</b> (en versiones "
              "antiguas: <b>Hacer copia en Google Drive</b> en <b>Nunca</b>).",
              "Toque en <b>Guardar</b> (Hacer copia) y espere a que termine.",
              "Verifique la línea <b>Local:</b> — debe mostrar la hora de ahora.",
          ]),
          par_de_figuras("whatsapp_12_ativado_chave", "Protegida con la clave de 64 dígitos.",
                         "whatsapp_13_backup_feito", "Copia local hecha: verifique la hora en "
                         "«Local»."),
          caixa("atencao", "Haga la copia de seguridad <b>el día del examen</b>, después de "
                "activar la clave. Una copia antigua — o hecha con contraseña — no abre con la "
                "clave nueva y no trae los mensajes recientes."),
          secao("Etapa 4 — En la herramienta: extraer"),
          p("Haga la extracción normalmente (capítulo 4), con el módulo <b>WhatsApp — Mídia e "
            "Backups</b> marcado. Copia los medios y las copias cifradas y registra, "
            "preguntándole al propio dispositivo, <b>cuándo se grabó cada copia</b>."),
          secao("Etapa 5 — En la herramienta: descifrar"),
          passos([
              "Abra <b>Casos e Documentos</b> (Casos y Documentos), elija el caso y la "
              "adquisición.",
              "Haga clic en <b>Decifrar backup</b> (Descifrar copia de seguridad).",
              "Escriba la clave en los 16 campos (o pegue la clave entera en cualquier campo).",
              "Haga clic en <b>Decifrar</b> (Descifrar). La copia descifrada va a la carpeta "
              "<b>decifrados</b> del caso, <b>fuera</b> de la adquisición sellada, con la "
              "procedencia al lado. La clave queda registrada en el complemento del caso, para "
              "que otro examinador pueda repetir el descifrado.",
              "A continuación se genera el <b>Informe de Contenido</b>, con las conversaciones.",
          ]),
          figura("18_chave_whatsapp", "La clave de 64 dígitos, en 16 grupos, en la herramienta.",
                 largura=UTIL * 0.6, altura_max=9 * cm),
          secao("Etapa 6 — Leer y seleccionar las conversaciones"),
          p("El Informe de Contenido trae la planilla (CSV) y el cuaderno HTML con el texto "
            "íntegro. Las conversaciones muy largas aparecen en el PDF como índice, para que el "
            "documento no tenga miles de páginas. Para el laudo, use <b>PDF de conversas "
            "selecionadas</b> (PDF de conversaciones seleccionadas): marque las conversaciones "
            "relevantes y la herramienta genera el PDF solo de ellas, completas, con el origen "
            "de cada mensaje."),
          figura("17_conversas", "Selección de las conversaciones que van al PDF."),
          secao("La fecha de la copia en los documentos"),
          p("El contenido descifrado retrata el dispositivo <b>en la fecha en que se grabó la "
            "copia de seguridad</b>, no el día del examen. Por eso el informe y el laudo traen "
            "la <b>Nota de la fuente</b>: la fecha de la copia (informada por el propio "
            "dispositivo y registrada en el sello), el mensaje más reciente que contiene y el "
            "aviso de que los mensajes posteriores no están en el material."),
          secao("Cuando la copia no abre"),
          itens([
              "<b>Clave escrita mal</b>: no se descifra nada. Verifique grupo a grupo.",
              "<b>Copia protegida por contraseña o clave de acceso</b>: no abre con ninguna "
              "clave. Rehaga las etapas 1 a 3 y extraiga de nuevo.",
              "<b>Copia hecha antes de activar la clave</b>: no abre con ella. Haga una copia "
              "nueva (etapa 3) y extraiga de nuevo.",
              "<b>Copia .crypt14 o anterior</b>: no abre con la clave de 64 dígitos.",
              "<b>Sin copia de seguridad en el dispositivo</b>: el módulo dice que solo "
              "encontró medios. Esto no significa ausencia de mensajes.",
          ]),
          ]

    # =====================================================================
    h += capitulo(6, "iPhone",
                  "Sin jailbreak, el camino es la copia de seguridad local del iPhone — la "
                  "misma que haría iTunes —, obtenida después de que el dispositivo confía en "
                  "la computadora.")
    h += [secao("Antes de empezar: la computadora"),
          passos([
              "Instale la aplicación <b>Dispositivos Apple</b> (Microsoft Store) o iTunes. "
              "Instala el servicio de Windows que conversa con el iPhone. No hace falta abrirla "
              "ni sincronizar nada — y <b>no</b> sincronice: la sincronización graba en el "
              "dispositivo.",
              "Si el iPhone ya estaba en el cable durante la instalación, <b>desconéctelo y "
              "conéctelo de nuevo</b>: el servicio solo ve el dispositivo conectado después de "
              "que empezó a ejecutarse.",
          ]),
          secao("Antes de empezar: el iPhone"),
          passos([
              "El iPhone necesita haber <b>terminado la configuración inicial</b>. En un "
              "dispositivo restaurado, iOS rechaza la copia de seguridad hasta entonces (la "
              "herramienta muestra «configuración inicial no concluida — código 212»). La "
              "pantalla de la <b>cuenta Apple</b> puede saltarse: toque en <b>¿Olvidó la "
              "contraseña o no tiene una Cuenta Apple?</b> y elija configurar más tarde. No "
              "hace falta crear cuenta para el examen.",
              "Desbloquee la pantalla, conecte el cable y toque en <b>Confiar</b> cuando "
              "aparezca <b>¿Confiar en esta computadora?</b>. El iPhone pide el código de "
              "desbloqueo.",
              "En la herramienta, página <b>iPhone</b>, haga clic en <b>Verificar Conexão</b> "
              "(Verificar conexión).",
          ]),
          figura("05_janela_iphone", "Página iPhone."),
          caixa("atencao", "Durante la copia de seguridad, el iPhone necesita quedar "
                "<b>desbloqueado</b>. Con el <b>Modo de Bajo Consumo</b> activado, el bloqueo "
                "automático queda fijo en 30 segundos. Prefiera mantener la pantalla activa "
                "tocándola. Si hace falta cambiar el <b>Bloqueo Automático</b> o apagar el Modo "
                "de Bajo Consumo, es una alteración hecha en el dispositivo examinado: "
                "regístrela en las observaciones del examen."),
          secao("Los módulos"),
          tabela_de_modulos("iOS"),
          Spacer(1, 8),
          secao("Copia común o copia cifrada"),
          p("La copia común no toca la configuración del dispositivo y trae iMessage y SMS, "
            "agenda, las fotos del carrete de la cámara y datos de aplicaciones (WhatsApp "
            "incluido). Pero iOS solo incluye el <b>registro de llamadas</b> y otros datos "
            "sensibles en la copia <b>cifrada</b>. El módulo de contraseña temporal define una "
            "contraseña generada por la herramienta, hace la copia cifrada y <b>retira la "
            "contraseña</b> al final, verificando la retirada."),
          tabela_simples(["Comparación", "Copia común", "Copia cifrada (contraseña temporal)"], [
              ["¿Altera el dispositivo?", "No (solo el emparejamiento, que toda copia exige)",
               "Sí: define y retira una contraseña de copia, con registro"],
              ["Mensajes, agenda, WhatsApp", "Sí, leídos directamente", "Sí, tras descifrar"],
              ["Registro de llamadas", "<b>No</b> — iOS no lo incluye", "Sí, tras descifrar"],
              ["Fotos y su GPS", "Sí", "No leídas en esta versión"],
              ["Código en la pantalla del iPhone", "Una vez (confiar)", "Hasta tres veces"],
          ], [0.28, 0.33, 0.39]),
          Spacer(1, 8),
          p("Las dos pueden marcarse juntas: cada copia queda en su carpeta "
            "(<b>backup_ios</b> y <b>backup_ios_cifrado</b>), y el contenido se copia dos "
            "veces. En la copia cifrada, el iPhone pide el código <b>hasta tres veces</b>: para "
            "aceptar la contraseña temporal, a veces durante la copia y para retirarla. "
            "Mantenga el dispositivo a mano."),
          caixa("atencao", "Si el dueño ya definió una contraseña de copia, el módulo de "
                "contraseña temporal <b>no se ejecuta</b> — cambiar la contraseña del dueño "
                "sería una alteración irreversible. Use la copia común: sale cifrada con la "
                "contraseña del dueño, y el contenido solo se lee con ella (botón Decifrar "
                "backup)."),
          secao("Descifrar la copia de seguridad"),
          passos([
              "Abra <b>Casos e Documentos</b> (Casos y Documentos), elija el caso y la "
              "adquisición del iPhone.",
              "Haga clic en <b>Decifrar backup</b> (Descifrar copia de seguridad).",
              "Cuando la copia se hizo con la contraseña temporal, la contraseña <b>ya viene "
              "rellenada</b>: la herramienta la lee del archivo <b>senha_do_backup.txt</b> de "
              "la adquisición, y solo si coincide con el sello. Confirme.",
              "Las bases descifradas van a la carpeta <b>decifrados</b> del caso, fuera de la "
              "adquisición sellada, cada una con la procedencia al lado. La contraseña queda "
              "registrada en el complemento del caso, para que otro examinador repita el "
              "descifrado.",
          ]),
          p("La contraseña también aparece en el desenlace de la recolección y en la consola. "
            "Si la copia estaba cifrada con la contraseña del dueño, es esa la que se escribe."),
          secao("Qué aparece en el Informe de Contenido"),
          itens([
              "Cada bloque dice de qué copia vino: <b>copia común del iPhone</b> o <b>copia "
              "cifrada del iPhone, descifrada</b>.",
              "Copia cifrada aún no descifrada: el informe dice que <b>nada se afirma</b> sobre "
              "el contenido — y no que esté vacío.",
              "Archivo que iOS no puso en la copia (las llamadas, en la copia común): el informe "
              "dice que la copia no lo contiene, y que eso no prueba ausencia.",
              "<b>WhatsApp</b>: textos, fotos, audios, grupos y ubicaciones compartidas, con las "
              "coordenadas y el enlace <b>abrir en el mapa</b>. Los registros que el propio "
              "WhatsApp genera — el aviso de cifrado, la creación de un grupo — aparecen con "
              "sentido <b>Sistema</b> y la observación «no es un mensaje escrito». El tipo de "
              "registro que la herramienta no conoce aparece como <b>no reconocido</b>, sin "
              "conjeturas sobre lo que sea.",
              "<b>Ubicaciones de las fotos</b>: las fotos del carrete de la cámara con GPS (ver "
              "capítulo 9).",
          ]),
          ]

    # =====================================================================
    h += capitulo(7, "Examen sin extracción",
                  "Dispositivo bloqueado por credencial, que no enciende o dañado: el examen "
                  "existe aun sin extracción, y el laudo negativo necesita la misma cadena de "
                  "custodia.")
    h += [passos([
              "En la página Android o iPhone, haga clic en <b>Exame sem extração</b> (Examen "
              "sin extracción).",
              "Siga las mismas pantallas de caso, autorización, pieza, sello y fotografías.",
              "En el formulario, informe si el dispositivo enciende, el estado en que se "
              "recibió, la batería, si estaba aislado de la red, el <b>tipo de bloqueo</b> y lo "
              "que se intentó. La recomendación ya viene rellenada.",
              "Si el dispositivo enciende, la herramienta <b>intenta la conexión sin "
              "alterarlo</b> y guarda la respuesta como prueba: en Android, el listado del ADB "
              "(por ejemplo, «NO AUTORIZADO»); en iPhone, una sesión sin pedido de "
              "emparejamiento.",
              "Genere el <b>Laudo Pericial</b> en Casos y Documentos: sale la versión «Examen "
              "sin Extracción».",
          ]),
          figura("11_exame_sem_extracao", "Estado del dispositivo e intentos.",
                 largura=UTIL * 0.6, altura_max=10 * cm),
          p("La conclusión dice que no fue posible extraer, y por qué — y que eso <b>no</b> "
            "permite concluir nada sobre el contenido del dispositivo."),
          ]

    # =====================================================================
    h += capitulo(8, "Discos y memorias USB",
                  "La plataforma Almacenamiento examina unidades conectadas a la computadora: "
                  "memorias USB, discos externos y el disco retirado de una computadora "
                  "examinada.")
    h += [caixa("atencao", "El disco de una computadora examinada se <b>retira</b> y se conecta "
                "a la estación por dock o adaptador, con un <b>bloqueador de escritura de "
                "hardware</b> entre los dos. La herramienta no sustituye al bloqueador. La "
                "estación del propio examinador aparece en la lista, identificada, para que no "
                "se elija por error."),
          figura("06_janela_armazenamento", "Página Almacenamiento: elección de la unidad."),
          tabela_de_modulos("Computador"),
          Spacer(1, 8),
          p("La <b>Imagen del Volumen</b> exige abrir la herramienta como Administrador. Un "
            "volumen cifrado con BitLocker se detecta y se informa."),
          ]

    # =====================================================================
    h += capitulo(9, "Casos y Documentos",
                  "Todo lo que se hace después de la extracción: documentos, examen del "
                  "material, entrega y organización de los casos — sin necesidad de abrir las "
                  "carpetas en Windows.")
    h += [figura("12_casos_ficha", "Casos y Documentos: casos, ficha, dispositivos y acciones."),
          secao("Los documentos"),
          tabela_simples(["Documento", "Para qué sirve"], [
              ["<b>Informe de Extracción</b>", "Línea de tiempo del procedimiento, entorno, "
               "módulos, desenlace y el manifiesto de hashes."],
              ["<b>Informe de Contenido</b>", "Los mensajes, llamadas y contactos "
               "interpretados: planillas CSV, cuaderno HTML y PDF, con el origen de cada línea."],
              ["<b>PDF de conversaciones seleccionadas</b>", "Solo las conversaciones "
               "relevantes, completas."],
              ["<b>Laudo Pericial</b>", "El documento final, firmado por el examinador de la "
               "sesión."],
          ], [0.3, 0.7]),
          Spacer(1, 8),
          p("Los documentos abren en el <b>visor de la herramienta</b> (páginas, zoom, "
            "imprimir, guardar copia) y quedan listados en la pestaña <b>Documentos</b>. Se "
            "graban <b>fuera</b> de la adquisición sellada, que nunca se altera."),
          figura("15_visualizador", "Visor de PDF.", altura_max=10 * cm),
          figura("22_laudo_pagina", "La primera página de un laudo.", largura=UTIL * 0.6,
                 altura_max=12 * cm),
          secao("Ubicaciones de las fotos"),
          p("El Informe de Contenido trae la sección <b>Ubicaciones de las fotos (GPS grabado "
            "en las imágenes)</b>: una línea por foto que tenga coordenadas en el EXIF — los "
            "datos que la cámara graba dentro del archivo. Vale para JPEG de Android y HEIC de "
            "iPhone."),
          tabela_simples(["Columna", "Qué es"], [
              ["Fecha y hora", "La del <b>reloj del dispositivo</b> que fotografió."],
              ["Hora del GPS (UTC)", "La de los <b>satélites</b>, grabada junto con la "
               "coordenada. No depende del reloj del dispositivo: si estaba errado, esta es la "
               "referencia."],
              ["Latitud, longitud, altitud", "Dónde se tomó la foto, según el EXIF."],
              ["Cámara", "Fabricante y modelo grabados en el archivo."],
              ["Mapa", "Enlace <b>abrir en el mapa</b>, clicable en el PDF."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          itens([
              "Solo entran fotos que <b>coinciden con el sello</b>. Una foto alterada después "
              "de la adquisición se rechaza, con el motivo.",
              "Las fotografías que el examinador toma de la pieza (anverso y reverso) <b>no</b> "
              "entran: la mesa del examen no es un lugar donde estuvo el dispositivo.",
              "La misma foto copiada por dos módulos cuenta una sola vez.",
              "Una coordenada <b>0,0</b> — típica de una cámara sin señal de GPS — no se vuelve "
              "ubicación: va a los descartes, con el motivo.",
          ]),
          caixa("atencao", "La coordenada dice dónde se tomó la <b>foto</b>, no dónde estaba el "
                "dispositivo. El EXIF es editable, y una foto recibida de otra persona trae la "
                "ubicación del dispositivo de ella. Las aplicaciones de mensajería suelen "
                "borrar el EXIF: una foto sin GPS no prueba que el dispositivo no registre "
                "ubicación."),
          secao("PDF de conversaciones"),
          p("El botón <b>PDF de conversas selecionadas</b> (PDF de conversaciones "
            "seleccionadas) usa la adquisición marcada en la lista. El título de la ventana "
            "muestra el caso y la adquisición: si la lista viene vacía, verifique primero que "
            "sea la adquisición correcta."),
          secao("Examinar el material: pestaña Material"),
          p("La pestaña <b>Material</b> muestra las carpetas y archivos de la adquisición, con "
            "la vista previa (foto, texto, planilla, PDF, tablas de base de datos) y la "
            "<b>verificación del SHA-256 contra el sello</b>: coincide, DIVERGE o no consta. "
            "Todo solo de lectura."),
          figura("14_casos_material", "Pestaña Material."),
          caixa("dica", "Prefiera la pestaña Material al Explorador de Windows. Al navegar, el "
                "Explorador puede crear archivos ocultos (Thumbs.db, desktop.ini) dentro de la "
                "carpeta sellada, y la verificación pasa a acusar un archivo agregado."),
          secao("Entregar: Exportar para entrega"),
          passos([
              "En la pestaña Documentos, seleccione documentos — o, en la pestaña Material, "
              "archivos y carpetas (Ctrl y Shift para varios).",
              "Haga clic en <b>Exportar para entrega</b> (Exportar para entrega) o <b>Exportar "
              "selecionados</b> (Exportar seleccionados).",
              "Elija el destino (memoria USB, carpeta) y escriba la finalidad o el destinatario.",
              "La herramienta copia, verifica cada copia por el SHA-256 y genera el <b>recibo "
              "de entrega</b> (PDF y texto), con campos de firma. La entrega queda registrada en "
              "el caso.",
          ]),
          figura("16_entrega", "Exportar para entrega.", largura=UTIL * 0.8, altura_max=6 * cm),
          secao("Rectificar, adjuntar, eliminar"),
          itens([
              "<b>Retificar Dados do Caso</b> (Rectificar Datos del Caso) y <b>Anexar "
              "Autorização</b> (Adjuntar Autorización) entran como <b>complemento</b> del caso: "
              "el original se preserva y lo que cambió queda registrado.",
              "<b>Excluir caso</b> (Eliminar caso) pide que se escriba el nombre del caso, "
              "rechaza un caso con una adquisición aún sin sello y envía todo a la "
              "<b>Papelera de Windows</b> (restaurable). La eliminación queda en el registro de "
              "accesos.",
          ]),
          ]

    # =====================================================================
    h += capitulo(10, "Cadena de custodia e integridad",
                  "Cómo la herramienta prueba que el material no cambió desde la recolección.")
    h += [secao("El sello de cada adquisición"),
          p("Al final de la extracción, el archivo <b>manifesto_hashes.txt</b> recibe el "
            "SHA-256 de cada archivo adquirido. El hash del propio manifiesto aparece en el pie "
            "de cada página de los documentos. Alterar cualquier archivo, o el manifiesto, "
            "cambia ese número."),
          secao("Verificar la integridad"),
          p("En la barra lateral, <b>Cadeia de Custódia</b> (Cadena de Custodia) verifica una "
            "adquisición contra su manifiesto y graba el resultado de la verificación (ninguna "
            "verificación borra otra)."),
          figura("21_cadeia_custodia", "Verificación de integridad.", altura_max=9 * cm),
          secao("Dónde queda cada cosa"),
          tabela_simples(["Carpeta del caso", "Contenido"], [
              ["<b>&lt;plataforma&gt;_&lt;fecha&gt;_&lt;hora&gt;</b>", "La adquisición sellada. "
               "Nunca se reescribe."],
              ["<b>documentos</b>", "Informe de Extracción, Laudo, Conversaciones."],
              ["<b>relatorios</b>", "Informes de Contenido (CSV, HTML, PDF)."],
              ["<b>decifrados</b>", "Copias descifradas, con la procedencia."],
              ["<b>complementos</b>", "Rectificaciones, autorizaciones, descifrados, entregas."],
          ], [0.38, 0.62]),
          ]

    # =====================================================================
    h += capitulo(11, "Dispositivos probados y limitaciones",
                  "La herramienta dice lo que verificó y lo que no verificó — inclusive sobre "
                  "sí misma. Esta es la lista de los dispositivos en que se probó la versión "
                  "1.0, y de las limitaciones conocidas.")
    h += [secao("Dónde se probó la versión 1.0"),
          tabela_simples(["Dispositivo", "Sistema", "Qué se probó"], [
              ["Motorola moto x4", "Android 9", "Extracción completa, WhatsApp por la clave de "
               "64 dígitos, fotos con GPS"],
              ["Samsung Galaxy A22", "Android 13 (One UI 5.1)", "Extracción completa, aplicación "
               "agente, alerta de reloj desfasado"],
              ["Emulador Android", "Android 13, con privilegios elevados", "Módulos que exigen "
               "privilegios elevados, WhatsApp"],
              ["iPhone 11", "iOS 18.6.2", "Copia común y cifrada, descifrado, WhatsApp, fotos "
               "con GPS"],
              ["Memoria USB (7,28 GiB)", "Windows 11", "Los cuatro módulos, inclusive la imagen "
               "del volumen"],
          ], [0.24, 0.26, 0.5]),
          Spacer(1, 8),
          p("Otros modelos y versiones tienden a funcionar por el mismo camino, pero no fueron "
            "verificados. Cuando un módulo falla en un dispositivo, la herramienta registra el "
            "rechazo y no concluye nada sobre el contenido."),
          secao("Limitaciones conocidas"),
          itens([
              "<b>Xiaomi, Redmi y POCO (MIUI / HyperOS)</b>: la aplicación agente no se "
              "verificó. Esos dispositivos suelen exigir «Instalar vía USB» y una cuenta "
              "Xiaomi; la instalación puede ser rechazada. La limitación consta del propio "
              "módulo.",
              "<b>Android 8 o anterior</b>: fuera del alcance de esta versión. En un Galaxy J5 "
              "Prime con Android 7, el Volcado del Sistema de Archivos se detuvo temprano en la "
              "copia del almacenamiento interno y, aun así, indicó «Concluido»; WhatsApp "
              "Business en la ubicación antigua no se busca. En un dispositivo así, verifique la "
              "reconciliación de cada módulo o use otra herramienta.",
              "<b>Android 12 en adelante</b> ya no tiene la copia de seguridad del sistema: SMS "
              "y llamadas se leen directamente; cuando el sistema rechaza esa lectura, entran "
              "por la aplicación agente, que es de selección expresa.",
              "<b>IMEI</b>: de Android 10 en adelante, el sistema no lo entrega sin privilegios "
              "elevados. La herramienta registra cada vía intentada y declara que no lo obtuvo.",
              "<b>WhatsApp en Android</b>: solo se descifra la copia protegida por la clave de "
              "64 dígitos (crypt15). El módulo de downgrade de WhatsApp aún no se ha probado en "
              "un dispositivo real.",
              "<b>iPhone</b>: las fotos de la copia cifrada no se leen en esta versión (las de "
              "la copia común, sí). Con una contraseña de copia definida por el dueño, solo la "
              "copia común, descifrada con la contraseña de él.",
              "<b>Fuera del alcance</b>: desbloqueo de dispositivos, sorteo de contraseñas, "
              "extracción física de celular sin privilegios elevados y recuperación de datos "
              "borrados.",
          ]),
          ]

    # =====================================================================
    h += capitulo(12, "Problemas comunes",
                  "Qué hacer cuando algo no sale como se espera.")
    for titulo, texto in (
        ("El dispositivo aparece como «no autorizado»",
         "Desbloquee la pantalla y acepte <b>Permitir la depuración USB</b>. Si la pregunta no "
         "aparece, apague y encienda la depuración USB, o revoque las autorizaciones en las "
         "Opciones de desarrollador y conecte de nuevo."),
        ("Ningún dispositivo responde",
         "Cambie el cable (puede ser solo de carga), ponga el modo USB en «Transferencia de "
         "archivos» y verifique que la depuración USB esté activada."),
        ("El dispositivo rechazó la aplicación agente",
         "Vea si hay una confirmación en la pantalla del dispositivo (Play Protect). En "
         "Xiaomi, active «Instalar vía USB»."),
        ("La consola alerta de que el reloj del dispositivo está desfasado",
         "El dispositivo marcaba otra fecha y hora (es común en un dispositivo sin chip o sin "
         "internet). No corrija el reloj: el desvío medido queda registrado, y el Informe de "
         "Extracción y el laudo avisan de que las fechas grabadas por el dispositivo deben "
         "leerse con esa corrección."),
        ("Windows mostró «Windows protegió su PC»",
         "Es el aviso para un programa sin firma digital pagada. Verifique el hash del "
         "instalador, haga clic en <b>Más información</b> y en <b>Ejecutar de todas formas</b> "
         "(capítulo 2). Si no hay botón, el Control Inteligente de Aplicaciones está activado y "
         "exige firma digital: instale en otra computadora, pida al área de TI que autorice el "
         "programa, o ejecute desde el código fuente (capítulo 2)."),
        ("La herramienta no encuentra el iPhone",
         "Verifique que la aplicación Dispositivos Apple (o iTunes) esté instalada, "
         "<b>desconecte y conecte el cable de nuevo</b>, desbloquee la pantalla y toque en "
         "<b>Confiar</b>."),
        ("El iPhone rechazó la copia de seguridad (código 212)",
         "La configuración inicial del dispositivo no se concluyó. Termínela — la cuenta Apple "
         "puede saltarse — e intente de nuevo (capítulo 6)."),
        ("La copia del iPhone se detuvo a la mitad",
         "La pantalla se bloqueó o el cable se movió. Mantenga el iPhone desbloqueado (cuidado "
         "con el Modo de Bajo Consumo) y escriba el código siempre que lo pida."),
        ("La lista de conversaciones vino vacía",
         "Verifique, en el título de la ventana, que la adquisición sea la correcta. Si lo es, "
         "el Informe de Contenido dice por qué no hay conversación interpretada."),
        ("El informe dice que «el provider respondió y no devolvió ningún registro»",
         "El propio Android respondió a la consulta que esa fuente está vacía — por ejemplo, "
         "SMS en un dispositivo sin chip. No es una falla de lectura. Los registros borrados no "
         "aparecen por esta vía."),
        ("Un archivo aparece con «(nome alterado 1)» (nombre alterado 1)",
         "Windows no acepta el nombre que el archivo tiene en el dispositivo (dos nombres que "
         "solo difieren en mayúsculas, o un punto al final). El contenido es el mismo, "
         "verificado por el hash, y la correspondencia está en el informe de reconciliación."),
        ("WhatsApp muestra «Activado · Contraseña»",
         "La copia está protegida por contraseña, y la herramienta descifra solo con la clave "
         "de 64 dígitos. Desactive la protección y actívela de nuevo por la clave (capítulo 5, "
         "etapas 1 y 2)."),
        ("Los mensajes recientes de WhatsApp no aparecen",
         "La copia es anterior a ellos. Vea la «Nota de la fuente» en el informe y haga una "
         "copia nueva antes de extraer."),
        ("Olvidé la contraseña y el código",
         "Cree un perfil nuevo. Las adquisiciones antiguas siguen a su nombre."),
    ):
        h += [sub(titulo), p(texto)]

    # =====================================================================
    h += capitulo(13, "Glosario", "Términos usados en la herramienta y en este manual.")
    h += [tabela_simples(["Término", "Significado"], [
        ["ADB", "Android Debug Bridge, la herramienta de depuración de Android."],
        ["Adquisición", "Una extracción de un dispositivo, grabada en una carpeta sellada "
         "dentro del caso."],
        ["Caso", "El conjunto de adquisiciones de un mismo examen."],
        ["Complemento", "Información añadida al caso después, sin reescribir la adquisición."],
        ["Copia cifrada (iPhone)", "Copia de seguridad local protegida por contraseña; es la "
         "única en que iOS incluye el registro de llamadas."],
        ["crypt15", "Formato de la copia de seguridad cifrada de WhatsApp."],
        ["EXIF", "Datos que la cámara graba dentro de la foto: fecha, cámara y, a veces, GPS."],
        ["GPS (UTC)", "Hora de los satélites grabada junto con la coordenada; no depende del "
         "reloj del dispositivo."],
        ["DEFR / DES", "Primer respondedor y especialista, en la norma ISO/IEC 27037."],
        ["Hash (SHA-256)", "Huella digital de un archivo: cualquier alteración cambia el valor."],
        ["Sello (manifiesto)", "La lista de hashes de todos los archivos de la adquisición."],
        ["Selección expresa", "Módulo que altera el dispositivo y solo se ejecuta si se elige "
         "uno a uno."],
        ["Salvedad", "Lo que el módulo no alcanzó, declarado junto con lo que obtuvo."],
    ], [0.25, 0.75])]
    return h


def main() -> None:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    documento = Apostila(SAIDA)
    documento.multiBuild(conteudo())
    print(f"Manual generado: {SAIDA}")


if __name__ == "__main__":
    main()
