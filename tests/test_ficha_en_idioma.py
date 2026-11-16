"""
Fase 2 — a Ficha do Aparelho sai no idioma ativo. Prova em INGLÊS que os
rótulos, o NÃO APURADO e o texto de rodapé vêm do catálogo (documento
DERIVADO, segue o idioma escolhido). O selado não é tocado.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.idioma import definir_idioma, traduzir  # noqa: E402
from core.ficha import CampoDaFicha, FichaDoAparelho, render_texto  # noqa: E402

falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


def contem(nome, texto, trecho):
    if trecho in texto:
        print("  OK   " + nome)
    else:
        print(f" FALHA {nome}\n    não contém: {trecho!r}")
        falhas.append(nome)


definir_idioma("en")
try:
    print("\n[1] Termos da Ficha em inglês (glossário)")
    igual("título", traduzir("fha_titulo_pdf"), "DEVICE INFORMATION SHEET")
    igual("NÃO APURADO", traduzir("fha_nao_apurado"), "NOT DETERMINED")
    igual("rótulo bloqueio", traduzir("fha_l_bloqueio"), "Lock state when received")
    igual("rótulo IMEI", traduzir("fha_l_imei"), "IMEI")
    igual("desbloqueado", traduzir("fha_desbloqueado"), "UNLOCKED")

    print("\n[2] render_texto respeita o idioma ativo")
    ficha = FichaDoAparelho(
        aquisicao="android_20260101_120000",
        campos=[CampoDaFicha("IMEI", "350123456789012", "identificacao/", apurado=True),
                CampoDaFicha("Encryption state", traduzir("fha_nao_apurado"),
                             "device_specs/", apurado=False)],
    )
    texto = render_texto(ficha)
    contem("título em inglês no texto", texto, "DEVICE INFORMATION SHEET")
    contem("aquisição em inglês", texto, "Acquisition: android_20260101_120000")
    contem("prefixo de fonte em inglês", texto, "source: identificacao/")
    contem("rodapé em inglês (NOT DETERMINED != ausência)", texto,
           "NOT DETERMINED does not mean the data is absent from the device")
finally:
    definir_idioma("pt")  # não vazar o idioma para outras verificações

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
