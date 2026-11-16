"""
Fase 3 — o registro do procedimento é SELADO no idioma do caso, e lido de
volta por esse idioma. O risco travado: um diário escrito em inglês, lido
por título em português, faria o laudo e a verificação de protocolos da ISO
27037 declararem "Registro não localizado" sobre algo que ESTÁ no registro —
ambiente, decisão, alteração e relógio virariam ausência falsa.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import gerar_manifesto  # noqa: E402
from core.idioma import definir_idioma  # noqa: E402
from core.protocolos import NAO_LOCALIZADO, verificar_automaticos  # noqa: E402
from services.case_service import CaseService  # noqa: E402
from services.dossie_service import montar_dossie  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar(raiz, caso, lacre):
    servico = CaseService(raiz)
    pasta = servico.abrir_caso("Android", caso, "SERIAL-" + lacre)
    servico.abrir_registro_procedimento(pasta, caso, "Android", "SERIAL-" + lacre)
    servico.registrar_operador(pasta, {"nome": "Jane", "funcao": "Examiner"})
    servico.registrar_ambiente("1.0.41")
    servico.registrar_relogio("Device clock 12s behind the workstation.")
    servico.registrar_decisao("Physical extraction not performed", "device without root")
    servico.registrar_alteracao("USB debugging enabled", "required to reach the device")
    servico.gravar_dados_do_caso(caso, {"referencia": "R-" + lacre})
    servico.gravar_cadeia_custodia(pasta, caso, {"marca_modelo": "Galaxy A22", "lacre": lacre})
    servico.encerrar_registro_procedimento("1 module(s).")
    gerar_manifesto(pasta)
    return pasta


def respostas(pasta):
    return {clausula: resposta for clausula, _, resposta, _ in verificar_automaticos(pasta)}


def resposta_do_relogio(pasta):
    # A cláusula 6.6 aparece duas vezes (relógio e identificadores); aqui só o relógio.
    for _, pergunta, resposta, _ in verificar_automaticos(pasta):
        if "relógio" in pergunta:
            return resposta
    return None


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    definir_idioma("en")
    try:
        pasta_en = montar(raiz, "CASE_EN", "L-EN")
        bruto = (pasta_en / "registro_procedimento.txt").read_text(encoding="utf-8")
        print("\n[1] Registro SELADO em inglês")
        checar("título em inglês", "FORENSIC ACQUISITION PROCEDURE RECORD" in bruto)
        checar("cabeçalho Device em inglês", "Device:      SERIAL-L-EN" in bruto)
        checar("evento de relógio em inglês", "CLOCK CHECK" in bruto)
        checar("evento de decisão em inglês", "METHODOLOGICAL DECISION" in bruto)
        checar("evento de alteração em inglês", "CHANGE TO THE EXAMINED DEVICE" in bruto)
        checar("prefixo Decision em inglês", "Decision: Physical extraction" in bruto)

        print("\n[2] Dossiê lê o registro em inglês")
        d = montar_dossie(pasta_en)
        checar("dispositivo lido do cabeçalho", d.identificador_do_dispositivo == "SERIAL-L-EN")
        checar("abertura lida", d.abertura != "")
        checar("encerramento lido", d.encerramento != "")
        checar("alteração encontrada", len(d.eventos_com("alteracao")) == 1)
        checar("decisão encontrada", len(d.eventos_com("decisao")) == 1)
        checar("relógio encontrado", d.evento("relogio") is not None)
        checar("ambiente lido", len(d.ambiente) > 0)

        print("\n[3] Protocolos ISO: o que ESTÁ no registro NÃO vira 'não localizado'")
        r = respostas(pasta_en)
        checar("ambiente comprovado (5.3.3/5.3.4)", r.get("5.3.3 / 5.3.4") != NAO_LOCALIZADO)
        checar("decisão comprovada (5.3.5)", r.get("5.3.5") != NAO_LOCALIZADO)
        checar("alteração comprovada (5.4.1/6.1)", r.get("5.4.1 / 6.1") != NAO_LOCALIZADO)
        checar("relógio comprovado (6.6)", resposta_do_relogio(pasta_en) != NAO_LOCALIZADO)
    finally:
        definir_idioma("pt")

    print("\n[4] Português — inalterado e lido certo")
    pasta_pt = montar(raiz, "CASE_PT", "L-PT")
    bruto_pt = (pasta_pt / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("título em português", "REGISTRO DO PROCEDIMENTO DE AQUISIÇÃO FORENSE" in bruto_pt)
    checar("evento em português", "DECISÃO METODOLÓGICA" in bruto_pt)
    d_pt = montar_dossie(pasta_pt)
    checar("dispositivo lido (pt)", d_pt.identificador_do_dispositivo == "SERIAL-L-PT")
    checar("decisão encontrada (pt)", len(d_pt.eventos_com("decisao")) == 1)
    r_pt = respostas(pasta_pt)
    checar("decisão comprovada (pt)", r_pt.get("5.3.5") != NAO_LOCALIZADO)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
