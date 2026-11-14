"""
Gera o Guia de Prática com Emulador do Hexis Forensics, em PDF (duas páginas).

Para quem quer treinar o fluxo da ferramenta sem aparelho real e sem risco a
um caso: montar um emulador Android, popular dados de teste, extrair e ler o
resultado. O emulador é bancada de treino, nunca prova de caso real.

    py ferramentas/apostila/gerar_guia_emulador.py
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

SAIDA = AQUI / "saida" / "Guia_de_Pratica_com_Emulador.pdf"
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


def tabela(cabecalho_linha, filas, larguras):
    dados = [[Paragraph(c, CELA_B) for c in cabecalho_linha]]
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
    cab = Table([[Paragraph("Guia de Prática com Emulador", TITULO), logo]],
                colWidths=[LARGURA - 4.4 * cm, 4.4 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [cab, Paragraph(sub_titulo, SUB),
            Paragraph(f"Hexis Forensics {VERSAO} — Guia de Prática com Emulador — o passo a passo "
                      "do exame real está na Apostila do Usuário", SUB), Spacer(1, 2)]


def conteudo():
    h = []
    # ---------------- PÁGINA 1 ----------------
    h += cabecalho("Página 1 · MONTAR O EMULADOR (bancada de treino) · verso: extrair e ler o "
                   "resultado")
    h += caixa("<b>SÓ PARA TREINO.</b> O emulador serve para aprender a operar o Hexis Forensics "
               "sem aparelho real e sem risco a um caso. Ele <b>não é um aparelho de verdade</b>: "
               "não tem IMEI nem banda-base reais, a partição de dados é diferente e já vem com "
               "<b>privilégio elevado (root)</b>, que um celular comum não tem. Por isso, "
               "<b>nunca</b> use o emulador para afirmar que uma extração vai funcionar num "
               "celular real, nem como base de laudo. É laboratório, não prova.", alerta=True)

    h += faixa("1. INSTALAR O ANDROID STUDIO E CRIAR O EMULADOR", AZUL)
    h.append(etapa("A. Android Studio e a imagem certa"))
    h.append(passos([
        "Baixe e instale o <b>Android Studio</b> (developer.android.com/studio). É gratuito e "
        "roda no Windows. Aceite os componentes padrão na instalação.",
        "Abra o <b>Device Manager</b> (ícone de celular à direita) > <b>Create device</b> > "
        "escolha um <b>Pixel</b> > <b>Next</b>.",
        "<b>System Image:</b> escolha <b>Android 13 (API 33)</b> numa versão <b>sem Google "
        "Play</b> — o rótulo deve ser “Google APIs” ou “AOSP”, <b>não</b> “Google Play”. A imagem "
        "com Google Play <b>bloqueia o root</b> e serve menos ao treino. Baixe a imagem.",
        "<b>Finish</b> para criar o emulador. Dê um nome que lembre treino, p. ex. "
        "<b>Bancada-Treino</b>.",
    ], reiniciar=True))

    h.append(etapa("B. Ligar e conferir o privilégio elevado (root)"))
    h.append(passos([
        "No Device Manager, clique em <b>Play</b> para iniciar o emulador e espere a tela inicial "
        "do Android abrir.",
        "No computador, abra o Terminal na pasta do <b>adb</b> (ou com o adb no PATH) e digite "
        "<b>adb devices</b>: deve listar algo como <b>emulator-5554 device</b>. O emulador já vem "
        "autorizado — não há cabo nem impressão digital RSA.",
        "Digite <b>adb root</b>: deve responder “restarting adbd as root”. É esse privilégio — "
        "que o celular comum não tem — que deixa o emulador rodar os módulos que exigem root.",
    ]))

    h += faixa("2. POPULAR DADOS DE TESTE")
    h.append(etapa("C. Contatos, SMS e WhatsApp"))
    h.append(passos([
        "<b>Contatos:</b> abra o app Contatos do emulador e crie alguns, com nome e número.",
        "<b>SMS:</b> na barra lateral do emulador, <b>Extended controls</b> (o botão de três "
        "pontos “...”) > <b>Phone</b> > digite um número e uma mensagem > <b>Send message</b>: "
        "chega um SMS de teste no emulador.",
        "<b>WhatsApp:</b> baixe o <b>APK no site</b> (whatsapp.com/android — no emulador não há "
        "Play Store) e <b>arraste o arquivo .apk para a janela do emulador</b> para instalar. "
        "Configure com um número cujo SMS você consiga receber e troque algumas mensagens para "
        "ter conteúdo.",
    ]))
    h += caixa("<b>Gmail não roda</b> no emulador sem Google Play — é esperado, não é defeito. O "
               "treino aqui cobre contatos, SMS, mídias e WhatsApp, que é o que a ferramenta "
               "extrai no Android.")

    # ---------------- PÁGINA 2 ----------------
    h.append(PageBreak())
    h += cabecalho("Página 2 · EXTRAIR E LER O RESULTADO")

    h += faixa("3. EXTRAIR COM O HEXIS", AZUL)
    h.append(etapa("D. Conectar e abrir um caso de treino  "
                   "<font color='grey' size='7.5'>(apostila, cap. 3–4)</font>"))
    h.append(passos([
        "Com o emulador aberto, na ferramenta: página <b>Android</b> > <b>Verificar Conexão</b>. "
        "O emulador aparece conectado e autorizado, sem cabo.",
        "<b>Iniciar Extração</b> > confirme o examinador > leia <b>Método e limitações</b> > "
        "<b>Ciente — Prosseguir</b>.",
        "<b>Caso:</b> crie um caso novo e deixe <b>treino</b> explícito no nome (p. ex. "
        "TREINO-001). <b>Nunca misture com caso real.</b> Preencha dispositivo, lacre e as fotos "
        "com dados fictícios.",
    ], reiniciar=True))

    h.append(etapa("E. Marcar os módulos e extrair"))
    h.append(passos([
        "Os módulos comuns já vêm marcados. Como o emulador tem <b>privilégio elevado</b>, você "
        "pode marcar também os de <b>seleção expressa</b> (os que alteram o aparelho / exigem "
        "root) para ver como a ferramenta os conduz e registra.",
        "Para treinar o WhatsApp, siga a <b>chave de 64 dígitos</b> como no Guia de Extração "
        "Rápida (etapa B do Android).",
        "<b>Iniciar</b> e aguarde a mensagem de extração finalizada. Não feche a ferramenta no "
        "meio: a aquisição ficaria sem lacre.",
    ]))

    h += faixa("4. LER O RESULTADO · Casos e Documentos > caso > aquisição", VERDE)
    h += tabela(["Documento / ação", "O que é"], [
        ["Relatório de Extração", "O procedimento: método, desfecho de cada módulo e hashes."],
        ["Relatório de Conteúdo", "Mensagens, WhatsApp, contatos e locais das fotos, com a "
         "origem de cada linha (CSV + PDF)."],
        ["Decifrar backup", "Trate o WhatsApp com a chave de 64 dígitos que você gerou."],
        ["Conferir Integridade", "Recalcula o hash de cada arquivo e compara com o lacre — "
         "treine também este passo."],
    ], [0.3, 0.7])

    h += faixa("COMO LER O RESULTADO DE CADA MÓDULO")
    h += tabela(["Resultado", "O que significa"], [
        ["Concluído", "Obteve o que se propunha."],
        ["Concluído com ressalva", "Obteve parte e declarou o que não alcançou."],
        ["Não obteve dado", "Nada foi adquirido. <b>Não</b> significa que o dado não exista no "
         "aparelho."],
    ], [0.3, 0.7])

    h += caixa("<b>O QUE O EMULADOR NÃO ENSINA.</b> Por ter root, o emulador mostra extrações que "
               "num <b>celular comum sem root não aconteceriam</b>. Não conclua que “funcionou no "
               "emulador” significa “funciona no aparelho X”. O emulador treina o <b>operador</b> "
               "e o <b>fluxo</b>; a prova de que um método funciona num modelo real só vem "
               "testando o modelo real.", alerta=True)
    h += caixa("<b>Regra de ouro:</b> o que não foi obtido não é o que não existe. A ferramenta "
               "nunca afirma o que não verificou — e você, treinando, também não.")
    return h


def main():
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            title="Guia de Prática com Emulador — Hexis Forensics",
                            author="Hexis Forensics")
    doc.build(conteudo())
    print("Guia do emulador (PT) gerado:", SAIDA)


if __name__ == "__main__":
    main()
