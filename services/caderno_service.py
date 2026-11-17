"""
Caderno de aquisição: blocos prontos para o perito colar no laudo dele.

A ferramenta deixa de entregar o documento pronto e passa a entregar
**material verificado**. A razão é dupla, e a segunda é a que importa: o
laudo é ato técnico assinado por quem o subscreve, e um documento gerado
inteiro convida o examinador a assinar texto que não redigiu. A ferramenta
não deve afirmar — deve fornecer o que sustenta a afirmação de quem assina.

Por que HTML, e não texto ou Markdown: tabela em texto puro colada no Word
vira sopa de espaços. HTML renderizado no navegador e copiado dali chega ao
editor com as tabelas inteiras, e não exige biblioteca nenhuma para ser
gerado — é só texto.

**O selo de rastreio é o que impede o copiar-e-colar de romper a doutrina.**
Enquanto o documento era gerado pela ferramenta, cada afirmação vinha de um
arquivo selado dentro da aquisição e ninguém podia alterá-la sem alterar a
evidência. Colado no editor, o texto passa a ser editável. Por isso cada
bloco termina com a aquisição de origem e o SHA-256 do manifesto: quem ler
o laudo consegue conferir se o que está lá bate com o que foi coletado.

Nada aqui é reimplementado. Os blocos leem os mesmos registros que o
gerador de PDF lê — `metodo_declarado`, `desfecho_da_coleta`,
`manifesto_hashes`, mais o que os módulos apuraram do aparelho. Uma segunda
fonte da mesma informação já causou defeito neste projeto.
"""

from __future__ import annotations

import datetime
import html
import json
from pathlib import Path

from core.aparelho import ler_caracteristicas
from core.operador import ler_da_aquisicao as ler_operador_da_aquisicao
from core.desfecho import ler_desfecho
from core.hashing import (
    PREFIXO_CONFERENCIA,
    calcular_sha256,
    ler_manifesto,
    localizar_manifesto,
)
from core.metodo import ler_metodo, resumir_modulos
from core.protocolos import desdobrar, exige_especificacao, verificar_automaticos
from core.case import (
    NOME_CADEIA_CUSTODIA,
    idioma_para_selar,
    rotulos_do_dispositivo,
)
from core.idioma import idioma_ativo, traduzir
from core.versao import descrever_ambiente

def modalidade_sugerida(pasta_aquisicao) -> str:
    """
    Sugestão de modalidade de acesso, lida dos módulos daquela aquisição.

    Reexportada pela mesma razão de `perguntas_dos_protocolos`: a interface
    monta o formulário sem importar nada de `core`. Vazio significa que não
    há registro — e o formulário precisa saber a diferença entre isso e uma
    sugestão legítima.
    """
    return resumir_modulos(pasta_aquisicao)


SEM_INFORMACAO = "Não informado"
TRACO = "—"


def escapar(valor) -> str:
    """Escapa para HTML. Vazio vira travessão, nunca string vazia."""
    texto = str(valor).strip() if valor is not None else ""
    return html.escape(texto) if texto else TRACO


def tabela(cabecalho, linhas, larguras=None) -> str:
    """
    Tabela HTML com bordas explícitas.

    As bordas vão em CSS de elemento, e não em classe: o Word preserva o
    que está computado no elemento copiado e descarta boa parte das regras
    de folha externa. Tabela sem borda no laudo colado é o mesmo defeito
    que motivou sair do texto puro.
    """
    cols = ""
    if larguras:
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in larguras) + "</colgroup>"

    ths = "".join(f"<th>{html.escape(c)}</th>" for c in cabecalho)
    trs = []
    for linha in linhas:
        tds = "".join(f"<td>{celula}</td>" for celula in linha)
        trs.append(f"<tr>{tds}</tr>")
    return (
        f'<table>{cols}<thead><tr>{ths}</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody></table>'
    )


