"""
Testes do caderno de aquisicao.

A ferramenta deixou de entregar o laudo pronto e passou a entregar blocos
que o perito copia para o documento que ele assina. A troca resolve um
problema e cria outro, e os dois estao aqui.

Resolve: laudo e ato tecnico de quem o subscreve, e documento gerado
inteiro convida o examinador a assinar texto que nao redigiu.

Cria: enquanto a ferramenta gerava o documento, cada afirmacao vinha de um
arquivo selado e ninguem podia altera-la sem alterar a evidencia. Colado no
editor, o texto vira editavel. O bloco [3] guarda a defesa contra isso -- o
selo de rastreio em CADA bloco, com a aquisicao de origem e o SHA-256 do
manifesto. Bloco sem selo e afirmacao sem lastro.

O bloco [2] e o de sempre: registro ausente nao pode virar silencio. Uma
aquisicao sem manifesto, sem metodo ou sem desfecho tem que produzir um
caderno que DIZ que nao tem, em vez de omitir a secao -- omitir faria o
laudo silenciar sobre o que nao foi verificado.
"""
import html.parser
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

import core.android.extractors  # noqa: F401  (registra os extratores)
import core.computador.extractors  # noqa: F401
from core.case import criar_pasta_aquisicao
from core.hashing import gerar_manifesto
from core.metodo import descrever, gravar_metodo
from services.caderno_service import gerar_caderno_html, modalidade_sugerida
from services.extraction_service import listar_extratores
from services.laudo_service import perguntas_dos_protocolos

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


class Validador(html.parser.HTMLParser):
    """Confere que as tags fecham na ordem. HTML torto cola torto."""

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


def montar_protocolos(respostas, observacoes):
    return [
        (c, p, r, o)
        for (c, p), r, o in zip(perguntas_dos_protocolos(), respostas, observacoes)
    ]


FORM_BASE = {
    "natureza": "Teste",
    "operador": "",
    "modelo": "Aparelho de teste",
    "lacre": "000123",
    "tipo_extracao": "Lógico",
    "protocolos": [],
    "observacoes": "",
}
DISP_BASE = {"Cor": "Preto", "Estado": "Íntegro"}


def gerar(pasta, form=None, disp=None):
    """Gera o caderno e devolve o texto."""
    saida = Path(pasta).parent / "caderno.html"
    dados = dict(FORM_BASE)
    dados.update(form or {})
    ok = gerar_caderno_html(pasta, dados, dict(DISP_BASE, **(disp or {})), saida)
    return ok, saida.read_text(encoding="utf-8") if ok else ""


# ---------------------------------------------------------------------------
print("\n[1] O caderno sai bem formado e com os blocos separados")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_001", "Android")
    (aquisicao / "arquivo.txt").write_text("conteudo", encoding="utf-8")
    gerar_manifesto(aquisicao)

    ok, texto = gerar(aquisicao)
    checar("o caderno e gravado", ok)

    validador = Validador()
    validador.feed(texto)
    checar("as tags fecham na ordem", not validador.erros and not validador.pilha)

    checar("ha oito blocos copiaveis", texto.count('class="conteudo"') == 8)
    checar("cada bloco tem botao de copiar", texto.count("onclick=\"copiar(") == 8)
    checar("e botao de PDF proprio", texto.count("onclick=\"imprimir(this)\"") == 8)
    checar("o caderno diz que NAO e o laudo", "não é o laudo" in texto)

# ---------------------------------------------------------------------------
print("\n[2] Registro ausente e declarado, nunca omitido")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    # Aquisicao crua: sem manifesto, sem metodo, sem desfecho, sem nada
    # apurado do aparelho. O caderno tem de sair mesmo assim, dizendo o que
    # falta -- omitir a secao faria o laudo silenciar sobre o nao verificado.
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_002", "Android")

    ok, texto = gerar(aquisicao)
    checar("o caderno sai mesmo sem registro nenhum", ok)
    checar("ainda com os oito blocos", texto.count('class="conteudo"') == 8)

    checar(
        "sem manifesto, nao afirma integridade",
        "não possui manifesto de integridade" in texto,
    )
    checar(
        "sem metodo, diz que o registro nao foi localizado",
        "registro de método desta aquisição não foi localizado" in texto,
    )
    checar(
        "sem desfecho, diz que o resultado nao pode ser reproduzido",
        "registro de desfecho desta aquisição não foi localizado" in texto,
    )
    checar(
        "sem caracteristica apurada, recusa a conclusao negativa",
        "não é ausência de característica no dispositivo" in texto,
    )
    checar(
        "e sem protocolos preenchidos, diz isso",
        "não foram preenchidos" in texto,
    )

# ---------------------------------------------------------------------------
print("\n[3] O selo de rastreio ancora cada bloco a aquisicao")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_003", "Computador")
    (aquisicao / "arquivo.txt").write_text("conteudo", encoding="utf-8")
    manifesto = gerar_manifesto(aquisicao)

    from core.hashing import calcular_sha256

    esperado = calcular_sha256(manifesto)

    ok, texto = gerar(aquisicao)
    checar("ha um selo por bloco", texto.count('class="rastreio"') == 8)
    checar("o selo nomeia a aquisicao", texto.count(aquisicao.name) >= 8)
    checar("e traz o SHA-256 do manifesto de verdade", texto.count(esperado) >= 8)
    checar(
        "o caderno pede que o selo seja mantido ao colar",
        "Mantenha essa linha ao colar" in texto,
    )

with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_004", "Computador")
    ok, texto = gerar(aquisicao)
    checar(
        "sem manifesto, o selo diz que nada se pode afirmar",
        texto.count("nada se pode") >= 8,
    )

