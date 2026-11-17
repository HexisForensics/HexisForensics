"""
Fase 3 — o relatório de conferência de integridade (conferencia_integridade_*.txt)
sai no idioma CARIMBADO no caso, como o manifesto que ele confere. O corpo
com os nomes dos arquivos é dado e nunca é traduzido. Caso legado (sem
carimbo) e pasta fora de um caso continuam em português, sem mudar um byte.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import conferir_manifesto, gerar_manifesto  # noqa: E402
from core.idioma import definir_idioma  # noqa: E402
from services.case_service import CaseService  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


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


def relatorio_de(pasta):
    return sorted(pasta.glob("conferencia_integridade_*.txt"))[-1].read_text(encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    definir_idioma("en")
    try:
        pasta = montar(raiz, "CASE_EN")
        res = conferir_manifesto(pasta)
        rel = relatorio_de(pasta)
        print("\n[1] Caso selado em inglês — relatório em inglês")
        checar("é íntegro", res.integro is True)
        checar("título em inglês", "INTEGRITY VERIFICATION (SHA-256)" in rel)
        checar("rótulo da pasta em inglês", "Folder verified:" in rel)
        checar("rótulo dos selos em inglês", "Seals in folder:" in rel)
        checar("resultado ÍNTEGRO em inglês", "RESULT: INTACT:" in rel)
        checar("rodapé em inglês", "Intact files:" in rel)
        checar("o resumo gravado é o do caso (inglês)", "INTACT:" in res.resumo_no_idioma("en"))

        # Divergência: altero o arquivo depois do selo e confiro de novo.
        (pasta / "arq.txt").write_text("outro", encoding="utf-8")
        res2 = conferir_manifesto(pasta)
        rel2 = relatorio_de(pasta)
        print("\n[2] Divergência em inglês")
        checar("não é mais íntegro", res2.integro is False)
        checar("resultado DISCREPANCIES em inglês", "RESULT: DISCREPANCIES:" in rel2)
        checar("seção de alterados em inglês", "FILES ALTERED SINCE COLLECTION" in rel2)
        checar("nota de alterados em inglês", "CHANGED after the manifest" in rel2)
        checar("o arquivo alterado é nomeado", "arq.txt" in rel2)
    finally:
        definir_idioma("pt")

    print("\n[3] Português — inalterado (byte a byte no texto fixo)")
    pasta_pt = montar(raiz, "CASE_PT")
    res_pt = conferir_manifesto(pasta_pt)
    rel_pt = relatorio_de(pasta_pt)
    checar("título em português", "CONFERÊNCIA DE INTEGRIDADE (SHA-256)" in rel_pt)
    checar("rótulo da pasta em português", "Pasta conferida:" in rel_pt)
    checar("resultado ÍNTEGRO em português", "RESULTADO: ÍNTEGRO:" in rel_pt)
    checar("rodapé em português", "Arquivos íntegros:" in rel_pt)

    print("\n[4] Pasta sem caso.json — cai para português")
    with tempfile.TemporaryDirectory() as td:
        solta = Path(td)
        (solta / "x.txt").write_text("y", encoding="utf-8")
        gerar_manifesto(solta)
        conferir_manifesto(solta)
        rel_solta = relatorio_de(solta)
        checar("título em português na pasta solta",
               "CONFERÊNCIA DE INTEGRIDADE (SHA-256)" in rel_solta)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
