"""
Fase 3 — o caderno de aquisição (HTML selado) e o cabeçalho do manifesto
saem no idioma carimbado no caso. O corpo do manifesto (hash *caminho) é
universal e nunca é tocado; o SHA de cada arquivo não muda.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import gerar_manifesto, ler_manifesto, localizar_manifesto  # noqa: E402
from core.idioma import definir_idioma  # noqa: E402
from services.case_service import CaseService  # noqa: E402
from services.caderno_service import gerar_caderno_html  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


FORM = {"modelo": "Galaxy A22", "lacre": "L-1", "tipo_extracao": "Lógico",
        "protocolos": [], "observacoes": ""}
DISP = {"Cor": "Preto", "Estado": "Íntegro"}


def montar(raiz, caso):
    servico = CaseService(raiz)
    pasta = servico.abrir_caso("Android", caso, "SERIAL-1")
    servico.abrir_registro_procedimento(pasta, caso, "Android", "SERIAL-1")
    servico.registrar_operador(pasta, {"nome": "Jane", "funcao": "Examiner"})
    servico.gravar_dados_do_caso(caso, {"referencia": "R-1"})
    servico.gravar_cadeia_custodia(pasta, caso, {"marca_modelo": "Galaxy A22", "lacre": "L-1"})
    (pasta / "arq.txt").write_text("conteudo", encoding="utf-8")
    servico.encerrar_registro_procedimento("1 module(s).")
    gerar_manifesto(pasta)
    return pasta


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    definir_idioma("en")
    try:
        pasta = montar(raiz, "CASE_EN")
        saida = pasta.parent / "caderno.html"
        gerar_caderno_html(pasta, FORM, DISP, saida)
        html = saida.read_text(encoding="utf-8")
        print("\n[1] Caderno de aquisição em inglês")
        checar("lang=en", '<html lang="en">' in html)
        checar("capa em inglês", "Acquisition dossier" in html)
        checar("botão Copy block", ">Copy block<" in html)
        checar("seção método em inglês", "Method used" in html)
        checar("seção integridade em inglês", "Integrity of the acquired material" in html)
        checar("seção protocolos em inglês", "verified by the tool" in html)
        checar("os oito blocos seguem lá", html.count('class="conteudo"') == 8)

        man = localizar_manifesto(pasta)
        texto_man = man.read_text(encoding="utf-8")
        print("\n[2] Manifesto em inglês (cabeçalho) e corpo intacto")
        checar("cabeçalho em inglês", "FORENSIC HASH MANIFEST (SHA-256)" in texto_man)
        checar("rótulo da pasta em inglês", "Folder analyzed:" in texto_man)
        checar("corpo (hash *caminho) continua legível", "arq.txt" in ler_manifesto(man))
    finally:
        definir_idioma("pt")

    print("\n[3] Português — inalterado")
    pasta_pt = montar(raiz, "CASE_PT")
    saida_pt = pasta_pt.parent / "caderno.html"
    gerar_caderno_html(pasta_pt, FORM, DISP, saida_pt)
    html_pt = saida_pt.read_text(encoding="utf-8")
    checar("lang=pt-BR", '<html lang="pt-BR">' in html_pt)
    checar("capa em português", "Caderno de aquisição" in html_pt)
    checar("botão Copiar bloco", ">Copiar bloco<" in html_pt)
    checar("manifesto em português",
           "MANIFESTO FORENSE DE HASHES" in localizar_manifesto(pasta_pt).read_text(encoding="utf-8"))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
