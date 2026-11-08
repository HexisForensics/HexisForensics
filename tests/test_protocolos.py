"""
Testes dos protocolos periciais (ABNT NBR ISO/IEC 27037:2013).

O questionario e dividido em dois blocos, e a divisao e o que estes testes
guardam:

- o que a FERRAMENTA comprova, ela responde sozinha, sempre acompanhada do
  arquivo que sustenta a resposta;
- o que so o EXAMINADOR sabe, so ele responde, e nao responder aparece como
  tal.

A regra que nao pode quebrar esta no bloco [2]: registro ausente vira
"Registro nao localizado", NUNCA "Nao". Sao coisas diferentes -- "nao houve"
e "nao consegui verificar" sustentam conclusoes opostas num exame, e o
segundo e o unico verdadeiro quando o arquivo nao esta la.

E no bloco [3]: a norma NAO exige ausencia de alteracao. Exige que a
alteracao seja minimizada, documentada e justificada (5.4.1, 6.1). Um
aparelho Android precisa ter a depuracao USB ativada para ser periciado --
perguntar se "nada foi modificado" obrigaria o examinador a negar o que o
proprio registro do procedimento afirma.
"""
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.protocolos import (
    NAO_LOCALIZADO,
    NAO_RESPONDIDO,
    SIM,
    TITULO_ALTERACAO,
    TITULO_AMBIENTE,
    TITULO_DECISAO,
    TITULO_RELOGIO,
    exige_especificacao,
    perguntas_do_examinador,
    verificar_automaticos,
)
from services.laudo_service import perguntas_dos_protocolos

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar_aquisicao(raiz: Path, com_diario=True, com_alteracao=True) -> Path:
    aquisicao = raiz / "android_20260823_120000"
    aquisicao.mkdir(parents=True)
    if com_diario:
        linhas = [
            "REGISTRO DO PROCEDIMENTO",
            f"[data] {TITULO_AMBIENTE}",
            "    ferramenta: HexisForensics",
            f"[data] {TITULO_RELOGIO}",
            "    Relogio do aparelho: ... Desvio: 1s",
            f"[data] {TITULO_DECISAO}",
            "    Decisao: comandos vinculados ao serial.",
        ]
        if com_alteracao:
            linhas += [
                f"[data] {TITULO_ALTERACAO}",
                "    Alteracao: Depuracao USB ativada.",
                "    Justificativa: imposicao do protocolo ADB.",
            ]
        (aquisicao / "registro_procedimento.txt").write_text(
            "\n".join(linhas), encoding="utf-8"
        )
    (aquisicao / "cadeia_custodia.txt").write_text("=== CADEIA ===", encoding="utf-8")
    (aquisicao / "identificacao").mkdir()
    (aquisicao / "manifesto_hashes.txt").write_text("abc *arquivo.txt", encoding="utf-8")
    return aquisicao


def como_dicionario(itens):
    return {clausula: (resposta, origem) for clausula, _, resposta, origem in itens}


# ---------------------------------------------------------------------------
print("\n[1] A ferramenta responde o que ela mesma comprova")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    itens = verificar_automaticos(aquisicao)
    por_clausula = como_dicionario(itens)

    checar("oito requisitos verificados", len(itens) == 8)
    checar("auditabilidade (5.3.2) confirmada", por_clausula["5.3.2"][0] == SIM)
    checar("repetibilidade e reprodutibilidade (5.3.3/5.3.4)", por_clausula["5.3.3 / 5.3.4"][0] == SIM)
    checar("relogio aferido (6.6)", por_clausula["6.6"][0] == SIM)
    checar("cadeia de custodia (6.1)", por_clausula["6.1"][0] == SIM)
    checar("integridade selada (5.4.5)", por_clausula["5.4.5"][0] == SIM)
    checar("justificabilidade conta as decisoes", "1 registrada" in por_clausula["5.3.5"][0])

    # Toda resposta precisa apontar o arquivo que a sustenta. Resposta sem
    # lastro seria mais uma afirmacao sem prova -- o oposto do proposito.
    sem_origem = [c for c, (r, o) in por_clausula.items() if r != NAO_LOCALIZADO and o == "—"]
    checar(f"toda resposta afirmativa aponta o registro ({sem_origem})", not sem_origem)