def _bloco(indice: int, titulo: str, corpo: str, rastreio: str, idioma: str) -> str:
    """Um bloco copiável, com o cabeçalho (não copiado) e o selo de rastreio."""
    ident = f"bloco{indice}"
    return f"""
<section class="bloco">
  <div class="cabeca">
    <h2>{html.escape(titulo)}</h2>
    <span class="acoes">
      <button class="copiar" onclick="copiar('{ident}', this)">{html.escape(traduzir("cad_btn_copiar", idioma))}</button>
      <button class="pdf" onclick="imprimir(this)">{html.escape(traduzir("cad_btn_pdf", idioma))}</button>
    </span>
  </div>
  <div class="conteudo" id="{ident}">
    {corpo}
    <p class="rastreio">{rastreio}</p>
  </div>
</section>
"""


def _rastreio(pasta_aquisicao: Path, hash_manifesto: str) -> str:
    """
    Linha que ancora o bloco à aquisição de onde saiu.

    Sem ela, o texto colado no editor perde o vínculo com a coleta e volta
    a ser afirmação sem lastro — exatamente o que o documento gerado pela
    ferramenta evitava.
    """
    if hash_manifesto:
        return (
            f"Extraído de <b>{html.escape(pasta_aquisicao.name)}</b> — "
            f"SHA-256 do manifesto: <span class='mono'>{html.escape(hash_manifesto)}</span>"
        )
    return (
        f"Extraído de <b>{html.escape(pasta_aquisicao.name)}</b> — "
        "esta aquisição <b>não possui manifesto de integridade</b>, e nada se pode "
        "afirmar aqui sobre a preservação do material."
    )


# ---------------------------------------------------------------------------
# Blocos
# ---------------------------------------------------------------------------
def _operador_da_aquisicao(pasta_aquisicao: Path) -> str:
    """
    O operador como ficou gravado NA AQUISIÇÃO, sob o selo. Não vem de
    formulário: o caderno é escrito dias depois, e quem o gera pode não ser
    quem coletou.
    """
    idi = idioma_para_selar(pasta_aquisicao)
    lido = ler_operador_da_aquisicao(pasta_aquisicao)
    if lido is None:
        return traduzir("cad_op_nao_registrado", idi)
    operador, conta = lido
    return traduzir("cad_op_resumo", idi,
                    resumo=operador.resumo(), conta=conta or traduzir("cad_op_nao_apurada", idi))


def _dados_do_caso_na_aquisicao(pasta_aquisicao: Path) -> list:
    """
    (rótulo, valor) dos dados do CASO como gravados nesta aquisição, sob o
    selo. Tudo o que a cadeia de custódia traz e não é da peça nem de
    controle — o que serve tanto ao registro de hoje quanto aos antigos.
    """
    idi = idioma_para_selar(pasta_aquisicao)
    fora = {rotulo for _, rotulo in rotulos_do_dispositivo(idi)} | {
        "Tipo Projeto", traduzir("sl_fotos_anexas", idi)}
    try:
        texto = (pasta_aquisicao / NOME_CADEIA_CUSTODIA).read_text(encoding="utf-8")
    except OSError:
        return []
    pares = []
    for linha in texto.splitlines():
        if ":" not in linha or linha.startswith("="):
            continue
        rotulo, valor = linha.split(":", 1)
        if rotulo.strip() not in fora:
            pares.append((rotulo.strip(), valor.strip()))
    return pares


def _corpo_identificacao_exame(pasta_aquisicao: Path, dados_form: dict) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    ambiente = descrever_ambiente()
    linhas = [
        [escapar(rotulo), escapar(valor)]
        for rotulo, valor in _dados_do_caso_na_aquisicao(pasta_aquisicao)
    ] + [
        [traduzir("cad_ie_l_aquisicao", idi), escapar(pasta_aquisicao.name)],
        [traduzir("cad_ie_l_operador", idi), escapar(_operador_da_aquisicao(pasta_aquisicao))],
        [traduzir("cad_ie_l_modalidade", idi), escapar(dados_form.get("tipo_extracao"))],
        [traduzir("cad_ie_l_ferramenta", idi), escapar(ambiente.get("ferramenta"))],
        [traduzir("cad_ie_l_estacao", idi), escapar(ambiente.get("estacao"))],
        [traduzir("cad_ie_l_sistema", idi), escapar(ambiente.get("sistema"))],
    ]
    # A versão da ferramenta e o ambiente entram porque a norma cobra
    # repetibilidade e reprodutibilidade, e nenhuma das duas é aferível sem
    # saber qual versão, em que estação, produziu o resultado. O documento
    # anterior não imprimia nada disso.
    return tabela([traduzir("cad_h_parametro", idi), traduzir("cad_h_valor", idi)],
                  linhas, ["35%", "65%"])


