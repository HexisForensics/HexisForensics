"""
Testes do contrato de metadados de metodo dos extratores.

Um extrator sabe coisas sobre si que ninguem mais sabe: o que ele NAO
alcanca, o que ele altera no aparelho e que competencia sua operacao exige.
Antes deste contrato esse conhecimento existia, mas em docstring -- o modulo
de WhatsApp explicava em prosa que sem privilegio elevado nao chega ao banco
de mensagens, e nem a interface nem o laudo jamais souberam disso.

O teste central e o [1]: **modulo nenhum pode ficar mudo sobre os proprios
limites**. Laudo silencioso sobre o que o metodo nao alcanca convida a ler
ausencia de dado como ausencia de fato -- afirmar alem do verificado, so que
por omissao. Um modulo novo que esqueca de declarar suas limitacoes falha
aqui, e nao chega ao laudo calado.

A exigencia vale para Android, iOS e Computador. (O iOS entrou ao sair dos
stubs -- e o teste cobra isso sozinho: ele nao tem lista fixa de plataformas,
percorre as que tem extratores reais registrados, e uma plataforma que saia
do stub sem declarar limitacoes falha aqui sem que ninguem lembre de vir
alterar este arquivo.
"""
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

import core.android.extractors  # noqa: F401  (registra os extratores)
import core.computador.extractors  # noqa: F401
import core.ios.extractors  # noqa: F401
from core.base_extractor import BaseExtractor, Perfil
from services.extraction_service import listar_extratores

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


PLATAFORMAS = ("Android", "iOS", "Computador")


def saiu_do_stub(extrator) -> bool:
    """
    `True` se o extrator tem `executar()` proprio.

    Plataforma ainda em stub herda o `executar` da sua base, que so
    devolve "nao implementado nesta versao" -- cobrar limitacoes dela
    seria cobrar de codigo que nao adquire nada. O criterio e estrutural
    de proposito: quando o iOS sair do stub, ele entra nesta cobranca
    sozinho, sem que ninguem precise lembrar de voltar aqui.
    """
    quem_define = next(base for base in extrator.__mro__ if "executar" in base.__dict__)
    return not quem_define.__module__.endswith(".base")


extratores = []
por_plataforma = {}
for nome_plataforma in PLATAFORMAS:
    reais = [e for e in listar_extratores(nome_plataforma) if saiu_do_stub(e)]
    por_plataforma[nome_plataforma] = reais
    extratores.extend(reais)

# ---------------------------------------------------------------------------
print("\n[1] Nenhum modulo fica mudo sobre os proprios limites")
# ---------------------------------------------------------------------------
checar("ha extratores Android registrados", len(por_plataforma["Android"]) > 0)
checar(
    "ha extratores de Computador registrados",
    len(por_plataforma["Computador"]) > 0,
)
checar(
    "ha extratores de iOS registrados (sairam do stub e entram na cobranca)",
    len(por_plataforma["iOS"]) > 0,
)

mudos = [e.nome_exibicao for e in extratores if not e.limitacoes_conhecidas]
checar(f"todos declaram ao menos uma limitacao (mudos: {mudos})", not mudos)

# ---------------------------------------------------------------------------
print("\n[2] As limitacoes sao texto de laudo, nao rascunho")
# ---------------------------------------------------------------------------
for extrator in extratores:
    for limitacao in extrator.limitacoes_conhecidas:
        rotulo = f"{extrator.id}: limitacao e string nao vazia"
        if not (isinstance(limitacao, str) and limitacao.strip()):
            checar(rotulo, False)
            break
    else:
        checar(f"{extrator.id}: {len(extrator.limitacoes_conhecidas)} limitacao(oes) legivel(is)", True)

curtas = [
    (e.id, lim)
    for e in extratores
    for lim in e.limitacoes_conhecidas
    if len(lim) < 40
]
# Limitacao de uma palavra ("root") nao serve a quem le o laudo: o texto tem
# de dizer o que nao se obtem e por que.
checar(f"nenhuma limitacao curta demais para o laudo ({curtas})", not curtas)

# ---------------------------------------------------------------------------
print("\n[3] Alteracao no dispositivo vem sempre com justificativa")
# ---------------------------------------------------------------------------
# O principio forense: toda alteracao no alvo e registrada E justificada.
# Declarar a alteracao sem o motivo deixaria o laudo dizendo que a ferramenta
# mexeu no aparelho sem dizer por que -- pior do que nao declarar.
malformadas = []
com_alteracao = 0
for extrator in extratores:
    for item in extrator.alteracoes_no_dispositivo:
        if not (isinstance(item, tuple) and len(item) == 2 and all(
            isinstance(parte, str) and parte.strip() for parte in item
        )):
            malformadas.append((extrator.id, item))
        else:
            com_alteracao += 1

checar(f"toda alteracao e um par (alteracao, justificativa) ({malformadas})", not malformadas)
checar("ha modulos que declaram alteracao", com_alteracao > 0)

# ---------------------------------------------------------------------------
print("\n[4] O perfil exigido e declarado e coerente")
# ---------------------------------------------------------------------------
for extrator in extratores:
    checar(
        f"{extrator.id}: perfil e um Perfil ({getattr(extrator.perfil_minimo, 'name', '?')})",
        isinstance(extrator.perfil_minimo, Perfil),
    )

# Quem exige privilegio elevado no aparelho nao e coleta de rotina: decidir
# diante do que foge do procedimento e competencia de especialista.
incoerentes = [
    e.id
    for e in extratores
    if e.requer_privilegio_root and e.perfil_minimo is not Perfil.DES
]
checar(f"modulo que exige privilegio elevado pede DES ({incoerentes})", not incoerentes)

# ---------------------------------------------------------------------------
print("\n[5] O contrato tem padrao seguro para quem nao declarar")
# ---------------------------------------------------------------------------
checar("limitacoes comecam vazias na base", BaseExtractor.limitacoes_conhecidas == ())
checar("alteracoes comecam vazias na base", BaseExtractor.alteracoes_no_dispositivo == ())
checar("e o perfil padrao e o menos restritivo", BaseExtractor.perfil_minimo is Perfil.DEFR)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
