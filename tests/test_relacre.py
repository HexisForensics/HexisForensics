"""
Reaposição de lacre: o novo lacre entra como COMPLEMENTO do caso, com a foto
preservada fora do selo, e a aquisição selada permanece intacta.
"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core.case import criar_pasta_aquisicao, pasta_do_caso
from core.hashing import gerar_manifesto, conferir_manifesto
from services.case_service import CaseService
from services import relacre_service

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


with tempfile.TemporaryDirectory() as td:
    raiz = Path(td) / "extracoes"
    aq = criar_pasta_aquisicao(raiz, "CASO_RL", "Android", datetime(2026, 11, 20, 9, 0))
    servico = CaseService(raiz)
    servico.abrir_registro_procedimento(aq, "CASO_RL", "Android", "ZY22RL")
    servico.gravar_dados_do_caso("CASO_RL", {"referencia": "Proc. 1"})
    servico.gravar_cadeia_custodia(aq, "CASO_RL", {"marca_modelo": "A22", "lacre": "000123"})
    servico.encerrar_registro_procedimento("1 modulo.")
    gerar_manifesto(aq)
    selo_antes = conferir_manifesto(aq)
    caso = pasta_do_caso(aq)

    foto = Path(td) / "lacre_novo.jpg"
    foto.write_bytes(b"\xff\xd8\xff\xe0JFIF-foto-ficticia-do-novo-lacre\xff\xd9")

    print("[1] Reaposicao registrada como complemento, com foto e hash")
    r = relacre_service.registrar_reaposicao(aq, {
        "numero": "000987", "data": "20/11/2026 17:00",
        "por": "Maria Perita", "registro": "PC-SP 12.345", "foto": foto})
    checar("sucesso", r.sucesso)
    checar("complemento gravado", r.caminho_complemento and r.caminho_complemento.is_file())
    texto = r.caminho_complemento.read_text(encoding="utf-8") if r.caminho_complemento else ""
    checar("o novo lacre consta", "000987" in texto)
    checar("quem relacrou consta", "Maria Perita" in texto)
    checar("o SHA-256 da foto consta", "SHA-256 da foto:" in texto)
    checar("a foto foi copiada para reaposicoes/ do caso",
           any((caso / "reaposicoes").glob("lacre_*.jpg")))

    print("\n[2] A aquisicao selada permanece intacta")
    selo_depois = conferir_manifesto(aq)
    checar("o selo continua integro", selo_depois.integro)
    checar("nenhum arquivo selado mudou", selo_antes.integro and selo_depois.integro)

    print("\n[3] Campos obrigatorios")
    r2 = relacre_service.registrar_reaposicao(aq, {"numero": "", "foto": foto})
    checar("sem numero e FALHA", not r2.sucesso and r2.erro)
    r3 = relacre_service.registrar_reaposicao(aq, {"numero": "111", "foto": None})
    checar("sem foto e FALHA", not r3.sucesso and r3.erro)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