# ---------------------------------------------------------------------------
print("\n[2] Registro ausente vira 'nao localizado', NUNCA 'Nao'")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    vazia = Path(temporario) / "android_sem_nada"
    vazia.mkdir()
    itens = verificar_automaticos(vazia)
    por_clausula = como_dicionario(itens)

    checar("mesmo sem registro, todos os requisitos aparecem", len(itens) == 8)
    respostas = [r for r, _ in por_clausula.values()]
    checar("nenhuma resposta e 'Nao'", "Não" not in respostas)
    checar(
        "todas dizem que o registro nao foi localizado",
        all(r == NAO_LOCALIZADO for r in respostas),
    )
    checar("e nenhuma inventa origem", all(o == "—" for _, o in por_clausula.values()))

# ---------------------------------------------------------------------------
print("\n[3] Alteracao: a norma pede registro e justificativa, nao ausencia")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    com = montar_aquisicao(Path(temporario) / "com", com_alteracao=True)
    resposta_com = como_dicionario(verificar_automaticos(com))["5.4.1 / 6.1"][0]
    checar("alteracao registrada e contada como conformidade", resposta_com.startswith(SIM))
    checar("dizendo que foi justificada", "justificada" in resposta_com)

    sem = montar_aquisicao(Path(temporario) / "sem", com_alteracao=False)
    resposta_sem = como_dicionario(verificar_automaticos(sem))["5.4.1 / 6.1"][0]
    checar(
        "sem alteracao, diz que nenhuma foi registrada",
        "Nenhuma alteração foi registrada" in resposta_sem,
    )
    # O ponto: ausencia de alteracao NAO e reportada como falha de
    # conformidade, e presenca de alteracao NAO e reportada como problema.
    checar("e isso nao vira 'Nao'", resposta_sem != "Não")

# ---------------------------------------------------------------------------
print("\n[4] O que so o examinador sabe fica com ele")
# ---------------------------------------------------------------------------
perguntas = perguntas_do_examinador()
checar("ha perguntas para o examinador", len(perguntas) >= 5)
checar("todas trazem a clausula da norma", all(c and p for c, p in perguntas))

texto = " ".join(p for _, p in perguntas)
checar("pergunta pelo isolamento de redes", "isolado de redes" in texto)
checar("nao pergunta se 'nada foi modificado'", "não foi modificado" not in texto)
checar("pergunta pelo lacre", "lacre" in texto)
checar("e pela competencia de quem operou", "competência" in texto)

# O meio de isolamento continua sendo exigido -- mudou onde ele e coletado.
# Antes a propria pergunta mandava escrever no campo geral de observacoes;
# agora cada item tem observacao propria, e a pergunta e marcada como
# exigente de especificacao. Sem isso, "Sim" para isolamento seria uma
# afirmacao sem o meio que a sustenta, que e o que este teste protege.
isolamento = [p for _, p in perguntas if "isolado de redes" in p]
checar("o isolamento e um item so", len(isolamento) == 1)
checar("e cobra especificacao do meio empregado", exige_especificacao(isolamento[0]))

manuseio = [p for _, p in perguntas if "manuseio" in p]
checar("o manuseio tambem cobra especificacao", manuseio and exige_especificacao(manuseio[0]))

# Pergunta sem "Especificar" nao pode cobrar o campo: cobrar de todas
# transformaria a marca em ruido e o examinador aprenderia a ignora-la.
lacre = [p for _, p in perguntas if "lacre" in p]
checar("pergunta objetiva nao cobra especificacao", not exige_especificacao(lacre[0]))

# A redacao pergunta FATO, nao autocertificacao de cumprimento. "O
# dispositivo estava ligado?" e observavel; "foi mantido no estado em que
# foi recebido?" pedia que o examinador atestasse a propria conformidade.
checar("pergunta o estado do aparelho como fato", "estava ligado" in texto)
checar("sem pedir autocertificacao de conformidade",
       "mantido no estado em que foi recebido" not in texto)

