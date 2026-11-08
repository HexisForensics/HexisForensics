"""
Gera o Guia de Extração Rápida do Hexis Forensics, em PDF (duas páginas,
frente e verso).

Para quem não vai ler a apostila: Android e iPhone do cabo ao laudo, com o
WhatsApp dentro do fluxo de cada um. Cada passo remete ao capítulo da
apostila que o explica.

    py ferramentas/apostila/gerar_guia_rapido.py
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

SAIDA = AQUI / "saida" / "Guia_de_Extracao_Rapida.pdf"
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
                       leading=12, spaceBefore=4, spaceAfter=1)
CORPO = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=10.8)
NUMERO = ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=8.5, textColor=AZUL,
                        leading=10.8, alignment=1)
CAIXA = ParagraphStyle("x", parent=CORPO, fontSize=8.2, leading=10.4)

LARGURA = A4[0] - 2.4 * cm
CONTADOR = {"n": 0}


def faixa(texto, cor=ESCURO):
    t = Table([[Paragraph(texto, FAIXA)]], colWidths=[LARGURA])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cor),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return [Spacer(1, 6), t, Spacer(1, 2)]


def etapa(texto):
    return Paragraph(texto, ETAPA)


def passos(lista, reiniciar=False):
    """Passos numerados em sequência contínua dentro de cada plataforma."""
    if reiniciar:
        CONTADOR["n"] = 0
    linhas = []
    for texto in lista:
        CONTADOR["n"] += 1
        linhas.append([Paragraph(str(CONTADOR["n"]), NUMERO), Paragraph(texto, CORPO)])
    t = Table(linhas, colWidths=[0.8 * cm, LARGURA - 0.8 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3),
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


def tabela(linhas, larguras):
    dados = [[Paragraph(c, CORPO) for c in linha] for linha in linhas]
    t = Table(dados, colWidths=[LARGURA * f for f in larguras])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINHA)]))
    return t


def cabecalho(subtitulo):
    logo = Image(str(LOGO), width=4.2 * cm, height=4.2 * cm * 256 / 740)
    texto = [Paragraph("Guia de Extração Rápida", TITULO), Paragraph(subtitulo, SUB)]
    t = Table([[texto, logo]], colWidths=[LARGURA - 4.4 * cm, 4.4 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 2)]


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(1.2 * cm, 0.55 * cm,
                      f"Hexis Forensics {VERSAO} · Guia de Extração Rápida · os detalhes de cada "
                      "passo estão na Apostila do Usuário")
    canvas.drawRightString(A4[0] - 1.2 * cm, 0.55 * cm, f"página {doc.page} de 2")
    canvas.restoreState()


def pagina_android():
    h = cabecalho("Página 1 · ANDROID, do cabo ao laudo, com o WhatsApp · verso: iPhone e "
                  "depois da extração")
    h += caixa("<b>Tenha em mãos antes de começar:</b> cabo USB de <b>dados</b> (cabo só de "
               "carga não serve) · número do <b>lacre</b> · a peça para <b>duas fotos</b> "
               "(frente e verso) · o documento de <b>autorização</b> digitalizado · o seu "
               "perfil de examinador criado na ferramenta.")

    h += faixa("ANDROID")
    h.append(etapa("A. Preparar o aparelho  <font color='grey' size='7.5'>(apostila, cap. 3)"
                   "</font>"))
    h.append(passos([
        "<b>Configurações > Sobre o telefone</b> > toque <b>7 vezes</b> em <b>Número da "
        "versão</b> (ou “Número de compilação”) até aparecer “Você agora é um desenvolvedor”.",
        "<b>Opções do desenvolvedor</b>: ligue <b>Depuração USB</b> e <b>Permanecer ativo</b>.",
        "Conecte o cabo > marque <b>Sempre permitir a partir deste computador</b> > "
        "<b>Permitir</b>.",
        "Na ferramenta, página <b>Android</b> > <b>Verificar Conexão</b>: o aparelho tem de "
        "aparecer conectado e autorizado.",
    ], reiniciar=True))

    h.append(etapa("B. WhatsApp: gravar o backup com a CHAVE DE 64 DÍGITOS  "
                   "<font color='grey' size='7.5'>(cap. 5) · pule se não houver WhatsApp"
                   "</font>"))
    h.append(passos([
        "No aparelho: WhatsApp > Configurações > Conversas > Backup de conversas > <b>Backup "
        "criptografado de ponta a ponta</b>. Se estiver <b>Ativado · Senha</b> ou <b>Chave de "
        "acesso</b>: <b>Desativar</b> (pede a senha do backup).",
        "<b>Ativar</b> > <b>NÃO</b> toque no botão verde “Usar chave de acesso” > <b>Mais "
        "opções</b> > <b>Chave de criptografia de 64 dígitos</b> > Gerar.",
        "<b>Anote ou fotografe a chave</b> (16 grupos de 4) > “Anotei minha chave” > Criar.",
        "Conta do Google: <b>Nenhuma</b> · Backup automático: <b>Desativado</b> · <b>Fazer "
        "backup</b>. Confira a linha <b>Local:</b> com o horário de agora.",
    ]))

    h.append(etapa("C. Extrair  <font color='grey' size='7.5'>(cap. 4)</font>"))
    h.append(passos([
        "Confira os módulos: os comuns já vêm marcados (o <b>WhatsApp — Mídia e Backups</b> "
        "entre eles). Os que alteram o aparelho começam desmarcados: só marque se precisar.",
        "<b>Iniciar Extração</b> > confirme o examinador > leia <b>Método e limitações</b> > "
        "<b>Ciente — Prosseguir</b>.",
        "<b>Caso</b>: novo ou existente (um caso reúne vários aparelhos) > <b>Autorização</b>: "
        "anexe o documento > <b>Dispositivo</b>: marca, modelo, <b>lacre</b> e as <b>duas "
        "fotos</b>.",
        "Aguarde até a mensagem de extração finalizada. <b>Não feche a ferramenta</b> no "
        "meio: a aquisição ficaria sem lacre. Para parar, use <b>Cancelar</b>.",
    ]))

    h.append(etapa("D. Decifrar o WhatsApp  <font color='grey' size='7.5'>(cap. 5)</font>"))
    h.append(passos([
        "<b>Casos e Documentos</b> > caso > aquisição > <b>Decifrar backup</b> > digite ou "
        "cole a chave de 64 dígitos > <b>Decifrar</b>. Depois, siga o verso (“Depois da "
        "extração”).",
    ]))
    h += caixa("<b>ATENÇÃO.</b> Ligar a depuração USB, mexer na proteção do backup do WhatsApp "
               "e mandar fazer o backup são <b>alterações no aparelho</b>, impostas pelo método: "
               "a ferramenta registra, e a chave fica no complemento do caso. Faça o backup "
               "<b>no dia do exame</b>: backup antigo ou feito com senha não abre com a chave "
               "nova e não traz as mensagens recentes.", alerta=True)
    return h


def pagina_iphone_e_depois():
    h = cabecalho("Página 2 · iPHONE e DEPOIS DA EXTRAÇÃO (Android e iPhone)")

    h += faixa("iPHONE · o WhatsApp vem dentro do backup do iPhone", AZUL)
    h.append(etapa("A. Preparar  <font color='grey' size='7.5'>(cap. 6)</font>"))
    h.append(passos([
        "No computador: app <b>Dispositivos Apple</b> (Microsoft Store) ou iTunes instalado. "
        "Não abra nem sincronize. Se o iPhone já estava no cabo, <b>desconecte e conecte de "
        "novo</b>.",
        "iPhone com a <b>configuração inicial concluída</b> (a conta Apple pode ser pulada), "
        "<b>desbloqueado</b> > <b>Confiar</b> > código de desbloqueio.",
        "Página <b>iPhone</b> > <b>Verificar Conexão</b>.",
    ], reiniciar=True))
    h.append(etapa("B. Escolher o backup e extrair"))
    h.append(tabela([
        ["", "<b>Backup comum</b>", "<b>Backup cifrado</b> (senha temporária)"],
        ["Traz", "Mensagens, agenda, <b>WhatsApp</b>, fotos e o GPS delas",
         "Tudo do comum (menos as fotos) <b>+ registro de chamadas</b>"],
        ["Altera o aparelho?", "Não (só o pareamento)",
         "Sim: define e retira uma senha de backup, com registro"],
        ["Código no iPhone", "Uma vez", "Até <b>três</b> vezes: fique com o aparelho à mão"],
    ], [0.2, 0.36, 0.44]))
    h.append(passos([
        "Marque um ou os dois > <b>Iniciar Extração</b> > as mesmas telas do Android (método, "
        "caso, autorização, lacre e fotos). Mantenha o iPhone <b>desbloqueado</b> durante o "
        "backup (cuidado com o Modo de Pouca Energia).",
        "Fez o cifrado? <b>Casos e Documentos</b> > aquisição > <b>Decifrar backup</b>: a "
        "senha <b>já vem preenchida</b> > Decifrar.",
    ]))

    h += faixa("DEPOIS DA EXTRAÇÃO · em Casos e Documentos > caso > aquisição", VERDE)
    h.append(tabela([
        ["<b>Relatório de Conteúdo</b>", "Mensagens, WhatsApp, chamadas, contatos e locais "
         "das fotos, com a origem de cada linha (CSV + PDF)."],
        ["<b>PDF de conversas selecionadas</b>", "Clique nas conversas relevantes > "
         "<b>Gerar PDF das selecionadas</b>. Confira no título da janela se a aquisição é a "
         "certa."],
        ["<b>Relatório de Extração</b>", "O procedimento: peça, fotos, método, desfecho de "
         "cada módulo e hashes."],
        ["<b>Laudo Pericial</b>", "O documento final, no nome do examinador da sessão."],
        ["<b>Conferir Integridade</b>", "Recalcula o hash de cada arquivo e compara com o "
         "lacre. Faça antes de entregar."],
        ["<b>Exportar para entrega…</b>", "Copia o material para a mídia de entrega, com "
         "registro."],
    ], [0.34, 0.66]))

    h += faixa("COMO LER O RESULTADO DE CADA MÓDULO")
    h.append(tabela([
        ["<b>Concluído</b>", "Obteve o que se propunha."],
        ["<b>Concluído com ressalva</b>", "Obteve parte e declarou o que não alcançou."],
        ["<b>Não obteve dado</b>", "Nada foi adquirido. <b>Não</b> significa que o dado não "
         "exista no aparelho."],
    ], [0.3, 0.7]))

    h += faixa("DEU ERRADO?", VERMELHO)
    h.append(tabela([
        ["Android “não autorizado”", "Desbloqueie a tela e aceite <b>Permitir</b>. Sem o "
         "aviso: Opções do desenvolvedor > Revogar autorizações > reconecte."],
        ["Nenhum aparelho responde", "Troque o cabo · modo USB em <b>Transferência de "
         "arquivos</b> · confira a depuração USB."],
        ["WhatsApp não decifra", "Chave errada (confira grupo a grupo) · backup com senha ou "
         "anterior à chave: refaça a etapa B e extraia de novo."],
        ["Não encontra o iPhone", "Dispositivos Apple instalado · reconecte o cabo · "
         "desbloqueie · <b>Confiar</b>."],
        ["iPhone: código 212", "Termine a configuração inicial do aparelho e tente de novo."],
        ["Backup do iPhone parou", "A tela bloqueou ou o cabo mexeu: mantenha desbloqueado e "
         "digite o código sempre que pedir."],
        ["Relógio do aparelho deslocado", "<b>Não corrija</b>: o desvio fica registrado e os "
         "documentos avisam."],
    ], [0.3, 0.7]))
    h += caixa("<b>Regra de ouro:</b> o que não foi obtido não é o que não existe. A "
               "ferramenta nunca afirma o que não verificou, e o laudo também não deve.")
    return h


def main() -> int:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    historia = pagina_android() + [PageBreak()] + pagina_iphone_e_depois()
    SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                      topMargin=0.9 * cm, bottomMargin=1.0 * cm,
                      title="Guia de Extração Rápida — Hexis Forensics",
                      author="Hexis Forensics").build(historia, onFirstPage=rodape,
                                                      onLaterPages=rodape)
    print(f"Guia gerado: {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
