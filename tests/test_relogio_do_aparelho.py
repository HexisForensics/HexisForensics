"""
Desvio do relógio do aparelho (Galaxy A22 real, 30/10/2026: 539 dias atrasado).

A suíte media e registrava o desvio como "46588884s atrasado", sem alerta e
só no registro do procedimento. Agora: por extenso, alerta acima do limite e
nota no Relatório de Extração e no laudo — lida de volta do registro, que é a
fonte única e está sob o selo.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.device import RelogioDispositivo  # noqa: E402
from core.procedimento import RegistroProcedimento  # noqa: E402
from core.relogio import (  # noqa: E402
    LIMITE_DE_DESVIO_SEGUNDOS,
    alerta,
    desvio_da_aquisicao,
    ler_desvio_registrado,
    por_extenso,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


SAMSUNG = -46588884  # medido no Galaxy A22: 9/5/2025 contra 30/10/2026

print("\n[1] Por extenso")
checar("539 dias, 5 h e 21 min", por_extenso(SAMSUNG) == "539 dias, 5 h e 21 min")
checar("menos de um minuto fica em segundos", por_extenso(42) == "42 s")
checar("um dia só, no singular", por_extenso(86400) == "1 dia")
relogio = RelogioDispositivo(1_000_000 + SAMSUNG, 1_000_000, "Fri May  9 13:21:09 -03 2025",
                             "America/Sao_Paulo")
resumo = relogio.resumo()
checar("o registro diz o desvio por extenso, com os segundos exatos",
       "539 dias, 5 h e 21 min atrasado (-46588884 s)" in resumo)

print("\n[2] Alerta")
checar("desvio grande gera alerta", "539 dias" in alerta(SAMSUNG)
       and "deslocadas" in alerta(SAMSUNG))
checar("desvio pequeno não alerta", alerta(LIMITE_DE_DESVIO_SEGUNDOS) == "")
checar("relógio não lido não alerta (nem inventa)", alerta(None) == "")

print("\n[3] Lido de volta do registro, inclusive de aquisição antiga")
checar("formato atual", ler_desvio_registrado("    " + resumo) == SAMSUNG)
checar("formato antigo, como no CASO_004",
       ler_desvio_registrado("Relogio ... | Desvio: 46588884s atrasado") == SAMSUNG)
checar("antigo adiantado", ler_desvio_registrado("Desvio: 12s adiantado") == 12)
checar("sem desvio", ler_desvio_registrado("Desvio: nenhum") == 0)
checar("relógio ilegível: desconhecido, não zero",
       ler_desvio_registrado("Relogio do aparelho: NAO FOI POSSIVEL LER (desvio desconhecido).")
       is None)

with tempfile.TemporaryDirectory() as temporario:
    pasta = Path(temporario)
    registro = RegistroProcedimento(pasta)
    registro.abrir("CASO_004", "Android", "RX8XX00XXXX")
    registro.registrar_relogio(resumo)
    registro.encerrar("1 módulo.")
    checar("a aquisição devolve o desvio gravado", desvio_da_aquisicao(pasta) == SAMSUNG)

print("\n[4] O documento traz o desvio e o alerta")
from services import blocos_pdf  # noqa: E402
from services.dossie_service import Dossie  # noqa: E402

dossie = Dossie(pasta=Path(temporario), caso="CASO_004")
dossie.desvio_do_relogio = SAMSUNG
textos = " ".join(
    getattr(elemento, "text", "") or str(getattr(elemento, "_cellvalues", ""))
    for elemento in blocos_pdf.bloco_peca(dossie, 400)
)
checar("a peça descreve o relógio aferido", "539 dias, 5 h e 21 min atrasado" in textos)
checar("e alerta que as datas estão deslocadas", "deslocadas" in textos)

dossie.desvio_do_relogio = 30
textos = " ".join(
    getattr(elemento, "text", "") or str(getattr(elemento, "_cellvalues", ""))
    for elemento in blocos_pdf.bloco_peca(dossie, 400)
)
checar("desvio pequeno aparece sem alerta", "30 s adiantado" in textos and "deslocadas" not in textos)

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