clausulas_do_examinador = {c for c, _ in perguntas}
clausulas_automaticas = {c for c, _, _, _ in verificar_automaticos(Path("."))}
sobreposicao = clausulas_do_examinador & clausulas_automaticas
# 6.1 aparece nos dois blocos, mas em aspectos distintos: a ferramenta
# verifica se HA registro de cadeia; o examinador declara se o lacre estava
# integro. Nada alem disso pode se sobrepor.
checar(f"os blocos nao se duplicam alem do previsto ({sobreposicao})", sobreposicao <= {"6.1"})

# ---------------------------------------------------------------------------
print("\n[5] A interface recebe as perguntas sem conhecer core")
# ---------------------------------------------------------------------------
# `ui/` so fala com `services/` — ver CLAUDE.md.
checar("o servico expoe as perguntas", perguntas_dos_protocolos() == perguntas)
checar(
    "em pares (clausula, pergunta) legiveis",
    all(isinstance(c, str) and isinstance(p, str) for c, p in perguntas_dos_protocolos()),
)

# ---------------------------------------------------------------------------
print("\n[6] Caracteristicas do aparelho: apurado nao se confunde com digitado")
# ---------------------------------------------------------------------------
# O laudo descrevia o dispositivo so pelo que alguem digitou no cadastro. A
# extracao LE do aparelho fabricante, modelo, serie e versao do sistema, e
# nada disso chegava ao documento. Agora os modulos gravam em forma
# estruturada e o laudo separa as duas origens.
from core.aparelho import (  # noqa: E402
    gravar_identificacao,
    gravar_tecnicos,
    ler_caracteristicas,
)

with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "aq"
    aquisicao.mkdir()

    checar("sem modulo executado, nao ha o que apurar", ler_caracteristicas(aquisicao).vazio)

    gravar_tecnicos(aquisicao, {
        "fabricante": "samsung",
        "modelo": "SM-G980F",
        "numero_serie": "R58N123456",
        "versao_android": "13",
        "patch_seguranca": "",       # vazio de proposito
    })
    apuradas = ler_caracteristicas(aquisicao)
    pares = dict(apuradas.em_pares())

    checar("o que foi apurado aparece", not apuradas.vazio)
    checar("com o rotulo do laudo", pares.get("Fabricante") == "samsung")
    checar("e o modelo lido do aparelho", pares.get("Modelo") == "SM-G980F")
    # Campo vazio nao pode virar linha em branco no laudo: sugeriria falha de
    # leitura do documento em vez de dado nao obtido.
    checar("campo vazio NAO vira linha", "Patch de segurança" not in pares)

    # Os dois modulos gravam separadamente, e um nao depende do outro ter
    # rodado. O IMEI so entra quando de fato obtido.
    checar("sem identificacao, nao ha IMEI", "IMEI" not in pares)
    gravar_identificacao(aquisicao, {"imei": "353879104312345"})
    pares = dict(ler_caracteristicas(aquisicao).em_pares())
    checar("com identificacao, o IMEI entra", pares.get("IMEI") == "353879104312345")
    checar("sem apagar o que o outro modulo apurou", pares.get("Modelo") == "SM-G980F")

    # A ordem no laudo e a definida, nao a de insercao.
    rotulos = [r for r, _ in ler_caracteristicas(aquisicao).em_pares()]
    checar("a ordem dos campos e a do laudo", rotulos.index("Modelo") < rotulos.index("IMEI"))

    # JSON corrompido nao pode derrubar a geracao do laudo.
    (aquisicao / "device_specs" / "caracteristicas_tecnicas.json").write_text(
        "{ nao e json", encoding="utf-8"
    )
    sobrevivente = ler_caracteristicas(aquisicao)
    checar("json ilegivel nao estoura", isinstance(sobrevivente.valores, dict))
    checar("e o outro registro continua sendo lido", "imei" in sobrevivente.valores)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