def _corpo_identificacao_peca(pasta_aquisicao: Path, dados_form: dict, dados_disp: dict) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    partes = []
    apuradas = ler_caracteristicas(pasta_aquisicao)

    partes.append(f"<h3>{html.escape(traduzir('cad_ip_apurado_h3', idi))}</h3>")
    if apuradas.vazio:
        partes.append(traduzir("cad_ip_vazio", idi))
    else:
        partes.append(tabela(
            [traduzir("cad_h_parametro", idi), traduzir("cad_ip_h_valor_lido", idi)],
            [[escapar(rotulo), escapar(valor)] for rotulo, valor in apuradas.em_pares()],
            ["35%", "65%"],
        ))
        partes.append(traduzir("cad_ip_nota_apurado", idi))

    partes.append(f"<h3>{html.escape(traduzir('cad_ip_declarado_h3', idi))}</h3>")
    partes.append(tabela(
        [traduzir("cad_h_parametro", idi), traduzir("cad_ip_h_descricao", idi)],
        [
            [traduzir("cad_ip_l_marca", idi), escapar(dados_form.get("modelo"))],
            [traduzir("cad_ip_l_cor", idi), escapar(dados_disp.get("Cor"))],
            [traduzir("cad_ip_l_estado", idi), escapar(dados_disp.get("Estado"))],
            [traduzir("cad_ip_l_lacre", idi), escapar(dados_form.get("lacre"))],
        ],
        ["35%", "65%"],
    ))
    partes.append(traduzir("cad_ip_nota_sep", idi))
    return "".join(partes)


def _corpo_metodo(pasta_aquisicao: Path) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    metodo = ler_metodo(pasta_aquisicao)
    if metodo.vazio:
        return traduzir("cad_met_vazio", idi)
    linhas = [[escapar(m.nome), escapar(m.perfil)] for m in metodo.modulos]
    return tabela([traduzir("cad_met_h_modulo", idi), traduzir("cad_met_h_competencia", idi)],
                  linhas, ["70%", "30%"])


def _corpo_limitacoes(pasta_aquisicao: Path) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    metodo = ler_metodo(pasta_aquisicao)
    if metodo.vazio:
        return traduzir("cad_lim_vazio", idi)
    if not metodo.tem_limitacao:
        return traduzir("cad_lim_sem", idi)

    partes = [traduzir("cad_lim_intro", idi)]
    for modulo in metodo.modulos:
        if not modulo.limitacoes:
            continue
        itens = "".join(f"<li>{escapar(texto)}</li>" for texto in modulo.limitacoes)
        partes.append(f"<p><b>{escapar(modulo.nome)}</b></p><ul>{itens}</ul>")

    if metodo.tem_alteracao:
        partes.append(f"<h3>{html.escape(traduzir('cad_lim_alt_h3', idi))}</h3>")
        itens = []
        for modulo in metodo.modulos:
            for alteracao, justificativa in modulo.alteracoes:
                justif = traduzir("cad_lim_justificativa", idi, valor=escapar(justificativa))
                itens.append(f"<li>{escapar(alteracao)}<br><i>{justif}</i></li>")
        partes.append(f"<ul>{''.join(itens)}</ul>")
        partes.append(traduzir("cad_lim_nota", idi))
    return "".join(partes)


def _corpo_protocolos_ferramenta(pasta_aquisicao: Path) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    itens = verificar_automaticos(pasta_aquisicao)
    linhas = [
        [escapar(clausula), escapar(pergunta), f"<b>{escapar(resposta)}</b>", escapar(origem)]
        for clausula, pergunta, resposta, origem in itens
    ]
    return (
        traduzir("cad_pf_intro", idi)
        + tabela(
            [traduzir("cad_pf_h_clausula", idi), traduzir("cad_pf_h_requisito", idi),
             traduzir("cad_pf_h_resposta", idi), traduzir("cad_pf_h_registro", idi)],
            linhas,
            ["10%", "45%", "20%", "25%"],
        )
    )


