"""
Fase 4 — o VEREDITO do desfecho (resumo, rótulo e a moldura do
desfecho_da_coleta.txt, selado) sai no idioma carimbado; a moldura do console
de execução tem catálogo. A narração interna dos módulos segue PT (dado).
PT idêntico byte a byte ao de antes.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.desfecho import (  # noqa: E402
    descrever_execucao, gravar_desfecho, FALHA, SUCESSO,
)
from core.idioma import traduzir  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


REG = [("m1", "Módulo A", True, "ok", {}), ("m2", "Módulo B", False, "sem dado", {})]
d = descrever_execucao(REG)

print("\n[1] Resumo em PT idêntico ao de antes")
checar("resumo PT",
       d.resumo_no_idioma("pt") == "2 módulo(s) executado(s): 1 concluído(s), 1 sem obter dado.")
vazio = descrever_execucao([])
checar("resumo vazio PT",
       vazio.resumo_no_idioma("pt") == "Nenhum módulo foi executado nesta aquisição.")
cancel = descrever_execucao(REG, cancelada=True)
checar("resumo cancelada PT termina igual",
       cancel.resumo_no_idioma("pt").endswith("todos os módulos.."))

print("\n[2] Resumo e rótulos em EN")
checar("resumo EN",
       d.resumo_no_idioma("en") == "2 module(s) run: 1 completed, 1 with no data obtained.")
checar("rótulo falha EN", d.modulos[1].rotulo_no_idioma("en") == "No data obtained")
checar("rótulo sucesso EN", d.modulos[0].rotulo_no_idioma("en") == "Completed")
checar("rótulo falha PT (idêntico)", d.modulos[1].rotulo_no_idioma("pt") == "Não obteve dado")

print("\n[3] O desfecho_da_coleta.txt selado sai no idioma passado")
with tempfile.TemporaryDirectory() as tmp:
    aq_en = Path(tmp) / "en"
    aq_en.mkdir()
    gravar_desfecho(aq_en, d, "en")
    txt_en = (aq_en / "desfecho" / "desfecho_da_coleta.txt").read_text(encoding="utf-8")
    checar("título EN", "COLLECTION OUTCOME" in txt_en)
    checar("status EN", "Status:" in txt_en)
    checar("como ler EN", "HOW TO READ THIS RECORD" in txt_en)
    checar("nota de falha EN", "'No data obtained' means that material was not acquired." in txt_en)

    aq_pt = Path(tmp) / "pt"
    aq_pt.mkdir()
    gravar_desfecho(aq_pt, d, "pt")
    txt_pt = (aq_pt / "desfecho" / "desfecho_da_coleta.txt").read_text(encoding="utf-8")
    checar("título PT", "DESFECHO DA COLETA" in txt_pt)
    checar("como ler PT", "COMO LER ESTE REGISTRO" in txt_pt)
    checar("nota de falha PT idêntica",
           "'Não obteve dado' significa que aquele material não foi adquirido." in txt_pt)

print("\n[4] A moldura do console de execução tem catálogo EN")
checar("cabeçalho de módulo EN",
       traduzir("xs_modulo_cabecalho", "en", indice=1, total=3, nome="X") == "[MODULE 1/3] X")
checar("ignorado EN", traduzir("xs_ignorado", "en", motivo="m") == "[SKIPPED] m")
checar("desfecho EN", traduzir("xs_desfecho", "en", resumo="r") == "[OUTCOME] r")
checar("nota do desfecho EN em inglês",
       "does NOT mean absence of data" in traduzir("xs_desfecho_nota", "en"))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