# ---------------------------------------------------------------------------
print("\n[4] A resposta incompleta do examinador aparece como incompleta")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_005", "Android")
    gerar_manifesto(aquisicao)

    # Item 3 pede "Especificar" e foi respondido "Sim" sem observacao. Um
    # "Sim" liso ali aparentaria resposta inteira.
    protocolos = montar_protocolos(
        ["Sim", "Não", "Sim", "Sim", "Sim", "Sim"],
        ["decisão anexada", "recebido desligado", "", "lacre íntegro", "", "conectado à estação"],
    )
    ok, texto = gerar(aquisicao, {"protocolos": protocolos})

    checar("silencio na especificacao fica visivel", "Sim — não especificado" in texto)
    checar("resposta com observacao sai inteira", "conectado à estação" in texto)
    checar(
        "o bloco avisa que 'Nao' nao e irregularidade",
        "não indica irregularidade" in texto,
    )

# ---------------------------------------------------------------------------
print("\n[5] O ambiente do exame chega ao caderno")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_006", "Android")
    gerar_manifesto(aquisicao)
    ok, texto = gerar(aquisicao)

    # A norma cobra repetibilidade e reprodutibilidade, e nenhuma das duas e
    # afericavel sem saber qual versao, em que estacao, produziu o resultado.
    # O documento anterior nao imprimia nada disso.
    from core.versao import identificacao_ferramenta

    checar("a versao da ferramenta consta", identificacao_ferramenta() in texto)
    checar("a estacao forense consta", "Estação forense" in texto)
    checar("e o sistema da estacao", "Sistema da estação" in texto)

# ---------------------------------------------------------------------------
print("\n[6] A modalidade vem do que a aquisicao registrou")
# ---------------------------------------------------------------------------
# O campo trazia a constante "Lógico (Backup ADB / API do Sistema)",
# sempre, sob um rotulo que dizia "Pre-detectado". Uma imagem bit-a-bit de
# volume, sem ADB nenhum envolvido, saia no documento descrita como backup
# logico via ADB -- e quem aceitasse o padrao assinava metodo que nao foi o
# empregado. Mesmo defeito do hash inventado e das perguntas pre-marcadas:
# um padrao plausivel que o operador nao tem motivo para questionar.
CONSTANTE_ANTIGA = "Lógico (Backup ADB / API do Sistema)"

with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_008", "Computador")
    modulos = [
        c for c in listar_extratores("Computador") if c.id == "computador_imagem_fisica"
    ]
    gravar_metodo(aquisicao, descrever(modulos))

    sugestao = modalidade_sugerida(aquisicao)
    checar("a modalidade sai do metodo declarado", sugestao == "Imagem do Volume (Bit-a-Bit)")
    checar("e nao da constante antiga", sugestao != CONSTANTE_ANTIGA)
    checar("nem menciona ADB numa aquisicao de computador", "ADB" not in sugestao)

with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_009", "Android")
    modulos = [
        c for c in listar_extratores("Android") if c.id in ("android_sms", "android_whatsapp")
    ]
    gravar_metodo(aquisicao, descrever(modulos))

    sugestao = modalidade_sugerida(aquisicao)
    checar("com varios modulos, todos aparecem", sugestao.count(";") == len(modulos) - 1)
    checar("na ordem em que foram declarados", sugestao.startswith(modulos[0].nome_exibicao))

with tempfile.TemporaryDirectory() as tmp:
    # Sem registro de metodo, nada e sugerido. Oferecer palpite aqui e o
    # defeito; o campo fica vazio e o formulario avisa.
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_010", "Android")
    checar("sem metodo registrado, nada e sugerido", modalidade_sugerida(aquisicao) == "")

# O defeito morava no formulário, e o teste acima cobre o serviço. Esta
# guarda fecha o outro lado: a constante nao pode voltar a ser digitada no
# codigo da interface. Linhas de comentario ficam de fora da busca --
# explicar o defeito corrigido e justamente o que evita que ele volte.
codigo_formulario = [
    linha
    for linha in (RAIZ_PROJETO / "ui" / "widgets" / "caderno_form_dialog.py")
    .read_text(encoding="utf-8")
    .splitlines()
    if not linha.strip().startswith("#")
]
checar(
    "a constante nao volta ao codigo do formulario",
    not any(CONSTANTE_ANTIGA in linha for linha in codigo_formulario),
)
checar(
    "e o rotulo nao promete deteccao que nao existe",
    not any("Pré-detectado" in linha for linha in codigo_formulario),
)

# ---------------------------------------------------------------------------
print("\n[7] Conteudo de terceiro nao injeta HTML")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    aquisicao = criar_pasta_aquisicao(Path(tmp) / "extracoes", "CASO_007", "Android")
    gerar_manifesto(aquisicao)

    # O modelo do aparelho e a observacao do examinador sao texto digitado.
    # Sem escape, um "<b>" no cadastro viraria formatacao no caderno, e um
    # "</table>" quebraria o documento inteiro.
    ok, texto = gerar(
        aquisicao,
        {
            "modelo": "<b>Modelo</b> & </table><script>alert(1)</script>",
            "protocolos": montar_protocolos(
                ["Sim"] * 6, ["<i>obs</i>", "", "", "", "", ""]
            ),
        },
    )
    checar("a marcacao digitada e escapada", "&lt;b&gt;Modelo&lt;/b&gt;" in texto)
    checar("o e comercial tambem", "&amp;" in texto)
    checar("nenhum script de terceiro entra", "<script>alert(1)</script>" not in texto)

    validador = Validador()
    validador.feed(texto)
    checar("e o documento continua fechando certo", not validador.erros and not validador.pilha)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