def _corpo_protocolos_examinador(dados_form: dict, idi: str) -> str:
    protocolos = dados_form.get("protocolos") or []
    if not protocolos:
        return traduzir("cad_pe_vazio", idi)

    linhas = []
    for item in protocolos:
        clausula, pergunta, resposta, observacao = desdobrar(item)
        if resposta == "Sim" and not observacao and exige_especificacao(pergunta):
            resposta = "Sim — não especificado"
        linhas.append([
            escapar(clausula), escapar(pergunta), f"<b>{escapar(resposta)}</b>", escapar(observacao)
        ])

    partes = [
        traduzir("cad_pe_intro", idi),
        tabela(
            [traduzir("cad_pf_h_clausula", idi), traduzir("cad_pe_h_questao", idi),
             traduzir("cad_pf_h_resposta", idi), traduzir("cad_pe_h_observacao", idi)],
            linhas,
            ["10%", "40%", "20%", "30%"],
        ),
    ]
    gerais = (dados_form.get("observacoes") or "").strip()
    if gerais:
        partes.append(traduzir("cad_pe_obs_gerais", idi, valor=escapar(gerais)))
    return "".join(partes)


def _corpo_desfecho(pasta_aquisicao: Path) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    desfecho = ler_desfecho(pasta_aquisicao)
    if desfecho.vazio:
        return traduzir("cad_des_vazio", idi)

    linhas = []
    for modulo in desfecho.modulos:
        detalhe = escapar(modulo.mensagem)
        if modulo.ressalvas:
            itens = "".join(f"<li>{escapar(r)}</li>" for r in modulo.ressalvas)
            detalhe += f"<ul>{itens}</ul>"
        linhas.append([escapar(modulo.nome),
                       f"<b>{escapar(modulo.rotulo_no_idioma(idi))}</b>", detalhe])

    return (
        f"<p>{escapar(desfecho.resumo_no_idioma(idi))}</p>"
        + tabela([traduzir("cad_des_h_modulo", idi), traduzir("cad_des_h_situacao", idi),
                  traduzir("cad_des_h_resultado", idi)], linhas, ["30%", "20%", "50%"])
        + traduzir("cad_des_nota", idi)
    )


def _corpo_integridade(pasta_aquisicao: Path, hash_manifesto: str) -> str:
    idi = idioma_para_selar(pasta_aquisicao)
    manifesto = localizar_manifesto(pasta_aquisicao)
    if manifesto is None:
        return traduzir("cad_int_sem", idi)

    try:
        arquivos = ler_manifesto(manifesto)
    except (OSError, ValueError):
        arquivos = {}

    partes = [tabela(
        [traduzir("cad_h_parametro", idi), traduzir("cad_h_valor", idi)],
        [
            [traduzir("cad_int_l_algoritmo", idi), "SHA-256"],
            [traduzir("cad_int_l_manifesto", idi), escapar(manifesto.name)],
            [traduzir("cad_int_l_cobertos", idi), escapar(len(arquivos))],
            [traduzir("cad_int_l_sha", idi), f"<span class='mono'>{escapar(hash_manifesto)}</span>"],
        ],
        ["35%", "65%"],
    )]
    partes.append(traduzir("cad_int_nota", idi, manifesto=escapar(manifesto.name)))

    resultado = _ultima_conferencia(pasta_aquisicao)
    if resultado:
        partes.append(traduzir("cad_int_ultima", idi, valor=escapar(resultado)))
    else:
        partes.append(traduzir("cad_int_sem_conf", idi))
    return "".join(partes)


