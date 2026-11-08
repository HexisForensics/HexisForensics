"""
Testes do caderno de conteudo.

Mesma troca que o caderno da aquisicao: a apresentacao sai em HTML, em
blocos que o analista copia para o documento que assina. As planilhas
continuam ao lado e nao sao substituidas -- sao elas o dado para cruzar e
filtrar.

O bloco [3] guarda o defeito que a mudanca CRIA, e que o PDF nao tinha. O
aviso de divergencia de hash vivia no topo do documento, e isso bastava
enquanto o documento era lido inteiro. Aqui cada bloco e copiado sozinho:
uma tabela de SMS colada num relatorio, sem o alerta que ficou la atras,
apresentaria como integro um conteudo cuja origem nao confere mais com o
selo da coleta. Por isso o alerta e repetido DENTRO de cada artefato
divergente.

O bloco [2] e o de sempre: "nao coletado" e "nenhum registro" sao fatos
diferentes, e so o segundo diz algo sobre o aparelho.
"""
import html.parser
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao
from core.hashing import gerar_manifesto
from services.relatorio_service import FONTES_BANCO, NOME_CADERNO, RelatorioService

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


class Validador(html.parser.HTMLParser):
    VAZIAS = {"meta", "br", "col", "link", "img", "hr", "input"}

    def __init__(self):
        super().__init__()
        self.pilha = []
        self.erros = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VAZIAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if not self.pilha or self.pilha[-1] != tag:
            self.erros.append(tag)
        else:
            self.pilha.pop()


SMS_BRUTO = (
    "Row: 0 _id=1, address=+5511988887777, date=1787513890741, read=0, type=1, "
    "body=Oi, tudo bem? Vamos combinar aquilo\n"
    "Row: 1 _id=2, address=+5511977776666, date=1787513890843, read=1, type=2, "
    "body=Segunda mensagem, com virgula, para testar\n"
)

CHAMADAS_BRUTO = (
    "Row: 0 _id=1, number=+5511911112222, date=1787513890891, duration=42, type=1, "
    "name=Contato Um\n"
)


def montar_aquisicao(raiz, identificador, com_sms=True, com_chamadas=True):
    """Monta uma aquisicao com conteudo bruto e a sela."""
    aquisicao = criar_pasta_aquisicao(raiz, identificador, "Android")
    if com_sms:
        (aquisicao / "sms").mkdir()
        (aquisicao / "sms" / "sms_todas.txt").write_text(SMS_BRUTO, encoding="utf-8")
    if com_chamadas:
        (aquisicao / "contacts_calls").mkdir()
        (aquisicao / "contacts_calls" / "registro_chamadas_bruto.txt").write_text(
            CHAMADAS_BRUTO, encoding="utf-8"
        )
    gerar_manifesto(aquisicao)
    return aquisicao


def ler_caderno(resultado):
    caderno = [c for c in resultado.arquivos_gerados if c.name == NOME_CADERNO]
    return caderno[0].read_text(encoding="utf-8") if caderno else ""


# ---------------------------------------------------------------------------
print("\n[1] O caderno sai ao lado das planilhas, sem substitui-las")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_001")
    resultado = RelatorioService.gerar(aquisicao)

    nomes = {c.name for c in resultado.arquivos_gerados}
    checar("o caderno HTML e gerado", NOME_CADERNO in nomes)
    checar("as planilhas continuam sendo geradas", "sms.csv" in nomes)
    checar("e a de chamadas tambem", "chamada.csv" in nomes)
    checar("a procedencia continua", "PROCEDENCIA.txt" in nomes)

    texto = ler_caderno(resultado)
    validador = Validador()
    validador.feed(texto)
    checar("as tags fecham na ordem", not validador.erros and not validador.pilha)

    checar("ha um bloco por artefato mais os fixos", texto.count('class="conteudo"') >= 5)
    checar("todo bloco tem selo de rastreio",
           texto.count('class="rastreio"') == texto.count('class="conteudo"'))
    checar("o selo declara a versao do normalizador", "Normalizador versão" in texto)
    checar("o caderno aponta o CSV como a relacao completa", "sms.csv</b>" in texto)
    checar("e diz que nao substitui as planilhas", "não substitui as planilhas" in texto)

    checar("o conteudo das mensagens aparece", "Vamos combinar aquilo" in texto)
    checar("inclusive o corpo com virgula, que ja quebrou o parser",
           "Segunda mensagem, com virgula, para testar" in texto)

