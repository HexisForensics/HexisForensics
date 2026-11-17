"""
Fase 4 — a narração de um módulo (log, mensagem do resultado e o arquivo-
resumo SELADO) sai no idioma do selo. A saída crua do aparelho nunca passa
pelo catálogo. PT idêntico ao de antes; EN autorado. Prova no 1º módulo
migrado: android_estado_inicial.
"""

import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.extractors.estado_dispositivo import EstadoDispositivoExtractor  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def resumo_em(idioma, captura_ok=True, motivo="", coletados=None, perfis=1):
    ext = EstadoDispositivoExtractor()
    ext._idi_selo = idioma
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        ext._gravar_resumo(pasta, captura_ok, motivo, coletados or [], perfis)
        return (pasta / "RESUMO_ESTADO.txt").read_text(encoding="utf-8")


print("\n[1] Resumo selado em PT — idêntico ao de antes")
pt = resumo_em("pt", coletados=["Estado de energia e da tela"])
checar("título PT", "ESTADO DO APARELHO AO SER RECEBIDO" in pt)
checar("captura PT", "Captura de tela: obtida" in pt)
checar("perfis PT", "Perfis de usuário no aparelho: 1" in pt)
checar("itens PT", "[ITENS DE ESTADO COLETADOS]" in pt)
checar("nota PT", "não indica falha da coleta." in pt)

print("\n[2] Resumo selado em EN")
en = resumo_em("en", coletados=[EstadoDispositivoExtractor()._t("lg_estado_rot_energia")])
# nota: o _t acima resolve no idioma ATIVO (pt); o conteúdo coletado é dado,
# o que importa é a MOLDURA do resumo em EN:
en2 = resumo_em("en", captura_ok=False, motivo="no image", coletados=[], perfis=2)
checar("título EN", "DEVICE STATE AS RECEIVED" in en)
checar("captura EN", "Screenshot: obtained" in en)
checar("perfis EN", "User profiles on the device: 1" in en)
checar("itens EN", "[STATE ITEMS COLLECTED]" in en)
checar("nota EN", "does not indicate a collection failure." in en)
checar("sem captura EN", "Screenshot: NOT obtained — no image" in en2)

print("\n[3] A mensagem do resultado (selada no desfecho) no idioma do selo")
ext = EstadoDispositivoExtractor()
ext._idi_selo = "en"
msg_en = (ext._t("lg_estado_msg", n=5) + ext._t("lg_estado_com_captura"))
checar("mensagem EN", msg_en == "Initial state recorded: 5 state item(s), with screenshot.")
ext._idi_selo = "pt"
msg_pt = (ext._t("lg_estado_msg", n=5) + ext._t("lg_estado_com_captura"))
checar("mensagem PT idêntica",
       msg_pt == "Estado inicial registrado: 5 item(ns) de estado, com captura de tela.")

print("\n[3b] A narração compartilhada da base Android no idioma do selo")
from core.idioma import traduzir as _t  # noqa: E402
checar("fidelidade EN", _t("lg_ab_fidelidade_ok", "en", n=3) == "    Fidelity confirmed: 3 file(s) identical to the source.")
checar("fidelidade PT idêntica",
       _t("lg_ab_fidelidade_ok", "pt", n=3) == "    Fidelidade confirmada: 3 arquivo(s) identicos a origem.")
checar("inventário EN",
       _t("lg_ab_origem_inventariada", "en", metodo="find", n=5, caminho="/sdcard")
       == "    Source inventoried via 'find': 5 file(s) in /sdcard")
checar("scoped storage EN em inglês",
       "no longer exposes" in _t("lg_ab_restricao_scoped", "en", api=33, caminho="/sdcard/Android/data"))

print("\n[4] Os marcadores compartilhados")
checar("concluído EN", ext._t("lg_concluido", valor="x") == "[CONCLUÍDO] x")  # ext ainda em pt
ext._idi_selo = "en"
checar("completed EN", ext._t("lg_concluido", valor="x") == "[COMPLETED] x")
checar("cancelada EN", ext._t("lg_cancelada_modulo") == "Extraction cancelled by the user.")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
