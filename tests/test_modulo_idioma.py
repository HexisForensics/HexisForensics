"""
Fase 4 — nome, descrição, limitações e alterações dos módulos no idioma do
caso. O `id` do módulo é a chave estável (`mod_<id>_*`); o texto do código
(PT) é a FONTE e o fallback. Módulo ainda não migrado cai para o português,
sem quebrar. O método selado (metodo_declarado) nasce no idioma carimbado.
"""

import json
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

import core.android.extractors  # noqa: F401,E402
from core.metodo import descrever, gravar_metodo, ler_metodo  # noqa: E402
from services.extraction_service import listar_extratores  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


EXTRATORES = {e.id: e for e in listar_extratores("Android")}
EST = EXTRATORES["android_estado_inicial"]

print("\n[1] O módulo migrado resolve nos dois idiomas")
checar("nome em PT é o literal", EST.nome_no_idioma("pt") == EST.nome_exibicao)
checar("nome em EN é traduzido", EST.nome_no_idioma("en") == "Device State as Received")
checar("descrição em PT é o literal", EST.descricao_no_idioma("pt") == EST.descricao)
checar("descrição em EN muda", EST.descricao_no_idioma("en") != EST.descricao)
checar("limitações em PT são os literais",
       EST.limitacoes_no_idioma("pt") == list(EST.limitacoes_conhecidas))
lim_en = EST.limitacoes_no_idioma("en")
checar("há duas limitações em EN", len(lim_en) == 2)
checar("limitação EN é inglês", "screenshot shows what was visible" in lim_en[1])

print("\n[2] Módulo ainda não migrado cai para o português (fallback)")
nao_migrado = EXTRATORES["android_device_info"]
checar("nome em EN = literal PT", nao_migrado.nome_no_idioma("en") == nao_migrado.nome_exibicao)
checar("limitações em EN = literais PT",
       nao_migrado.limitacoes_no_idioma("en") == list(nao_migrado.limitacoes_conhecidas))

print("\n[3] O catálogo PT do módulo migrado bate byte a byte com o literal")
pt = json.loads((RAIZ_PROJETO / "idiomas" / "pt.json").read_text(encoding="utf-8"))
checar("mod_..._nome == nome_exibicao",
       pt["mod_android_estado_inicial_nome"] == EST.nome_exibicao)
checar("mod_..._desc == descricao",
       pt["mod_android_estado_inicial_desc"] == EST.descricao)
checar("mod_..._lim_0 == limitação 0",
       pt["mod_android_estado_inicial_lim_0"] == EST.limitacoes_conhecidas[0])
checar("mod_..._lim_1 == limitação 1",
       pt["mod_android_estado_inicial_lim_1"] == EST.limitacoes_conhecidas[1])

print("\n[4] O método selado nasce no idioma carimbado")
with tempfile.TemporaryDirectory() as tmp:
    aq_en = Path(tmp) / "aq_en"
    aq_en.mkdir()
    gravar_metodo(aq_en, descrever([EST], "en"))
    m_en = ler_metodo(aq_en)
    checar("método EN traz o nome em inglês", m_en.modulos[0].nome == "Device State as Received")
    checar("método EN traz a limitação em inglês",
           "screenshot shows what was visible" in m_en.modulos[0].limitacoes[1])

    aq_pt = Path(tmp) / "aq_pt"
    aq_pt.mkdir()
    gravar_metodo(aq_pt, descrever([EST], "pt"))
    m_pt = ler_metodo(aq_pt)
    checar("método PT traz o nome literal", m_pt.modulos[0].nome == EST.nome_exibicao)
    checar("método PT traz as limitações literais",
           m_pt.modulos[0].limitacoes == list(EST.limitacoes_conhecidas))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
