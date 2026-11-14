"""
Gera a Apostila do Usuário do Hexis Forensics, em PDF.

Usa a identidade visual dos documentos da suíte (`services.identidade_pdf`),
as capturas de `capturas/` (geradas por `capturas.py`) e as do celular em
`celular/` (tiradas do aparelho pelo ADB). As tabelas de módulos são lidas
do próprio código: a apostila não envelhece em relação à ferramenta.

Uso:
    py ferramentas/apostila/capturas.py      # refaz as telas
    py ferramentas/apostila/gerar_apostila.py
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
SAIDA = AQUI / "saida" / "Apostila_Hexis_Forensics.pdf"

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
                         title="Apostila do Usuário — Hexis Forensics",
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
    tela.drawString(MARGEM, ALTURA * 0.52, "Apostila do Usuário")
    tela.setFont(F["texto"], 15)
    tela.setFillColor(colors.HexColor("#8fb4e6"))
    tela.drawString(MARGEM, ALTURA * 0.52 - 30,
                    "Extração e preservação de evidência digital, passo a passo")
    tela.setFillColor(VERDE)
    tela.rect(MARGEM, ALTURA * 0.52 - 52, 3.2 * cm, 4, stroke=0, fill=1)
    tela.setFillColor(colors.HexColor("#c8d6e6"))
    tela.setFont(F["texto"], 10.5)
    tela.drawString(MARGEM, 3.4 * cm, identificacao_ferramenta())
    tela.drawString(MARGEM, 2.8 * cm, f"Edição de {date.today():%d/%m/%Y}")
    tela.drawString(MARGEM, 2.2 * cm, "Orientada pela ABNT NBR ISO/IEC 27037")
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
    tela.drawRightString(LARGURA - MARGEM, topo - 0.45 * cm, "APOSTILA DO USUÁRIO")
    tela.setStrokeColor(AZUL)
    tela.setLineWidth(1.2)
    tela.line(MARGEM, topo - 0.95 * cm, LARGURA - MARGEM, topo - 0.95 * cm)
    tela.setStrokeColor(VERDE)
    tela.line(MARGEM, topo - 0.95 * cm, MARGEM + 2.2 * cm, topo - 0.95 * cm)
    tela.setFillColor(identidade.CINZA_TEXTO)
    tela.setFont(F["texto"], 7.5)
    tela.drawString(MARGEM, 1.1 * cm, f"Apostila do Usuário — {identificacao_ferramenta()}")
    tela.drawRightString(LARGURA - MARGEM, 1.1 * cm, f"página {doc.page}")
    tela.restoreState()


# ---------------------------------------------------------------------------
# Peças de conteúdo
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
    # O sumário só enxerga o que é posto na página; a faixa é que é posta.
    faixa._nivel_sumario = 0
    faixa._texto_sumario = f"{numero}. {titulo}"
    return [PageBreak(), faixa, Spacer(1, 10), Paragraph(abertura, CORPO), Spacer(1, 4)]


def secao(titulo: str):
    """Título de seção que nunca fica sozinho no pé da página."""
    # Salta de página se faltar espaço para o título E o começo do que ele anuncia.
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
    cores = {"atencao": ("#fdecea", "#b3261e", "Atenção"),
             "dica": ("#e8f8f4", "#19c3a6", "Dica"),
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
        reserva = Table([[Paragraph(f"<i>[captura pendente: {nome}]</i>", LEGENDA)]],
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
    """Duas telas de celular lado a lado, cada uma com a sua legenda."""
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
            moldura = Paragraph(f"<i>[captura pendente: {nome}]</i>", LEGENDA)
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
        altera = "sim — " + classe.alteracoes_no_dispositivo[0][0] if classe.alteracoes_no_dispositivo \
            else "não"
        exige = []
        if classe.requer_privilegio_root:
            exige.append(classe.rotulo_privilegio)
        if classe.selecao_expressa:
            exige.append("seleção expressa (começa desmarcado)")
        exige.append(f"perfil {classe.perfil_minimo.name}")
        linhas.append([f"<b>{identidade.escapar(classe.nome_exibicao)}</b>",
                       identidade.escapar(classe.descricao),
                       identidade.escapar(altera), identidade.escapar("; ".join(exige))])
    return tabela_simples(["Módulo", "O que faz", "Altera o aparelho?", "Exige"], linhas,
                          [0.22, 0.42, 0.2, 0.16])


# ---------------------------------------------------------------------------
# Conteúdo
# ---------------------------------------------------------------------------
def conteudo() -> list:
    h = []

    # --- Sumário
    h += [NextPageTemplate("conteudo"), PageBreak()]
    sumario = TableOfContents()
    sumario.levelStyles = [SUMARIO_1, SUMARIO_2]
    h += [Paragraph("Sumário", H1), Spacer(1, 10), sumario]

    # --- Aviso legal (antes do capítulo 1). Não entra no sumário.
    h += [PageBreak(),
          Paragraph("Aviso — tratamento de dados pessoais", H2),
          caixa("atencao",
                "Extrair e examinar dados de um aparelho é <b>tratamento de dados pessoais</b>. "
                "Use a ferramenta só com <b>base legal</b> (ordem judicial, requisição de "
                "autoridade competente ou consentimento documentado do titular) e conforme as "
                "normas aplicáveis: CF e CPP na investigação penal, LGPD nas demais perícias e, "
                "fora do Brasil, a lei local. Colete só o necessário e guarde com segurança. A "
                "legalidade do exame é responsabilidade de quem o executa e de quem o autoriza."),
          ]

    # =====================================================================
    h += capitulo(1, "Apresentação",
                  "O Hexis Forensics é uma ferramenta gratuita de extração e preservação "
                  "de evidência digital para celulares Android, iPhone e mídias de "
                  "armazenamento. Foi feita para o procedimento de rotina: coletar o que "
                  "responde ao exame, registrar como cada dado foi obtido e entregar "
                  "documentos que se sustentam sozinhos.")
    h += [secao("Por que esta ferramenta existe"),
          p("Boa parte dos exames em celulares e mídias é de rotina e não precisa de "
            "recursos avançados. Mesmo assim, quem faz esse trabalho costuma esbarrar em "
            "dois caminhos ruins."),
          sub("As ferramentas pagas são caras para a rotina"),
          itens([
              "<b>Licença cara.</b> Licenças anuais, por estação e cotadas em dólar "
              "inviabilizam o uso em menor escala.",
              "<b>Capacidade ociosa.</b> Paga-se por recursos avançados que os casos "
              "simples e recorrentes não usam.",
              "<b>Formação cara.</b> A formação certificada é cara, quando a maioria dos "
              "casos pede formação elementar e sólida.",
              "<b>Deslocamento do aparelho.</b> A evidência viaja até onde há ferramenta: "
              "mais etapas na cadeia de custódia e mais risco aos dados voláteis.",
          ]),
          sub("As ferramentas livres são gratuitas, mas não simples"),
          itens([
              "<b>Complexas de operar.</b> Linha de comando, ambiente técnico e pouca "
              "documentação: pouco amigáveis para o usuário comum de TI.",
              "<b>Sem documentação pericial.</b> Em geral, não geram cadeia de custódia "
              "nem laudo: o examinador monta tudo à parte.",
          ]),
          p("Na prática, a ferramenta livre é barata para baixar e cara para aprender: a "
            "complexidade de operação vira complexidade e custo de formação."),
          caixa("nota", "O que faltava: uma ferramenta simples, documentada e sem custo de "
                "licença para a aquisição de rotina."),

          secao("A proposta"),
          p("Aquisição lógica de rotina, simples de operar, com cadeia de custódia, lacre "
            "por hash e documentos. Cada dor tem uma resposta:"),
          tabela_simples(["Dor", "Resposta"], [
              ["<b>Licença cara</b>", "Sem custo de licença."],
              ["<b>Capacidade ociosa</b>", "Foco no que a rotina pede: Android, iPhone e mídias."],
              ["<b>Formação cara</b>", "Operação guiada, tela a tela, ao alcance de formação "
               "elementar e sólida."],
              ["<b>Deslocamento do aparelho</b>", "Windows 10 ou 11 e um cabo USB, onde o "
               "aparelho estiver."],
              ["<b>Complexidade das livres</b>", "Interface gráfica, sem linha de comando."],
              ["<b>Sem documentação pericial</b>", "Cadeia de custódia, lacre por hash e "
               "laudo já incluídos."],
          ], [0.32, 0.68]),

          secao("O que ela faz e até onde vai"),
          p("O alcance de cada coleta depende da plataforma e do tipo de extração. O quadro "
            "resume o que a versão 1.0 faz:"),
          tabela_simples(["Plataforma", "Lógica", "Sistema de arquivos", "Física (bit a bit)"], [
              ["<b>Android</b>", "Faz. Em aparelho comum, sem privilégio elevado.",
               "Parcial. Sem root, só o armazenamento compartilhado: os bancos dos "
               "aplicativos não vêm.",
               "Só com root. Partição de dados, perfil DES. Sem root, falha de forma explícita."],
              ["<b>iPhone</b>", "Faz. Backup comum e cifrado.", "Não faz. Exigiria jailbreak.",
               "Não faz. Exigiria exploração da inicialização do aparelho."],
              ["<b>Pendrives e discos</b>", "Faz. Cópia das pastas do usuário e índice com hash.",
               "Parcial. Índice da unidade inteira (caminho, datas e SHA-256), sem copiar o "
               "conteúdo; a cópia alcança só as pastas do usuário.",
               "Faz. Imagem .img do volume; exige Administrador e perfil DES."],
          ], [0.16, 0.26, 0.33, 0.25]),
          Spacer(1, 6),
          p("<b>Foco: aquisição lógica de rotina.</b> Sistema de arquivos completo e imagem "
            "física só com privilégio elevado, nunca no iPhone, e declarados como tal."),

          secao("Como funciona, em cinco passos"),
          passos([
              "<b>Conectar.</b> Android pela depuração USB, iPhone pareado, mídia com "
              "bloqueador de escrita.",
              "<b>Declarar o método.</b> A tela Método e limitações diz o que a coleta não alcança.",
              "<b>Identificar a peça.</b> Caso, autorização, marca e modelo, lacre e duas fotografias.",
              "<b>Extrair com hash.</b> Manifesto com o SHA-256 de cada arquivo: o lacre da aquisição.",
              "<b>Gerar os documentos.</b> Relatórios, conversas selecionadas e laudo.",
          ]),

          secao("Os documentos que ela gera"),
          p("Cada aquisição gera documentos que se sustentam sozinhos:"),
          itens([
              "<b>Relatório de Extração.</b> Linha do tempo do procedimento, ambiente, "
              "módulos, desfecho e manifesto de hashes.",
              "<b>Relatório de Conteúdo.</b> Mensagens, chamadas e contatos interpretados, "
              "com a origem de cada linha.",
              "<b>Conversas selecionadas.</b> Em PDF, só as conversas relevantes, completas.",
              "<b>Laudo Pericial.</b> O documento final, assinado pelo examinador da sessão.",
          ]),
          p("Todos são gravados <b>fora</b> da aquisição lacrada, que nunca é alterada "
            "(capítulo 9)."),

          secao("O diferencial: não coletado não é não existe"),
          p("Cada módulo termina em um de três estados:"),
          tabela_simples(["Estado", "O que significa"], [
              ["<b>Concluído</b>", "O módulo obteve o que se propunha."],
              ["<b>Concluído com ressalva</b>", "Obteve parte e declarou o que não alcançou."],
              ["<b>Não obteve dado</b>", "Nada daquele material foi adquirido, o que não "
               "significa que o dado não exista no aparelho."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          p("Na prática:"),
          itens([
              "<b>Consulta recusada pelo sistema:</b> a recusa é preservada e declarada; "
              "resposta vazia é registrada como tal.",
              "<b>Backup cifrado não decifrado:</b> “nada se afirma” sobre o conteúdo.",
              "<b>Aparelho bloqueado:</b> o laudo diz por que não extraiu.",
          ]),
          p("<b>Por que importa:</b> a ausência de um dado no material nunca é apresentada "
            "como ausência do dado no aparelho."),

          secao("Os princípios da ferramenta"),
          p("Três ideias orientam cada tela e cada documento. Conhecê-las ajuda a ler o "
            "que a ferramenta diz — e o que ela, de propósito, não diz."),
          itens([
              "<b>O necessário, bem registrado.</b> A ferramenta não mede qualidade pelo "
              "volume. Ela coleta o que interessa ao exame e documenta a procedência de cada "
              "dado: de que arquivo veio, por qual via, com qual hash.",
              "<b>Nunca afirmar o que não foi verificado.</b> Quando um dado não é obtido, o "
              "documento diz POR QUÊ — o sistema recusou, o módulo não foi executado, o "
              "backup não continha. Ausência de dado no material nunca é apresentada como "
              "ausência de dado no aparelho.",
              "<b>Toda alteração no aparelho é registrada e justificada.</b> Os módulos que "
              "mexem no dispositivo são marcados, começam desmarcados e deixam no registro "
              "do procedimento o que foi feito e por quê.",
          ]),
          secao("O que a ferramenta não faz"),
          p("Ser honesto sobre o alcance é parte do método. A ferramenta <b>não</b> "
            "desbloqueia aparelho, não contorna senha, não recupera dado apagado, não "
            "extrai da nuvem, não faz extração física de iPhone e, no Android, só faz "
            "extração física com root. Também não decodifica todos os aplicativos "
            "existentes. Para esses casos existem ferramentas especializadas. O Hexis "
            "Forensics cobre a aquisição lógica de rotina — e o que cerca a extração: cadeia "
            "de custódia, lacre por hash, laudo, exame sem extração e entrega documentada."),
          secao("Os papéis DEFR e DES"),
          p("A norma ABNT NBR ISO/IEC 27037 distingue o <b>DEFR</b> (primeiro respondedor: "
            "identifica, coleta e preserva seguindo procedimento) do <b>DES</b> (especialista: "
            "decide diante do que foge do procedimento). Cada módulo declara o perfil mínimo "
            "que exige. A ferramenta não impede ninguém — ela informa, e o laudo registra."),
          secao("Conformidade e transparência"),
          sub("Conformidade"),
          itens([
              "<b>ABNT NBR ISO/IEC 27037.</b> Identificação, coleta, aquisição e preservação.",
              "<b>Cadeia de custódia (CPP, arts. 158-A a 158-F).</b> Lacre, fotografias e "
              "registro de cada etapa.",
          ]),
          sub("Transparência"),
          itens([
              "<b>Instalador com hash publicado.</b> O SHA-256 permite conferir o arquivo "
              "antes de instalar (capítulo 2).",
              "<b>Testada em aparelhos reais.</b> Motorola, Samsung, iPhone 11 e pendrive, "
              "com o que foi provado em cada um (capítulo 11).",
              "<b>Limitações declaradas.</b> Por exemplo: agente não verificado em Xiaomi; "
              "IMEI não entregue sem root a partir do Android 10.",
          ]),
          secao("Para ir além: o Treinamento Oficial"),
          p("Esta apostila ensina a operar a ferramenta. O <b>Treinamento Oficial Hexis "
            "Forensics</b> vai além: ensina a computação forense que sustenta cada tela — "
            "cadeia de custódia, integridade por hash, os limites de cada tipo de extração e "
            "a redação do laudo. Há também oferta em parceria com instituições de ensino "
            "superior e implantação com treinamento de equipes para polícias e órgãos de "
            "perícia."),
          ]

    # =====================================================================
    h += capitulo(2, "Instalação e primeiro acesso",
                  "Do instalador à primeira sessão: requisitos, criação do seu perfil de "
                  "examinador e o código de recuperação, que é o único jeito de voltar se "
                  "a senha for esquecida.")
    h += [secao("Requisitos"),
          itens([
              "Computador com <b>Windows 10 ou 11</b>.",
              "<b>Cabo USB de dados</b> (alguns cabos só carregam e não servem).",
              "Para <b>iPhone</b>: o aplicativo <b>Dispositivos Apple</b> (Microsoft Store) "
              "ou o iTunes, que instalam o serviço de comunicação com o aparelho.",
              "Para <b>discos de computador</b>: dock ou adaptador USB e um "
              "<b>bloqueador de escrita</b> de hardware (ver capítulo 8).",
          ]),
          secao("Conferir o instalador antes de instalar"),
          p("Junto do instalador é publicado o seu <b>hash SHA-256</b> — a impressão digital "
            "do arquivo. Conferi-lo garante que o arquivo baixado é exatamente o publicado, "
            "sem corrupção nem adulteração. É a mesma lógica do lacre das aquisições."),
          passos([
              "Na pasta onde está o instalador, clique com o botão direito num espaço vazio e "
              "escolha <b>Abrir no Terminal</b>.",
              "Digite <b>Get-FileHash .\\HexisForensics-Setup-1.0.0.exe</b> e tecle Enter.",
              "Compare o valor da coluna <b>Hash</b> com o publicado. Um único caractere "
              "diferente significa arquivo diferente: não instale.",
          ]),
          secao("Instalação"),
          p("Execute o instalador e siga as telas. Marque a opção <b>Criar atalho na Área de "
            "Trabalho</b>. Os casos ficam na pasta <b>HexisForensics-Casos</b>, dentro da "
            "pasta do seu usuário do Windows — fora da pasta do programa, para que uma "
            "atualização nunca alcance a evidência. Para atualizar, basta instalar a versão "
            "nova por cima: casos e examinadores são preservados."),
          sub("O aviso azul do Windows"),
          p("O instalador é gratuito e não tem assinatura digital paga. Por isso, na primeira "
            "execução, o Windows mostra a tela <b>“O Windows protegeu o computador”</b>, com "
            "editor desconhecido. É um aviso, não um diagnóstico de vírus:"),
          passos([
              "Clique em <b>Mais informações</b>.",
              "Confira o nome do arquivo e clique em <b>Executar assim mesmo</b>.",
          ]),
          caixa("nota", "Se o <b>Controle Inteligente de Aplicativos</b> do Windows 11 "
                "estiver ligado, ele bloqueia o instalador sem oferecer o botão: exige "
                "assinatura digital, que esta versão não tem. Não há versão portátil. As "
                "saídas são instalar em outro computador, pedir ao setor de TI que libere o "
                "programa, ou <b>rodar do código-fonte</b> (seção a seguir)."),
          secao("Alternativa: rodar do código-fonte"),
          p("Quando o instalador é bloqueado e não há como liberá-lo, a ferramenta roda "
            "direto do código-fonte, como qualquer projeto de código aberto — não há "
            "instalação, a mesma suíte é executada pelo Python. Exige alguns passos a mais, "
            "mas não depende de assinatura digital."),
          passos([
              "Instale o <b>Python 3.13</b> de <b>python.org</b> (em Downloads, escolha o "
              "instalador do Windows da versão <b>3.13</b>). <b>Não use o 3.14</b>: uma das "
              "bibliotecas do iPhone ainda não tem versão pronta para ele. Na primeira tela "
              "do instalador do Python, marque <b>Add python.exe to PATH</b>.",
              "Baixe o código pela <b>página de versões (Releases)</b> do projeto: "
              "<b>github.com/HexisForensics/HexisForensics/releases</b>. Na versão mais "
              "recente, baixe o <b>Fonte (ZIP)</b>. <b>Não</b> use o <b>Code → Download ZIP</b> "
              "da página principal — aquele traz a versão em desenvolvimento, sem versão "
              "marcada.",
              "<b>Confira o hash do ZIP</b>, como no instalador: na pasta do arquivo, "
              "<b>Abrir no Terminal</b> e "
              "<b>Get-FileHash .\\HexisForensics-1.0.0-fonte.zip</b>. O valor tem de ser "
              "idêntico ao publicado na Release.",
              "Extraia a pasta. Abra-a, clique com o botão direito num espaço vazio e escolha "
              "<b>Abrir no Terminal</b>.",
              "Digite <b>py -m pip install -r requirements.txt</b> e tecle Enter. Aguarde a "
              "instalação das bibliotecas (demora na primeira vez).",
              "Digite <b>py main.py</b> e tecle Enter. A ferramenta abre na tela de entrada, "
              "igual à versão instalada.",
          ]),
          caixa("nota", "Rodando do código-fonte, os casos ficam em <b>HexisForensics-Casos</b>, "
                "na sua pasta de usuário do Windows — a mesma da versão instalada, e <b>fora</b> "
                "da pasta do programa, para que atualizar (baixar o ZIP novo) nunca alcance as "
                "aquisições. O <b>adb.exe</b> já vem no ZIP, então a extração de Android "
                "funciona sem passo extra; para o iPhone, continua valendo o aplicativo "
                "Dispositivos Apple (Requisitos)."),
          secao("Primeiro acesso: o seu perfil de examinador"),
          p("A ferramenta abre na <b>tela de entrada</b>. Cada examinador tem perfil e senha "
            "próprios: é isso que identifica quem fez cada extração e quem assina cada laudo."),
          figura("01_entrada", "Tela de entrada: escolha o seu nome e digite a sua senha.",
                 altura_max=9 * cm),
          passos([
              "Na primeira vez, clique em <b>Novo examinador</b>.",
              "Preencha o <b>nome</b> como deve constar nos documentos, o <b>registro "
              "profissional</b> e a <b>instituição ou laboratório</b>.",
              "Crie uma <b>senha</b> de pelo menos 6 caracteres e repita-a.",
              "Clique em <b>Cadastrar e entrar</b>.",
              "Anote ou imprima o <b>código de recuperação</b> (próxima seção), marque a "
              "confirmação e clique em <b>Continuar</b>.",
          ]),
          figura("02_novo_examinador", "Cadastro de um novo examinador.", altura_max=9 * cm),
          secao("O código de recuperação"),
          p("Ao criar a senha, a ferramenta mostra um código de 16 caracteres, em quatro "
            "grupos. Ele aparece <b>uma única vez</b>. É o único jeito de entrar se você "
            "esquecer a senha: ninguém — nem o fabricante — consegue redefini-la. Usado, o "
            "código é trocado por outro, que também aparece uma vez."),
          figura("03_codigo_recuperacao", "O código de recuperação, com as opções de imprimir e "
                 "copiar.", altura_max=9 * cm),
          caixa("atencao", "Guarde o código longe do computador: impresso numa pasta, num "
                "cofre de senhas, num envelope lacrado. Quem perde a senha <b>e</b> o código "
                "precisa criar um perfil novo. As aquisições antigas continuam no nome dele, "
                "porque o nome está gravado dentro do lacre de cada uma."),
          secao("Esqueci minha senha"),
          passos(["Na tela de entrada, escolha o seu nome e clique em <b>Esqueci minha "
                  "senha</b>.",
                  "Digite o código de recuperação (com ou sem traços, maiúsculas ou minúsculas).",
                  "Escolha a nova senha e clique em <b>Redefinir e entrar</b>.",
                  "Anote o <b>novo</b> código que aparece: o antigo deixou de valer."]),
          secao("Durante a sessão"),
          itens([
              "O seu nome aparece no <b>rodapé da barra lateral</b>, com a hora de entrada.",
              "<b>Trocar examinador</b> devolve à tela de entrada, para outra pessoa entrar. "
              "Não é possível trocar durante uma extração.",
              "Depois de <b>15 minutos sem uso</b>, a tela é bloqueada e pede a senha de novo. "
              "Uma extração em andamento <b>continua rodando</b> por trás.",
              "Cinco senhas erradas seguidas travam aquele examinador por 10 minutos.",
              "Em <b>Examinadores</b> (barra lateral) você corrige os seus dados, troca a "
              "senha, gera um código de recuperação novo ou exclui o seu perfil. O botão "
              "<b>Novo examinador</b> abre o cadastro de outra pessoa: ela mesma cria a "
              "senha e recebe o código dela, e passa a ser o examinador da sessão. Ninguém "
              "vê nem altera os dados de outro examinador.",
              "Entradas, bloqueios, recuperações e exclusões ficam no <b>registro de "
              "acessos</b> da estação.",
          ]),
          caixa("nota", "O registro de cada aquisição diz: “sessão aberta com a senha do "
                "examinador nesta estação”. A senha garante a <b>autoria</b> — ninguém opera "
                "em nome de outro por descuido. Ela não prova identidade (senha emprestada "
                "também entra) e não protege os arquivos do caso, que ficam no disco."),
          ]

    # =====================================================================
    h += capitulo(3, "Preparando o celular Android",
                  "Sem privilégio elevado, a extração de Android é feita pelo ADB, a "
                  "ferramenta de depuração do próprio Android. Para isso, o aparelho precisa "
                  "autorizar o computador.")
    h += [secao("Etapa 1 — Ativar as Opções do desenvolvedor"),
          passos([
              "Abra <b>Configurações → Sobre o telefone</b> (no Motorola, <b>Configurações → "
              "Sistema → Sobre o dispositivo</b>; em outros: “Informações do software”).",
              "Role até o fim e toque <b>7 vezes</b> em <b>Número da versão</b> (em alguns "
              "aparelhos: “Versão do MIUI”, “Versão do SO” ou “Número de compilação”). O "
              "aparelho pode pedir o código de desbloqueio.",
              "Aparece a mensagem <b>“Você agora é um desenvolvedor”</b> — ou, se já estava "
              "ativo, “Você já é um desenvolvedor”.",
          ]),
          par_de_figuras("android_02_numero_versao", "Número da versão: toque 7 vezes. "
                         "(IMEI e endereços cobertos nesta apostila.)",
                         "android_03_desenvolvedor", "A confirmação do modo desenvolvedor."),
          secao("Etapa 2 — Ligar a depuração USB"),
          passos([
              "Abra <b>Configurações → Sistema → Avançado → Opções do desenvolvedor</b> (em "
              "alguns aparelhos, em “Configurações adicionais”).",
              "Ligue <b>Depuração USB</b>.",
              "Ligue também <b>Permanecer ativo</b>: a tela não apaga enquanto o aparelho está "
              "no cabo, e a conexão não cai no meio da extração.",
          ]),
          par_de_figuras("android_04_depuracao_usb", "Depuração USB ligada.",
                         "android_05_permanecer_ativo", "Permanecer ativo ligado."),
          secao("Etapa 3 — Autorizar o computador"),
          passos([
              "Conecte o cabo de dados. Na tela do aparelho aparece <b>Permitir depuração "
              "USB?</b>.",
              "Marque <b>Sempre permitir a partir deste computador</b>.",
              "Toque em <b>Permitir</b>.",
              "Na ferramenta, página <b>Android</b>, clique em <b>Verificar Conexão</b>. O "
              "status deve dizer que o aparelho está conectado e autorizado.",
          ]),
          par_de_figuras("android_06_permitir_depuracao", "O aviso de autorização "
                         "(reprodução: o Android não permite capturar esta tela).",
                         "android_07_modo_usb", "Preferências de USB, se a conexão cair."),
          caixa("dica", "Se o aviso não aparecer, ou o aparelho constar como <b>não "
                "autorizado</b>: desbloqueie a tela, toque em <b>Revogar autorizações de "
                "depuração USB</b> (nas Opções do desenvolvedor) e reconecte o cabo. Se a "
                "conexão cair durante a extração, abra <b>Configurações → Dispositivos "
                "conectados → USB</b> e escolha <b>Transferência de arquivo</b>."),
          figura("04_janela_android", "Página Android: status do aparelho, módulos de extração "
                 "e console."),
          secao("Particularidades por fabricante"),
          sub("Xiaomi (MIUI / HyperOS)"),
          p("Além da depuração USB, ligue <b>Instalar via USB</b> e <b>Depuração USB "
            "(configurações de segurança)</b>. As duas exigem uma <b>conta Xiaomi</b> logada "
            "e, às vezes, um chip inserido. Sem elas, o aparelho recusa o aplicativo agente. "
            "<i>Nesta versão, o agente ainda não foi verificado em aparelho Xiaomi: se a "
            "instalação for recusada, a ferramenta registra a recusa e não conclui nada sobre "
            "o conteúdo.</i>"),
          sub("Samsung"),
          p("As <b>Opções do desenvolvedor</b> aparecem no fim da lista de Configurações, logo "
            "abaixo de <b>Sobre o telefone</b>, depois dos 7 toques em <b>Informações do "
            "software → Número de compilação</b>."),
          p("Verificado num <b>Galaxy A22 com Android 13 (One UI 5.1)</b>, de fábrica e sem "
            "privilégio elevado: o aplicativo agente foi instalado, coletou e foi removido "
            "<b>sem nenhuma confirmação na tela</b> — nem “Instalar app?”, nem Play Protect, "
            "nem pedido de permissão. A Samsung também entrega a agenda de contatos ao módulo "
            "comum, sem o agente."),
          p("Em outros modelos ou versões, o <b>Play Protect</b> pode perguntar se o aplicativo "
            "é seguro. Se a pergunta aparecer, confirme a instalação na tela do aparelho."),
          caixa("atencao", "Ativar a depuração USB e autorizar o computador são alterações "
                "de configuração do aparelho. A ferramenta as registra no procedimento como "
                "imposição do método: sem elas não existe aquisição lógica em aparelho sem "
                "privilégio elevado."),
          ]

    # =====================================================================
    h += capitulo(4, "Extração Android, passo a passo",
                  "Do clique em Iniciar Extração ao lacre da aquisição. Cada etapa existe "
                  "para registrar algo que o laudo vai precisar.")
    h += [secao("Escolher os módulos"),
          p("A lista de módulos aparece na página Android. Os módulos comuns já vêm "
            "marcados. Os que alteram o aparelho de forma relevante são de <b>seleção "
            "expressa</b>: começam desmarcados e o botão <b>Marcar todos</b> não os alcança — "
            "precisam ser escolhidos um a um, de propósito."),
          secao("A sequência de telas"),
          passos([
              "Clique em <b>Iniciar Extração</b>. A ferramenta pede a confirmação do "
              "examinador da sessão (“Esta extração será registrada como feita por…”).",
              "<b>Método e limitações</b>: o que a coleta escolhida não vai alcançar e o que "
              "pode ser alterado no aparelho. É o momento de decidir — depois vira registro. "
              "Leia e clique em <b>Ciente — Prosseguir</b>.",
              "<b>Caso</b>: crie um caso novo ou escolha um existente. Um caso reúne vários "
              "aparelhos; cada aparelho vira uma aquisição dentro dele.",
              "<b>Autorização</b>: anexe o documento que autoriza o acesso aos dados. "
              "Prosseguir sem anexar é permitido, mas fica registrado que não havia "
              "documento à vista.",
              "<b>Dispositivo e cadeia de custódia</b>: marca e modelo, cor, estado, "
              "<b>número do lacre</b> (obrigatório) e pelo menos <b>duas fotografias</b> da "
              "peça (frente e verso).",
              "A extração começa. Acompanhe pelo console e pela coluna de status de cada "
              "módulo.",
          ]),
          figura("07_metodo", "Método e limitações: o que a coleta não alcança, antes de "
                 "começar.", altura_max=10 * cm),
          figura("08_caso", "Caso novo ou existente.", altura_max=8 * cm),
          figura("10_dispositivo", "Peça, lacre e fotografias.", largura=UTIL * 0.6,
                 altura_max=10 * cm),
          secao("Como ler o resultado"),
          p("Cada módulo termina em um de três estados, e eles não são intercambiáveis:"),
          tabela_simples(["Estado", "Significa"], [
              ["<b>Concluído</b>", "O módulo obteve o que se propunha."],
              ["<b>Concluído com ressalva</b>", "Obteve parte, e declarou o que não alcançou "
               "(por exemplo, uma consulta recusada pelo sistema)."],
              ["<b>Não obteve dado</b>", "Nada daquele material foi adquirido. Isso <b>não</b> "
               "significa que o dado não exista no aparelho."],
          ], [0.28, 0.72]),
          Spacer(1, 8),
          p("Ao fim, a ferramenta gera o <b>manifesto de hashes</b> (o lacre da aquisição): o "
            "SHA-256 de cada arquivo adquirido. Ela também confere se o aparelho conectado ao "
            "final é o mesmo do início."),
          caixa("atencao", "Não feche a ferramenta durante uma extração: a aquisição ficaria "
                "sem lacre. Se precisar parar, use <b>Cancelar</b> e aguarde a mensagem de "
                "extração finalizada."),
          secao("Os módulos disponíveis"),
          p("A tabela abaixo é gerada do próprio código da ferramenta."),
          tabela_de_modulos("Android"),
          ]

    # =====================================================================
    h += capitulo(5, "WhatsApp, passo a passo",
                  "Sem privilégio elevado, o banco de mensagens do WhatsApp fica em área "
                  "privada do aplicativo, inacessível. O caminho é o próprio backup local do "
                  "WhatsApp, protegido com uma chave de 64 dígitos que o examinador conhece. "
                  "As telas deste capítulo são de um aparelho real; a chave aparece coberta.")
    h += [secao("Por que este é o caminho"),
          p("O WhatsApp grava backups locais cifrados (<b>msgstore.db.crypt15</b>) numa pasta "
            "que a ferramenta consegue copiar. Quando o backup é protegido por uma <b>chave de "
            "64 dígitos</b> — e não por senha ou por chave de acesso —, quem tem a chave "
            "consegue decifrá-lo. A ferramenta decifra, confere a autenticidade do conteúdo e "
            "lê as conversas."),
          caixa("atencao", "Mexer na proteção do backup e mandar o WhatsApp fazer o backup são "
                "<b>alterações no aparelho examinado</b>, feitas pelo examinador. Ao decifrar, "
                "a ferramenta as registra no complemento do caso, junto com a chave."),
          secao("Etapa 1 — Ver como o backup está protegido"),
          p("No WhatsApp, abra <b>Configurações → Conversas → Backup de conversas</b> e role "
            "até <b>Backup criptografado de ponta a ponta</b>. O que está escrito embaixo dele "
            "decide o caminho:"),
          tabela_simples(["O que aparece", "O que fazer"], [
              ["<b>Desativado</b>", "Vá para a Etapa 2."],
              ["<b>Ativado · Senha</b> ou <b>Ativado · Chave de acesso</b>",
               "Não serve: a ferramenta decifra só com a chave de 64 dígitos. Toque na "
               "opção, em <b>Desativar</b>, informe a senha do backup e confirme. Depois, "
               "Etapa 2."],
              ["<b>Ativado · Chave de 64 dígitos</b> (em algumas versões, em inglês: "
               "<b>On · 64-digit key</b>)",
               "Serve, se alguém tiver a chave anotada. O WhatsApp só mostra a chave na "
               "criação: sem ela anotada, desative e crie uma nova (Etapa 2)."],
          ], [0.4, 0.6]),
          Spacer(1, 6),
          par_de_figuras("whatsapp_02_criptografado", "Ativado · Senha: não serve.",
                         "whatsapp_03_tela_criptografia", "Backup protegido com senha: "
                         "toque em Desativar."),
          par_de_figuras("whatsapp_04_desativado", "Confirme a desativação.",
                         "whatsapp_05_apos_desativar", "Agora: Desativado."),
          secao("Etapa 2 — Ativar com a chave de 64 dígitos"),
          passos([
              "Toque em <b>Backup criptografado de ponta a ponta</b>.",
              "<b>NÃO toque no botão verde “Usar chave de acesso”.</b> Toque em <b>Mais "
              "opções</b>.",
              "Escolha <b>Chave de criptografia de 64 dígitos</b> (e não “Senha”).",
              "Toque em <b>Gerar chave de 64 dígitos</b>.",
              "A chave aparece: 16 grupos de 4 caracteres. <b>Anote-a</b> — ou leia-a pelo "
              "cabo (ver dica). Toque em <b>Continuar</b>.",
              "O WhatsApp mostra a chave de novo para conferência. Toque em <b>Anotei minha "
              "chave de 64 dígitos</b>.",
              "Toque em <b>Criar</b>. O processo termina em segundo plano.",
          ]),
          par_de_figuras("whatsapp_06_ativar", "A armadilha: o botão verde não serve. "
                         "Toque em Mais opções.",
                         "whatsapp_07_mais_opcoes", "Escolha a chave de 64 dígitos."),
          par_de_figuras("whatsapp_08_gerar_chave", "Gerar a chave.",
                         "whatsapp_09_chave", "A chave (coberta nesta apostila)."),
          par_de_figuras("whatsapp_10_confirmar_chave", "Conferir e confirmar que anotou.",
                         "whatsapp_11_criar", "Criar o backup protegido."),
          caixa("dica", "Com o cabo conectado, a chave pode ser lida da tela pelo ADB, sem "
                "erro de digitação: o texto da tela é obtido por <b>uiautomator dump</b>. Na "
                "dúvida, fotografe a tela da chave e junte a foto ao caso."),
          secao("Etapa 3 — Gravar o backup NO APARELHO"),
          passos([
              "Em <b>Backup de conversas</b>, confira que <b>Conta do Google</b> está em "
              "<b>Nenhuma</b> e <b>Backup automático</b> em <b>Desativado</b> (em versões "
              "antigas: <b>Fazer backup no Google Drive</b> em <b>Nunca</b>).",
              "Toque em <b>Fazer backup</b> e aguarde terminar.",
              "Confira a linha <b>Local:</b> — ela deve mostrar o horário de agora.",
          ]),
          par_de_figuras("whatsapp_12_ativado_chave", "Protegido com a chave de 64 dígitos.",
                         "whatsapp_13_backup_feito", "Backup local feito: confira o horário "
                         "em “Local”."),
          caixa("atencao", "Faça o backup <b>no dia do exame</b>, depois de ativar a chave. Um "
                "backup antigo — ou feito com senha — não abre com a chave nova e não traz as "
                "mensagens recentes."),
          secao("Etapa 4 — Na ferramenta: extrair"),
          p("Faça a extração normalmente (capítulo 4), com o módulo <b>WhatsApp — Mídia e "
            "Backups</b> marcado. Ele copia as mídias e os backups cifrados e registra, "
            "perguntando ao próprio aparelho, <b>quando cada backup foi gravado</b>."),
          secao("Etapa 5 — Na ferramenta: decifrar"),
          passos([
              "Abra <b>Casos e Documentos</b>, escolha o caso e a aquisição.",
              "Clique em <b>Decifrar backup</b>.",
              "Digite a chave nos 16 campos (ou cole a chave inteira em qualquer campo).",
              "Clique em <b>Decifrar</b>. O backup decifrado vai para a pasta "
              "<b>decifrados</b> do caso, <b>fora</b> da aquisição lacrada, com a procedência "
              "ao lado. A chave fica registrada no complemento do caso, para que outro "
              "examinador possa repetir a decifragem.",
              "Em seguida é gerado o <b>Relatório de Conteúdo</b>, com as conversas.",
          ]),
          figura("18_chave_whatsapp", "A chave de 64 dígitos, em 16 grupos, na ferramenta.",
                 largura=UTIL * 0.6, altura_max=9 * cm),
          secao("Etapa 6 — Ler e selecionar as conversas"),
          p("O Relatório de Conteúdo traz a planilha (CSV) e o caderno HTML com a íntegra. "
            "Conversas muito longas aparecem no PDF como índice, para o documento não ter "
            "milhares de páginas. Para o laudo, use <b>PDF de conversas selecionadas</b>: "
            "marque as conversas relevantes e a ferramenta gera o PDF só delas, completas, "
            "com a origem de cada mensagem."),
          figura("17_conversas", "Escolha das conversas que vão para o PDF."),
          secao("A data do backup nos documentos"),
          p("O conteúdo decifrado retrata o aparelho <b>na data em que o backup foi "
            "gravado</b>, não no dia do exame. Por isso o relatório e o laudo trazem a nota "
            "<b>Nota da fonte</b>: a data do backup (informada pelo próprio aparelho e "
            "registrada no lacre), a mensagem mais recente contida nele e o aviso de que "
            "mensagens posteriores não estão no material."),
          secao("Quando o backup não abre"),
          itens([
              "<b>Chave digitada errada</b>: nada é decifrado. Confira grupo a grupo.",
              "<b>Backup protegido por senha ou chave de acesso</b>: não abre com chave "
              "nenhuma. Refaça as etapas 1 a 3 e extraia de novo.",
              "<b>Backup feito antes de ativar a chave</b>: não abre com ela. Faça um backup "
              "novo (etapa 3) e extraia de novo.",
              "<b>Backup .crypt14 ou anterior</b>: não abre com a chave de 64 dígitos.",
              "<b>Sem backup no aparelho</b>: o módulo diz que só encontrou mídia. Isso não "
              "significa ausência de mensagens.",
          ]),
          ]

    # =====================================================================
    h += capitulo(6, "iPhone",
                  "Sem jailbreak, o caminho é o backup local do iPhone — o mesmo que o iTunes "
                  "faria —, obtido depois que o aparelho confia no computador.")
    h += [secao("Antes de começar: o computador"),
          passos([
              "Instale o aplicativo <b>Dispositivos Apple</b> (Microsoft Store) ou o iTunes. "
              "Ele instala o serviço do Windows que conversa com o iPhone. Não é preciso "
              "abri-lo nem sincronizar nada — e <b>não</b> sincronize: a sincronização grava "
              "no aparelho.",
              "Se o iPhone já estava no cabo durante a instalação, <b>desconecte e conecte de "
              "novo</b>: o serviço só enxerga o aparelho conectado depois que ele começou a "
              "rodar.",
          ]),
          secao("Antes de começar: o iPhone"),
          passos([
              "O iPhone precisa ter <b>terminado a configuração inicial</b>. Num aparelho "
              "restaurado, o iOS recusa o backup até lá (a ferramenta mostra “configuração "
              "inicial não concluída — código 212”). A tela da <b>conta Apple</b> pode ser "
              "pulada: toque em <b>Esqueceu a senha ou não tem uma Conta Apple?</b> e escolha "
              "configurar mais tarde. Não é preciso criar conta para o exame.",
              "Desbloqueie a tela, conecte o cabo e toque em <b>Confiar</b> quando aparecer "
              "<b>Confiar neste computador?</b>. O iPhone pede o código de desbloqueio.",
              "Na ferramenta, página <b>iPhone</b>, clique em <b>Verificar Conexão</b>.",
          ]),
          figura("05_janela_iphone", "Página iPhone."),
          caixa("atencao", "Durante o backup, o iPhone precisa ficar <b>desbloqueado</b>. Com o "
                "<b>Modo de Pouca Energia</b> ligado, o bloqueio automático fica preso em 30 "
                "segundos. Prefira manter a tela ativa tocando nela. Se for preciso mudar o "
                "<b>Bloqueio Automático</b> ou desligar o Modo de Pouca Energia, é alteração "
                "feita no aparelho examinado: registre nas observações do exame."),
          secao("Os módulos"),
          tabela_de_modulos("iOS"),
          Spacer(1, 8),
          secao("Backup comum ou backup cifrado"),
          p("O backup comum não mexe na configuração do aparelho e traz iMessage e SMS, "
            "agenda, as fotos do rolo da câmera e dados de aplicativos (WhatsApp incluso). Mas "
            "o iOS só inclui o <b>registro de chamadas</b> e outros dados sensíveis no backup "
            "<b>cifrado</b>. O módulo de senha temporária define uma senha gerada pela "
            "ferramenta, faz o backup cifrado e <b>retira a senha</b> ao final, conferindo a "
            "retirada."),
          tabela_simples(["Comparação", "Backup comum", "Backup cifrado (senha temporária)"], [
              ["Altera o aparelho?", "Não (só o pareamento, que todo backup exige)",
               "Sim: define e retira uma senha de backup, com registro"],
              ["Mensagens, agenda, WhatsApp", "Sim, lidos direto", "Sim, depois de decifrar"],
              ["Registro de chamadas", "<b>Não</b> — o iOS não inclui", "Sim, depois de decifrar"],
              ["Fotos e o GPS delas", "Sim", "Não lidas nesta versão"],
              ["Código na tela do iPhone", "Uma vez (confiar)", "Até três vezes"],
          ], [0.28, 0.33, 0.39]),
          Spacer(1, 8),
          p("Os dois podem ser marcados juntos: cada backup fica na sua pasta "
            "(<b>backup_ios</b> e <b>backup_ios_cifrado</b>), e o conteúdo é copiado duas "
            "vezes. No backup cifrado, o iPhone pede o código <b>até três vezes</b>: para "
            "aceitar a senha temporária, às vezes durante o backup e para retirá-la. Fique "
            "com o aparelho à mão."),
          caixa("atencao", "Se o dono já definiu uma senha de backup, o módulo de senha "
                "temporária <b>não executa</b> — trocar a senha do dono seria alteração "
                "irreversível. Use o backup comum: ele sai cifrado com a senha do dono, e o "
                "conteúdo só se lê com ela (botão Decifrar backup)."),
          secao("Decifrar o backup"),
          passos([
              "Abra <b>Casos e Documentos</b>, escolha o caso e a aquisição do iPhone.",
              "Clique em <b>Decifrar backup</b>.",
              "Quando o backup foi feito pela senha temporária, a senha <b>já vem "
              "preenchida</b>: a ferramenta a lê do arquivo <b>senha_do_backup.txt</b> da "
              "aquisição, e só se ele confere com o lacre. Confirme.",
              "Os bancos decifrados vão para a pasta <b>decifrados</b> do caso, fora da "
              "aquisição lacrada, cada um com a procedência ao lado. A senha fica registrada "
              "no complemento do caso, para que outro examinador repita a decifragem.",
          ]),
          p("A senha também aparece no desfecho da coleta e no console. Se o backup estava "
            "cifrado com a senha do dono, é ela que se digita."),
          secao("O que aparece no Relatório de Conteúdo"),
          itens([
              "Cada bloco diz de qual backup veio: <b>backup comum do iPhone</b> ou "
              "<b>backup cifrado do iPhone, decifrado</b>.",
              "Backup cifrado ainda não decifrado: o relatório diz que <b>nada se afirma</b> "
              "sobre o conteúdo — e não que esteja vazio.",
              "Arquivo que o iOS não pôs no backup (as chamadas, no backup comum): o "
              "relatório diz que o backup não o contém, e que isso não prova ausência.",
              "<b>WhatsApp</b>: textos, fotos, áudios, grupos e localizações compartilhadas, "
              "com as coordenadas e o link <b>abrir no mapa</b>. Registros que o próprio "
              "WhatsApp gera — o aviso de criptografia, a criação de um grupo — aparecem "
              "com sentido <b>Sistema</b> e a observação “não é mensagem digitada”. Tipo "
              "de registro que a ferramenta não conhece aparece como <b>não reconhecido</b>, "
              "sem palpite sobre o que seja.",
              "<b>Locais das fotos</b>: as fotos do rolo da câmera com GPS (ver capítulo 9).",
          ]),
          ]

    # =====================================================================
    h += capitulo(7, "Exame sem extração",
                  "Aparelho bloqueado por credencial, que não liga ou danificado: o exame "
                  "existe mesmo sem extração, e o laudo negativo precisa da mesma cadeia de "
                  "custódia.")
    h += [passos([
              "Na página Android ou iPhone, clique em <b>Exame sem extração</b>.",
              "Siga as mesmas telas de caso, autorização, peça, lacre e fotografias.",
              "No formulário, informe se o aparelho liga, o estado em que foi recebido, a "
              "bateria, se estava isolado da rede, o <b>tipo de bloqueio</b> e o que foi "
              "tentado. A recomendação já vem preenchida.",
              "Se o aparelho liga, a ferramenta <b>tenta a conexão sem alterá-lo</b> e guarda "
              "a resposta como prova: no Android, a listagem do ADB (por exemplo, “NÃO "
              "AUTORIZADO”); no iPhone, uma sessão sem pedido de pareamento.",
              "Gere o <b>Laudo Pericial</b> em Casos e Documentos: sai a versão “Exame sem "
              "Extração”.",
          ]),
          figura("11_exame_sem_extracao", "Estado do aparelho e tentativas.", largura=UTIL * 0.6,
                 altura_max=10 * cm),
          p("A conclusão diz que não foi possível extrair, e por quê — e que isso <b>não</b> "
            "permite concluir nada sobre o conteúdo do aparelho."),
          ]

    # =====================================================================
    h += capitulo(8, "Discos e pendrives",
                  "A plataforma Armazenamento examina unidades conectadas ao computador: "
                  "pendrives, HDs externos e o disco retirado de um computador examinado.")
    h += [caixa("atencao", "O disco de um computador examinado é <b>retirado</b> e ligado à "
                "estação por dock ou adaptador, com um <b>bloqueador de escrita de "
                "hardware</b> entre os dois. A ferramenta não substitui o bloqueador. A "
                "estação do próprio examinador aparece na lista, identificada, para não ser "
                "escolhida por engano."),
          figura("06_janela_armazenamento", "Página Armazenamento: escolha da unidade."),
          tabela_de_modulos("Computador"),
          Spacer(1, 8),
          p("A <b>Imagem do Volume</b> exige abrir a ferramenta como Administrador. Volume "
            "cifrado com BitLocker é detectado e informado."),
          ]

    # =====================================================================
    h += capitulo(9, "Casos e Documentos",
                  "Tudo o que se faz depois da extração: documentos, exame do material, "
                  "entrega e organização dos casos — sem precisar abrir as pastas no Windows.")
    h += [figura("12_casos_ficha", "Casos e Documentos: casos, ficha, aparelhos e ações."),
          secao("Os documentos"),
          tabela_simples(["Documento", "Para que serve"], [
              ["<b>Relatório de Extração</b>", "Linha do tempo do procedimento, ambiente, "
               "módulos, desfecho e o manifesto de hashes."],
              ["<b>Relatório de Conteúdo</b>", "As mensagens, chamadas e contatos "
               "interpretados: planilhas CSV, caderno HTML e PDF, com a origem de cada linha."],
              ["<b>PDF de conversas selecionadas</b>", "Só as conversas relevantes, completas."],
              ["<b>Laudo Pericial</b>", "O documento final, assinado pelo examinador da sessão."],
          ], [0.3, 0.7]),
          Spacer(1, 8),
          p("Os documentos abrem no <b>visualizador da ferramenta</b> (páginas, zoom, "
            "imprimir, salvar cópia) e ficam listados na aba <b>Documentos</b>. Eles são "
            "gravados <b>fora</b> da aquisição lacrada, que nunca é alterada."),
          figura("15_visualizador", "Visualizador de PDF.", altura_max=10 * cm),
          figura("22_laudo_pagina", "A primeira página de um laudo.", largura=UTIL * 0.6,
                 altura_max=12 * cm),
          secao("Locais das fotos"),
          p("O Relatório de Conteúdo traz a seção <b>Locais das fotos (GPS gravado nas "
            "imagens)</b>: uma linha por foto que tenha coordenadas no EXIF — os dados que a "
            "câmera grava dentro do arquivo. Vale para JPEG do Android e HEIC do iPhone."),
          tabela_simples(["Coluna", "O que é"], [
              ["Data e hora", "A do <b>relógio do aparelho</b> que fotografou."],
              ["Hora do GPS (UTC)", "A dos <b>satélites</b>, gravada junto da coordenada. Não "
               "depende do relógio do aparelho: se ele estava errado, esta é a referência."],
              ["Latitude, longitude, altitude", "Onde a foto foi tirada, segundo o EXIF."],
              ["Câmera", "Fabricante e modelo gravados no arquivo."],
              ["Mapa", "Link <b>abrir no mapa</b>, clicável no PDF."],
          ], [0.3, 0.7]),
          Spacer(1, 6),
          itens([
              "Só entram fotos que <b>conferem com o lacre</b>. Foto alterada depois da "
              "aquisição é recusada, com o motivo.",
              "As fotografias que o examinador tira da peça (frente e verso) <b>não</b> entram: "
              "a mesa do exame não é um lugar onde o aparelho esteve.",
              "A mesma foto copiada por dois módulos conta uma vez só.",
              "Coordenada <b>0,0</b> — típica de câmera sem sinal de GPS — não vira local: vai "
              "para os descartes, com o motivo.",
          ]),
          caixa("atencao", "A coordenada diz onde a <b>foto</b> foi tirada, não onde o "
                "aparelho estava. O EXIF é editável, e uma foto recebida de outra pessoa traz "
                "a localização do aparelho dela. Aplicativos de mensagem costumam apagar o "
                "EXIF: foto sem GPS não prova que o aparelho não registre localização."),
          secao("PDF de conversas"),
          p("O botão <b>PDF de conversas selecionadas</b> usa a aquisição marcada na lista. O "
            "título da janela mostra o caso e a aquisição: se a lista vier vazia, confira "
            "primeiro se é a aquisição certa."),
          secao("Examinar o material: aba Material"),
          p("A aba <b>Material</b> mostra as pastas e arquivos da aquisição, com a prévia "
            "(foto, texto, planilha, PDF, tabelas de banco de dados) e a <b>conferência do "
            "SHA-256 com o lacre</b>: confere, DIVERGE ou não consta. Tudo só leitura."),
          figura("14_casos_material", "Aba Material."),
          caixa("dica", "Prefira a aba Material ao Explorer do Windows. Ao navegar, o Explorer "
                "pode criar arquivos ocultos (Thumbs.db, desktop.ini) dentro da pasta lacrada, "
                "e a conferência passa a acusar arquivo acrescentado."),
          secao("Entregar: Exportar para entrega"),
          passos([
              "Na aba Documentos, selecione documentos — ou, na aba Material, arquivos e "
              "pastas (Ctrl e Shift para vários).",
              "Clique em <b>Exportar para entrega</b> (ou <b>Exportar selecionados</b>).",
              "Escolha o destino (pendrive, pasta) e escreva a finalidade ou o destinatário.",
              "A ferramenta copia, confere cada cópia pelo SHA-256 e gera o <b>recibo de "
              "entrega</b> (PDF e texto), com campos de assinatura. A entrega fica registrada "
              "no caso.",
          ]),
          figura("16_entrega", "Exportar para entrega.", largura=UTIL * 0.8, altura_max=6 * cm),
          secao("Retificar, anexar, excluir"),
          itens([
              "<b>Retificar Dados do Caso</b> e <b>Anexar Autorização</b> entram como "
              "<b>complemento</b> do caso: o original é preservado e o que mudou fica registrado.",
              "<b>Excluir caso</b> pede que o nome do caso seja digitado, recusa caso com "
              "aquisição ainda sem lacre e envia tudo à <b>Lixeira do Windows</b> (restaurável). "
              "A exclusão fica no registro de acessos.",
          ]),
          ]

    # =====================================================================
    h += capitulo(10, "Cadeia de custódia e integridade",
                  "Como a ferramenta prova que o material não mudou desde a coleta.")
    h += [secao("O lacre de cada aquisição"),
          p("Ao final da extração, o arquivo <b>manifesto_hashes.txt</b> recebe o SHA-256 de "
            "cada arquivo adquirido. O hash do próprio manifesto aparece no rodapé de cada "
            "página dos documentos. Alterar qualquer arquivo, ou o manifesto, muda esse número."),
          secao("Conferir a integridade"),
          p("Na barra lateral, <b>Cadeia de Custódia</b> confere uma aquisição contra o seu "
            "manifesto e grava o resultado da conferência (nenhuma conferência apaga outra)."),
          figura("21_cadeia_custodia", "Conferência de integridade.", altura_max=9 * cm),
          secao("Onde fica cada coisa"),
          tabela_simples(["Pasta do caso", "Conteúdo"], [
              ["<b>&lt;plataforma&gt;_&lt;data&gt;_&lt;hora&gt;</b>", "A aquisição lacrada. Nunca "
               "é reescrita."],
              ["<b>documentos</b>", "Relatório de Extração, Laudo, Conversas."],
              ["<b>relatorios</b>", "Relatórios de Conteúdo (CSV, HTML, PDF)."],
              ["<b>decifrados</b>", "Backups decifrados, com a procedência."],
              ["<b>complementos</b>", "Retificações, autorizações, decifragens, entregas."],
          ], [0.38, 0.62]),
          ]

    # =====================================================================
    h += capitulo(11, "Aparelhos testados e limitações",
                  "A ferramenta diz o que verificou e o que não verificou — inclusive sobre "
                  "si mesma. Esta é a lista dos aparelhos em que a versão 1.0 foi provada, e "
                  "das limitações conhecidas.")
    h += [secao("Onde a versão 1.0 foi provada"),
          tabela_simples(["Aparelho", "Sistema", "O que foi provado"], [
              ["Motorola moto x4", "Android 9", "Extração completa, WhatsApp pela chave de 64 "
               "dígitos, fotos com GPS"],
              ["Samsung Galaxy A22", "Android 13 (One UI 5.1)", "Extração completa, aplicativo "
               "agente, alerta de relógio deslocado"],
              ["Emulador Android", "Android 13, com privilégio elevado", "Módulos que exigem "
               "privilégio elevado, WhatsApp"],
              ["iPhone 11", "iOS 18.6.2", "Backup comum e cifrado, decifragem, WhatsApp, fotos "
               "com GPS"],
              ["Pendrive (7,28 GiB)", "Windows 11", "Os quatro módulos, inclusive a imagem do "
               "volume"],
          ], [0.24, 0.26, 0.5]),
          Spacer(1, 8),
          p("Outros modelos e versões tendem a funcionar pelo mesmo caminho, mas não foram "
            "verificados. Quando um módulo falha num aparelho, a ferramenta registra a recusa "
            "e não conclui nada sobre o conteúdo."),
          secao("Limitações conhecidas"),
          itens([
              "<b>Xiaomi, Redmi e POCO (MIUI / HyperOS)</b>: o aplicativo agente não foi "
              "verificado. Esses aparelhos costumam exigir “Instalar via USB” e conta Xiaomi; a "
              "instalação pode ser recusada. A limitação consta do próprio módulo.",
              "<b>Android 8 ou anterior</b>: fora do escopo desta versão. Num Galaxy J5 Prime "
              "com Android 7, o Dump do Sistema de Arquivos parou cedo na cópia do armazenamento "
              "interno e, ainda assim, indicou “Concluído”; o WhatsApp Business no local antigo "
              "não é procurado. Em aparelho assim, confira a reconciliação de cada módulo ou use "
              "outra ferramenta.",
              "<b>Android 12 em diante</b> não tem mais o backup do sistema: SMS e chamadas são "
              "lidos diretamente; quando o sistema recusa essa leitura, entram pelo aplicativo "
              "agente, que é de seleção expressa.",
              "<b>IMEI</b>: do Android 10 em diante, o sistema não o entrega sem privilégio "
              "elevado. A ferramenta registra cada via tentada e declara que não obteve.",
              "<b>WhatsApp no Android</b>: só se decifra o backup protegido pela chave de 64 "
              "dígitos (crypt15). O módulo de downgrade do WhatsApp ainda não foi testado em "
              "aparelho real.",
              "<b>iPhone</b>: as fotos do backup cifrado não são lidas nesta versão (as do "
              "backup comum, sim). Com senha de backup definida pelo dono, só o backup comum, "
              "decifrado com a senha dele.",
              "<b>Fora do alcance</b>: desbloqueio de aparelho, contorno de senha, extração "
              "física de celular sem privilégio elevado e recuperação de dado apagado.",
          ]),
          ]

    # =====================================================================
    h += capitulo(12, "Problemas comuns", "O que fazer quando algo não sai como esperado.")
    for titulo, texto in (
        ("O aparelho aparece como “não autorizado”",
         "Desbloqueie a tela e aceite <b>Permitir depuração USB</b>. Se a pergunta não "
         "aparecer, desligue e ligue a depuração USB, ou revogue as autorizações nas Opções "
         "do desenvolvedor e conecte de novo."),
        ("Nenhum aparelho responde",
         "Troque o cabo (pode ser só de carga), ponha o modo USB em “Transferência de "
         "arquivos” e confira se a depuração USB está ligada."),
        ("O aparelho recusou o aplicativo agente",
         "Veja se há uma confirmação na tela do aparelho (Play Protect). Em Xiaomi, ligue "
         "“Instalar via USB”."),
        ("O console alerta que o relógio do aparelho está deslocado",
         "O aparelho marcava outra data e hora (é comum em aparelho sem chip ou sem "
         "internet). Não corrija o relógio: o desvio medido fica registrado, e o Relatório "
         "de Extração e o laudo avisam que as datas gravadas pelo aparelho devem ser lidas "
         "com essa correção."),
        ("O Windows mostrou “O Windows protegeu o computador”",
         "É o aviso para programa sem assinatura digital paga. Confira o hash do instalador, "
         "clique em <b>Mais informações</b> e em <b>Executar assim mesmo</b> (capítulo 2). Se "
         "não houver o botão, o Controle Inteligente de Aplicativos está ligado e exige "
         "assinatura digital: instale em outro computador, peça ao setor de TI que libere o "
         "programa, ou rode do código-fonte (capítulo 2)."),
        ("A ferramenta não encontra o iPhone",
         "Confira se o aplicativo Dispositivos Apple (ou o iTunes) está instalado, "
         "<b>desconecte e conecte o cabo de novo</b>, desbloqueie a tela e toque em "
         "<b>Confiar</b>."),
        ("O iPhone recusou o backup (código 212)",
         "A configuração inicial do aparelho não foi concluída. Termine-a — a conta Apple "
         "pode ser pulada — e tente de novo (capítulo 6)."),
        ("O backup do iPhone parou no meio",
         "A tela bloqueou ou o cabo mexeu. Mantenha o iPhone desbloqueado (cuidado com o Modo "
         "de Pouca Energia) e digite o código sempre que ele pedir."),
        ("A lista de conversas veio vazia",
         "Confira, no título da janela, se a aquisição é a certa. Se for, o Relatório de "
         "Conteúdo diz por que não há conversa interpretada."),
        ("O relatório diz que “o provider respondeu e não retornou nenhum registro”",
         "O próprio Android respondeu à consulta que aquela fonte está vazia — por exemplo, "
         "SMS num aparelho sem chip. Não é falha de leitura. Registros apagados não aparecem "
         "por esta via."),
        ("Um arquivo aparece com “(nome alterado 1)”",
         "O Windows não aceita o nome que o arquivo tem no aparelho (dois nomes que só "
         "diferem em maiúsculas, ou ponto no fim). O conteúdo é o mesmo, conferido pelo hash, "
         "e a correspondência está no relatório de reconciliação."),
        ("O WhatsApp mostra “Ativado · Senha”",
         "O backup está protegido por senha, e a ferramenta decifra só com a chave de 64 "
         "dígitos. Desative a proteção e ative de novo pela chave (capítulo 5, etapas 1 e 2)."),
        ("As mensagens recentes do WhatsApp não aparecem",
         "O backup é anterior a elas. Veja a “Nota da fonte” no relatório e faça um "
         "backup novo antes de extrair."),
        ("Esqueci a senha e o código",
         "Crie um perfil novo. As aquisições antigas continuam no seu nome."),
    ):
        h += [sub(titulo), p(texto)]

    # =====================================================================
    h += capitulo(13, "Glossário", "Termos usados na ferramenta e nesta apostila.")
    h += [tabela_simples(["Termo", "Significado"], [
        ["ADB", "Android Debug Bridge, a ferramenta de depuração do Android."],
        ["Aquisição", "Uma extração de um aparelho, gravada numa pasta lacrada dentro do caso."],
        ["Caso", "O conjunto de aquisições de um mesmo exame."],
        ["Complemento", "Informação juntada ao caso depois, sem reescrever a aquisição."],
        ["Backup cifrado (iPhone)", "Backup local protegido por senha; é o único em que o "
         "iOS inclui o registro de chamadas."],
        ["crypt15", "Formato do backup cifrado do WhatsApp."],
        ["EXIF", "Dados que a câmera grava dentro da foto: data, câmera e, às vezes, GPS."],
        ["GPS (UTC)", "Hora dos satélites gravada junto da coordenada; independe do relógio "
         "do aparelho."],
        ["DEFR / DES", "Primeiro respondedor e especialista, na ABNT NBR ISO/IEC 27037."],
        ["Hash (SHA-256)", "Impressão digital de um arquivo: qualquer alteração muda o valor."],
        ["Lacre (manifesto)", "A lista de hashes de todos os arquivos da aquisição."],
        ["Seleção expressa", "Módulo que altera o aparelho e só roda se escolhido um a um."],
        ["Ressalva", "O que o módulo não alcançou, declarado junto do que obteve."],
    ], [0.25, 0.75])]
    return h


def main() -> None:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    documento = Apostila(SAIDA)
    documento.multiBuild(conteudo())
    print(f"Apostila gerada: {SAIDA}")


if __name__ == "__main__":
    main()
