"""
Entrega de material: cópia conferida pelo hash, recibo, registro no caso
e a aquisição intocada. Cópia que não confere é falha, nunca "entregue".
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import calcular_sha256, conferir_manifesto, gerar_manifesto  # noqa: E402
from services import entrega_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402

aplicacao = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def texto_do_pdf(caminho: Path) -> str:
    documento = QPdfDocument()
    documento.load(str(caminho))
    return " ".join(" ".join(documento.getAllText(p).text().split())
                    for p in range(documento.pageCount()))


def estado(pasta: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in pasta.rglob("*")}


with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario) / "extracoes"
    aq = criar_pasta_aquisicao(raiz, "CASO_E", "Android", datetime(2026, 10, 24, 10, 0))
    servico = CaseService(raiz)
    servico.abrir_registro_procedimento(aq, "CASO_E", "Android", "SERIAL")
    (aq / "media" / "Camera").mkdir(parents=True)
    (aq / "media" / "Camera" / "foto1.jpg").write_bytes(b"\xff\xd8foto1")
    (aq / "media" / "Camera" / "foto2.jpg").write_bytes(b"\xff\xd8foto2")
    (aq / "sms").mkdir()
    (aq / "sms" / "sms_todas.txt").write_text("Row: 0 body=oi\n", encoding="utf-8")
    servico.encerrar_registro_procedimento("ok")
    gerar_manifesto(aq)
    documento = raiz / "CASO_E" / "documentos" / "Laudo_Pericial_android_20261024_100000.pdf"
    documento.parent.mkdir(parents=True)
    documento.write_bytes(b"%PDF-1.4 laudo")
    antes = estado(aq)
    destino = Path(temporario) / "pendrive"
    destino.mkdir()

    print("\n[1] Entrega de pasta do material e de documento")
    r = entrega_service.exportar(aq, destino, ["media/Camera", "sms/sms_todas.txt"], [documento],
                                 examinador="Fulana", finalidade="Juízo da 1ª Vara")
    checar("sem erro e sem falha", not r.erro and not r.falhas)
    nomes = [i.nome for i in r.itens]
    checar("a pasta entra com todos os arquivos, preservando o caminho",
           {"material/media/Camera/foto1.jpg", "material/media/Camera/foto2.jpg",
            "material/sms/sms_todas.txt", "documentos/" + documento.name} == set(nomes))
    checar("cada cópia tem o mesmo SHA-256 do original",
           all(calcular_sha256(r.pasta / i.nome) == i.sha256 for i in r.itens)
           and next(i for i in r.itens if i.nome.endswith("foto1.jpg")).sha256
           == calcular_sha256(aq / "media" / "Camera" / "foto1.jpg"))
    checar("o material diz que confere com o lacre",
           all(i.situacao == "confere com o lacre" for i in r.itens if i.origem == "material"))
    recibo = (r.pasta / "Recibo_de_Entrega.txt").read_text(encoding="utf-8")
    checar("recibo em texto com finalidade, examinador e hashes",
           "Juízo da 1ª Vara" in recibo and "Fulana" in recibo and r.itens[0].sha256 in recibo)
    texto = texto_do_pdf(r.recibo_pdf)
    checar("recibo em PDF, com a lista e as assinaturas",
           "RECIBO DE ENTREGA" in texto and "foto1.jpg" in texto and "Recebido por" in texto
           and "DOCUMENTO DE TESTE" not in texto)
    complementos = list((raiz / "CASO_E" / "complementos").glob("*entrega*"))
    checar("a entrega vira complemento do caso",
           len(complementos) == 1 and "foto2.jpg" in complementos[0].read_text(encoding="utf-8"))
    checar("a aquisição não foi tocada", estado(aq) == antes and conferir_manifesto(aq).integro)

    print("\n[2] O que não pode")
    checar("nada escolhido é recusado",
           "Nada foi escolhido" in entrega_service.exportar(aq, destino).erro)
    checar("destino dentro da aquisição é recusado",
           "dentro da aquisição" in entrega_service.exportar(aq, aq / "sms", ["sms"]).erro)
    original = entrega_service.calcular_sha256
    valores = iter(["aaaa", "bbbb"] * 10)
    entrega_service.calcular_sha256 = lambda _c: next(valores)
    r2 = entrega_service.exportar(aq, destino, ["sms/sms_todas.txt"])
    entrega_service.calcular_sha256 = original
    checar("cópia diferente do original é falha, e nada é dado como entregue",
           bool(r2.erro) and "NÃO é idêntica" in r2.erro and not r2.itens)

    r4 = entrega_service.exportar(aq, destino, ["sms/sms_todas.txt"])
    r5 = entrega_service.exportar(aq, destino, ["sms/sms_todas.txt"])
    checar("entregas seguidas não se sobrescrevem", r4.pasta != r5.pasta and r4.pasta.is_dir())

    print("\n[3] Em modo de teste, o recibo sai marcado")
    r3 = entrega_service.exportar(aq, destino, ["sms/sms_todas.txt"], teste=True)
    checar("tarja de TESTE no recibo em PDF e no texto",
           "DOCUMENTO DE TESTE" in texto_do_pdf(r3.recibo_pdf)
           and "TESTE, SEM VALOR PERICIAL" in (r3.pasta / "Recibo_de_Entrega.txt").read_text(
               encoding="utf-8"))

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