# ---------------------------------------------------------------------------
print("\n[2] Nao coletado nao se confunde com nenhum registro")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    # Sem o modulo de chamadas executado: o artefato nao esta presente.
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_002", com_chamadas=False)
    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)

    checar("artefato ausente e declarado NAO COLETADO", "NÃO COLETADO" in texto)
    checar(
        "recusando a leitura de ausencia no aparelho",
        "Não é ausência de dado no aparelho" in texto,
    )
    checar(
        "e o caderno explica a distincao ao leitor",
        "é ausência de coleta" in texto,
    )
    checar("nao existe bloco de chamadas", "Registro de Chamadas —" not in texto)

# ---------------------------------------------------------------------------
print("\n[3] O alerta de divergencia viaja dentro do bloco")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_003")

    # Adultera a origem DEPOIS do selo: o hash deixa de conferir.
    (aquisicao / "sms" / "sms_todas.txt").write_text(
        SMS_BRUTO + "Row: 2 _id=3, address=+5511900000000, date=1787513890999, "
        "read=1, type=1, body=Mensagem acrescentada depois do selo\n",
        encoding="utf-8",
    )

    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)

    checar("a divergencia e detectada", len(resultado.origens_divergentes) == 1)

    # O alerta precisa estar DENTRO do bloco de SMS, e nao so no topo. Um
    # bloco copiado sozinho leva consigo o que o desqualifica.
    inicio = texto.index("Mensagens SMS —")
    fim = texto.index("</section>", inicio)
    bloco_sms = texto[inicio:fim]
    checar("o bloco de SMS carrega o alerta", "NÃO confere mais" in bloco_sms)
    checar(
        "e diz que o conteudo nao deve ser usado assim",
        "não deve ser usado" in bloco_sms,
    )

    # O bloco de chamadas nao foi adulterado: nao pode herdar o alerta.
    inicio = texto.index("Registro de Chamadas —")
    fim = texto.index("</section>", inicio)
    bloco_chamadas = texto[inicio:fim]
    checar("o bloco integro NAO recebe o alerta", "NÃO confere mais" not in bloco_chamadas)

    checar(
        "a conferencia nomeia o arquivo divergente",
        "NÃO CONFERE" in texto,
    )

# ---------------------------------------------------------------------------
print("\n[4] Sem selo, a conferencia nao vira aprovacao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_004", "Android")
    (aquisicao / "sms").mkdir()
    (aquisicao / "sms" / "sms_todas.txt").write_text(SMS_BRUTO, encoding="utf-8")
    # Sem gerar_manifesto: nao ha selo a comparar.

    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)

    checar("origem sem selo nao e reportada como conferida",
           "Sem selo a comparar" in texto)
    checar(
        "e a distincao e explicada",
        "não é o mesmo que conferir" in texto,
    )
    checar(
        "o selo do rodape declara a falta do manifesto",
        "não possui manifesto de integridade" in texto,
    )

# ---------------------------------------------------------------------------
print("\n[5] Trecho nao interpretado acusa relatorio incompleto")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_005", "Android")
    (aquisicao / "sms").mkdir()
    # O trecho vai ANTES do primeiro "Row:". Depois dele, o normalizador o
    # trataria como continuacao do corpo da mensagem anterior -- e esse e o
    # comportamento certo, porque SMS tem quebra de linha. Preambulo nao e
    # continuacao de nada, e por isso vira descarte contado. Foi um BOM
    # invisivel, e depois um aviso do adb, que motivaram essa distincao.
    (aquisicao / "sms" / "sms_todas.txt").write_text(
        "aviso do adb que nao segue o padrao de registro nenhum\n" + SMS_BRUTO,
        encoding="utf-8",
    )
    gerar_manifesto(aquisicao)

    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)

    checar("o descarte e contado", resultado.total_descartes >= 1)
    checar(
        "e o caderno declara o relatorio INCOMPLETO",
        "INCOMPLETO em relação à evidência" in texto,
    )
    checar("com o trecho por extenso", "nao segue o padrao" in texto)

with tempfile.TemporaryDirectory() as tmp:
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_006")
    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)
    checar("sem descarte, o caderno afirma isso explicitamente",
           "Nenhum registro foi descartado em silêncio" in texto)

