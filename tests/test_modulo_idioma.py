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
import core.ios.extractors  # noqa: F401,E402
import core.computador.extractors  # noqa: F401,E402
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

print("\n[2] Módulo sem chave no catálogo cai para o português (fallback)")
# Um id inexistente no catálogo prova o fallback sem depender do estado da
# migração: quando a chave falta, sai o literal declarado no código.
from core.base_extractor import BaseExtractor  # noqa: E402


class _ModuloFicticio(BaseExtractor):
    id = "modulo_inexistente_no_catalogo"
    nome_exibicao = "Nome só no código"
    descricao = "Descrição só no código"
    limitacoes_conhecidas = ("Limitação declarada apenas no código-fonte.",)

    def disponivel(self):
        return (False, "")

    def executar(self, pasta_caso):
        return None


checar("nome em EN = literal PT", _ModuloFicticio.nome_no_idioma("en") == "Nome só no código")
checar("limitações em EN = literais PT",
       _ModuloFicticio.limitacoes_no_idioma("en") == ["Limitação declarada apenas no código-fonte."])

print("\n[3] O catálogo PT de TODO módulo bate byte a byte com o literal")
# O selo PT é escrito pelo catálogo (descrever resolve 'pt'): se a chave PT
# divergir do literal, um caso PT deixaria de ser idêntico ao de antes.
pt = json.loads((RAIZ_PROJETO / "idiomas" / "pt.json").read_text(encoding="utf-8"))
en = json.loads((RAIZ_PROJETO / "idiomas" / "en.json").read_text(encoding="utf-8"))

TODOS = []
for plat in ("Android", "iOS", "Computador"):
    for e in listar_extratores(plat):
        if e.id not in [x.id for x in TODOS]:
            TODOS.append(e)

divergentes = []
nao_migrados = []
for e in TODOS:
    campos = {f"mod_{e.id}_nome": e.nome_exibicao, f"mod_{e.id}_desc": e.descricao}
    for i, lim in enumerate(e.limitacoes_conhecidas):
        campos[f"mod_{e.id}_lim_{i}"] = lim
    for i, (o, j) in enumerate(e.alteracoes_no_dispositivo):
        campos[f"mod_{e.id}_alt_{i}_o"] = o
        campos[f"mod_{e.id}_alt_{i}_j"] = j
    if f"mod_{e.id}_nome" not in pt:
        nao_migrados.append(e.id)
        continue
    for chave, literal in campos.items():
        if pt.get(chave) != literal:
            divergentes.append(chave)

checar(f"todo mod_* PT é idêntico ao literal ({divergentes[:3]})", not divergentes)
checar(f"todos os módulos migrados (faltam: {nao_migrados})", not nao_migrados)

print("\n[3b] Cada módulo tem nome traduzido em EN presente no catálogo")
sem_en = [e.id for e in TODOS if f"mod_{e.id}_nome" not in en]
checar(f"todo módulo tem nome EN ({sem_en})", not sem_en)

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

print("\n[5] O nome selado no desfecho sobrevive no idioma carimbado")
# A extração passa extrator.nome_no_idioma(idioma_do_caso) ao registrar a
# execução; aqui provamos que o desfecho sela e relê esse nome tal como veio,
# para a tabela de resultados do laudo sair no idioma do caso.
from core.desfecho import descrever_execucao, gravar_desfecho, ler_desfecho  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    aq = Path(tmp) / "aq"
    aq.mkdir()
    nome_en = EST.nome_no_idioma("en")
    registros = [(EST.id, nome_en, True, "ok", {})]
    gravar_desfecho(aq, descrever_execucao(registros))
    d = ler_desfecho(aq)
    checar("o desfecho relê o nome em inglês", d.modulos[0].nome == nome_en)
    checar("e o txt selado traz o nome em inglês",
           nome_en in (aq / "desfecho" / "desfecho_da_coleta.txt").read_text(encoding="utf-8"))

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