def _ultima_conferencia(pasta_aquisicao: Path) -> str:
    """Linha de RESULTADO do relatório de conferência mais recente, se houver."""
    relatorios = sorted(Path(pasta_aquisicao).glob(f"{PREFIXO_CONFERENCIA}*.txt"))
    if not relatorios:
        return ""
    try:
        for linha in relatorios[-1].read_text(encoding="utf-8").splitlines():
            if linha.startswith("RESULTADO:"):
                return linha.replace("RESULTADO:", "").strip()
    except OSError:
        return ""
    return ""


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------
ESTILO = """
:root { color-scheme: light; }
body { background:#f4f4f6; color:#111; margin:0; padding:24px;
       font-family:'Segoe UI',Calibri,Arial,sans-serif; font-size:14px; line-height:1.5; }
.folha { max-width:900px; margin:0 auto; }
.capa { background:#fff; border:1px solid #ccc; border-radius:6px;
        padding:20px 24px; margin-bottom:20px; }
.capa h1 { margin:0 0 6px; font-size:20px; }
.capa p { margin:6px 0; color:#333; }
.alerta { background:#fff6e5; border-left:4px solid #b8860b;
          padding:8px 12px; border-radius:0 4px 4px 0; }
.bloco { background:#fff; border:1px solid #ccc; border-radius:6px;
         margin-bottom:18px; overflow:hidden; }
.cabeca { display:flex; align-items:center; justify-content:space-between;
          gap:12px; background:#eceff3; border-bottom:1px solid #ccc; padding:10px 16px; }
.cabeca h2 { margin:0; font-size:16px; }
.acoes { display:flex; gap:8px; flex-shrink:0; }
.copiar, .pdf { color:#fff; border:0; border-radius:4px; padding:6px 14px;
                font-size:13px; cursor:pointer; white-space:nowrap; }
.copiar { background:#2b4a7d; }
.copiar:hover { background:#1d3559; }
.pdf { background:#4a5568; }
.pdf:hover { background:#2d3748; }
.conteudo { padding:16px; }
.conteudo h3 { font-size:14px; margin:14px 0 6px; }
.conteudo p { margin:8px 0; }
.conteudo ul { margin:6px 0 10px; padding-left:22px; }
.conteudo li { margin:3px 0; }
table { border-collapse:collapse; width:100%; margin:8px 0; font-size:13px; }
th, td { border:1px solid #999; padding:6px 8px; text-align:left; vertical-align:top; }
th { background:#f2f2f2; font-weight:bold; }
.mono { font-family:Consolas,'Courier New',monospace; font-size:12px; word-break:break-all; }
.nota { font-style:italic; color:#333; }
.rastreio { margin-top:14px; padding-top:8px; border-top:1px solid #ccc;
            font-size:12px; color:#333; }
@media print {
  body { background:#fff; padding:0; }
  .acoes { display:none; }
  .bloco, .capa { border:0; page-break-inside:avoid; }
  /* Isolamento de um bloco. O "imprimir seleção" do navegador nao e
     uniforme entre Chrome e Firefox, e depender dele faria o operador
     descobrir a diferenca so na hora de juntar o documento aos autos. */
  body.imprimindo-um .capa { display:none; }
  body.imprimindo-um .bloco { display:none; }
  body.imprimindo-um .bloco.alvo { display:block; }
}
"""

SCRIPT = """
function copiar(id, botao) {
  var el = document.getElementById(id);
  var sel = window.getSelection();
  var range = document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
  var ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  sel.removeAllRanges();
  // Sem clipboard API: a página abre por file://, que não é contexto
  // seguro, e navigator.clipboard não existe ali. Falhando, o bloco fica
  // selecionado e o Ctrl+C do examinador resolve.
  botao.textContent = ok ? 'Copiado' : 'Selecione e use Ctrl+C';
  var antes = botao.style.background;
  botao.style.background = ok ? '#1f7a44' : '#8a5000';
  setTimeout(function () {
    botao.textContent = 'Copiar bloco';
    botao.style.background = antes;
  }, 2200);
}

function imprimir(botao) {
  var bloco = botao.closest('.bloco');
  document.body.classList.add('imprimindo-um');
  bloco.classList.add('alvo');

  function limpar() {
    document.body.classList.remove('imprimindo-um');
    bloco.classList.remove('alvo');
    window.removeEventListener('afterprint', limpar);
  }
  // afterprint cobre o caso normal; o timeout cobre navegador que nao o
  // dispara, para a pagina nao ficar presa mostrando um bloco so.
  window.addEventListener('afterprint', limpar);
  window.print();
  setTimeout(limpar, 1500);
}
"""