# ---------------------------------------------------------------------------
print("\n[6] Os bancos entram no relatorio pelo mesmo caminho")
# ---------------------------------------------------------------------------
# Ate aqui os leitores de WhatsApp e de correio existiam e ninguem os
# chamava: o banco chegava a aquisicao, era selado, hasheado, e ficava
# ilegivel. Este bloco cobre a fiacao.
def montar_msgstore(pasta: Path) -> Path:
    """msgstore.db no caminho que o dump do sistema de arquivos produz."""
    bancos = pasta / "filesystem" / "data_apps" / "com.whatsapp" / "databases"
    bancos.mkdir(parents=True)
    caminho = bancos / "msgstore.db"
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE jid(_id INTEGER PRIMARY KEY, raw_string TEXT)")
    c.execute("CREATE TABLE chat(_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT)")
    c.execute(
        "CREATE TABLE message(_id INTEGER PRIMARY KEY, chat_row_id INTEGER, "
        "from_me INTEGER, text_data TEXT, message_type INTEGER, timestamp INTEGER, "
        "sender_jid_row_id INTEGER)"
    )
    c.execute("INSERT INTO jid VALUES (1, '5511911112222@s.whatsapp.net')")
    c.execute("INSERT INTO chat VALUES (1, 1, NULL)")
    c.execute(
        "INSERT INTO message VALUES (1, 1, 0, 'Combinado para amanha', 0, 1787513890741, NULL)"
    )
    c.execute("INSERT INTO message VALUES (2, 1, 1, NULL, 1, 1787513891741, NULL)")
    c.commit()
    c.close()
    return caminho


with tempfile.TemporaryDirectory() as tmp:
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_007", com_chamadas=False)
    banco = montar_msgstore(aquisicao)
    gerar_manifesto(aquisicao)

    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)
    nomes = {c.name for c in resultado.arquivos_gerados}

    checar("o msgstore e localizado por busca, sem caminho fixo",
           any(a.chave == "whatsapp" and a.presente for a in resultado.artefatos))
    checar("as mensagens entram na contagem", resultado.total_registros >= 2)
    checar("a planilha do WhatsApp e gerada", "whatsapp.csv" in nomes)
    checar("e o caderno ganha o bloco", "WhatsApp — Mensagens" in texto)
    checar("com a mensagem de texto", "Combinado para amanha" in texto)
    checar("e a midia declarada como midia", "(imagem)" in texto)

    whatsapp = [a for a in resultado.artefatos if a.chave == "whatsapp"][0]
    checar("o banco e conferido contra o selo", whatsapp.confere_com_o_selo is True)
    checar("e o caminho registrado e o real dentro da aquisicao",
           whatsapp.caminho_relativo.endswith("com.whatsapp/databases/msgstore.db"))

    # A leitura abre o banco, e abrir um SQLite pode altera-lo. O original
    # dentro da aquisicao selada nao pode ter sido tocado.
    from core.hashing import calcular_sha256

    checar("o banco na aquisicao segue conferindo com o selo apos a leitura",
           calcular_sha256(banco) == whatsapp.sha256)

with tempfile.TemporaryDirectory() as tmp:
    # Sem banco nenhum: o artefato existe assim mesmo, marcado como NAO
    # COLETADO. Omiti-lo faria o leitor concluir que nao havia WhatsApp,
    # quando o modulo que traz o banco pode nem ter sido executado.
    aquisicao = montar_aquisicao(Path(tmp) / "extracoes", "CASO_008")
    resultado = RelatorioService.gerar(aquisicao)
    texto = ler_caderno(resultado)

    chaves = {a.chave for a in resultado.artefatos}
    checar("o artefato de WhatsApp existe mesmo sem banco", "whatsapp" in chaves)
    checar("o de correio tambem", "email" in chaves)

    ausentes = [a for a in resultado.artefatos if a.chave in ("whatsapp", "email")]
    checar("nenhum deles e dado como presente",
           all(not a.presente for a in ausentes))
    checar("e o caderno declara NAO COLETADO", "NÃO COLETADO" in texto)
    checar(
        "dizendo ONDE se procurou, para a busca poder ser conferida",
        FONTES_BANCO[0][2][0] in texto,
    )

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