def montar_documento(titulo: str, capa: str, secoes, rastreio: str, idioma: str = None) -> str:
    """
    Monta o documento HTML inteiro a partir das seções.

    Fica aqui, e não em quem chama, porque o caderno da aquisição e o de
    conteúdo precisam do mesmo esqueleto — o mesmo CSS que faz a tabela
    sobreviver à colagem no editor, o mesmo isolamento de impressão por
    bloco, o mesmo selo de rastreio. Duas implementações do mesmo HTML
    divergiriam na primeira correção feita só de um lado, e este projeto já
    pagou por uma segunda fonte da mesma informação.

    `secoes` é uma lista de `(título, corpo_html)`. `capa` é o cabeçalho
    próprio de cada caderno, que explica o que aquele documento é.
    """
    idi = idioma or idioma_ativo()
    emitido = datetime.datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
    blocos = "".join(
        _bloco(i, titulo_secao, corpo, rastreio, idi)
        for i, (titulo_secao, corpo) in enumerate(secoes, 1)
    )
    # Os rótulos dos botões no JS saem no idioma do documento. json.dumps gera
    # uma string JS válida (e escapa aspas, se houver).
    script = (
        SCRIPT
        .replace("'Copiado'", json.dumps(traduzir("cad_btn_copiado", idi)))
        .replace("'Selecione e use Ctrl+C'", json.dumps(traduzir("cad_btn_selecione", idi)))
        .replace("'Copiar bloco'", json.dumps(traduzir("cad_btn_copiar", idi)))
    )
    return f"""<!doctype html>
<html lang="{html.escape(traduzir("cad_lang", idi))}">
<head>
<meta charset="utf-8">
<title>{html.escape(titulo)}</title>
<style>{ESTILO}</style>
</head>
<body>
<div class="folha">
  <div class="capa">{capa.replace("{emitido}", html.escape(emitido))}</div>
  {blocos}
</div>
<script>{script}</script>
</body>
</html>
"""


def gerar_caderno_html(
    pasta_aquisicao: Path,
    dados_form: dict,
    dados_disp: dict,
    caminho_saida: Path,
) -> bool:
    """
    Escreve o caderno da aquisição em `caminho_saida`.

    Devolve `True` se gravou. Nenhuma seção inventa conteúdo: quando o
    registro que a sustenta não existe, o bloco diz isso — omitir faria o
    laudo silenciar sobre o que não foi verificado.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    caminho_saida = Path(caminho_saida)

    manifesto = localizar_manifesto(pasta_aquisicao)
    hash_manifesto = ""
    if manifesto is not None:
        try:
            hash_manifesto = calcular_sha256(manifesto)
        except OSError:
            hash_manifesto = ""

    idi = idioma_para_selar(pasta_aquisicao)
    rastreio = _rastreio(pasta_aquisicao, hash_manifesto)

    secoes = [
        (traduzir("cad_sec_id_exame", idi), _corpo_identificacao_exame(pasta_aquisicao, dados_form)),
        (traduzir("cad_sec_id_peca", idi),
         _corpo_identificacao_peca(pasta_aquisicao, dados_form, dados_disp)),
        (traduzir("cad_sec_metodo", idi), _corpo_metodo(pasta_aquisicao)),
        (traduzir("cad_sec_limitacoes", idi), _corpo_limitacoes(pasta_aquisicao)),
        (traduzir("cad_sec_prot_ferramenta", idi),
         _corpo_protocolos_ferramenta(pasta_aquisicao)),
        (traduzir("cad_sec_prot_examinador", idi),
         _corpo_protocolos_examinador(dados_form, idi)),
        (traduzir("cad_sec_desfecho", idi), _corpo_desfecho(pasta_aquisicao)),
        (traduzir("cad_sec_integridade", idi),
         _corpo_integridade(pasta_aquisicao, hash_manifesto)),
    ]

    documento = montar_documento(
        titulo=traduzir("cad_titulo_doc", idi, nome=pasta_aquisicao.name),
        capa=traduzir("cad_capa", idi, nome=html.escape(pasta_aquisicao.name)),
        secoes=secoes,
        rastreio=rastreio,
        idioma=idi,
    )

    try:
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        caminho_saida.write_text(documento, encoding="utf-8")
        return True
    except OSError:
        return False
