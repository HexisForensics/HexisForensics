"""
Testes do registro de QUEM executou a aquisicao.

O registro do procedimento dizia caso, aparelho, estacao, relogio e versao
da ferramenta -- e nao dizia quem. O campo "Perito / Operador" do caderno
lia `dados_form.get("operador")`, chave que o formulario NUNCA preencheu:
saia em branco em todo caderno ja emitido.
"""

import json
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import conferir_manifesto, gerar_manifesto  # noqa: E402
from core.operador import NAO_DECLARADO, Operador, ler_da_aquisicao  # noqa: E402
from services.caderno_service import _operador_da_aquisicao  # noqa: E402
from services.case_service import CaseService  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


PERFIL = {
    "nome": "Fulano de Tal",
    "funcao": "Perito em computação forense",
    "registro_funcional": "123.456-7",
    "unidade": "Unidade de Teste",
}


def abrir(raiz, nome, perfil):
    servico = CaseService(raiz)
    pasta = raiz / "CASO_T" / nome
    pasta.mkdir(parents=True)
    servico.abrir_registro_procedimento(pasta, "CASO_T", "Android", "SERIAL123")
    resumo = servico.registrar_operador(pasta, perfil)
    return pasta, resumo


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp)

    # -----------------------------------------------------------------------
    print("\n[1] Operador declarado entra no registro e na aquisicao")
    # -----------------------------------------------------------------------
    pasta, resumo = abrir(raiz, "android_20260101_000000", PERFIL)
    diario = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")

    checar("o registro tem o bloco do operador", "OPERADOR DA AQUISIÇÃO" in diario)
    checar("com o nome, marcado como DECLARADO",
           "Operador (declarado): Fulano de Tal" in diario)
    checar("com o registro funcional", "123.456-7" in diario)
    checar("a conta da estacao vem em linha propria, marcada como APURADA",
           "apurada pela ferramenta" in diario)
    checar("o bloco vem depois do cabecalho e nao o substitui",
           diario.index("Dispositivo: SERIAL123") < diario.index("OPERADOR DA AQUISIÇÃO"))

    lido = ler_da_aquisicao(pasta)
    checar("operador.json e gravado na aquisicao", lido is not None)
    checar("e devolve o mesmo operador", lido[0].nome == "Fulano de Tal")
    checar("o resumo de uma linha traz nome e complementos",
           resumo.startswith("Fulano de Tal (") and "123.456-7" in resumo)

    # -----------------------------------------------------------------------
    print("\n[2] O registro fica SOB O SELO: alterar o operador depois e detectado")
    # -----------------------------------------------------------------------
    gerar_manifesto(pasta)
    checar("a aquisicao selada confere integra", conferir_manifesto(pasta).integro)
    dados = json.loads((pasta / "operador.json").read_text(encoding="utf-8"))
    dados["nome"] = "Outra Pessoa"
    (pasta / "operador.json").write_text(json.dumps(dados), encoding="utf-8")
    checar("trocar o nome depois do selo quebra a conferencia",
           not conferir_manifesto(pasta).integro)

    # -----------------------------------------------------------------------
    print("\n[3] Sem perfil: a ausencia e DITA, e a aquisicao nao e impedida")
    # -----------------------------------------------------------------------
    pasta_sem, resumo_sem = abrir(raiz, "android_20260102_000000", {})
    diario_sem = (pasta_sem / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o resumo declara a ausencia", resumo_sem == NAO_DECLARADO)
    checar("o registro declara a ausencia", NAO_DECLARADO in diario_sem)
    checar("e nao inventa um nome a partir da conta do sistema",
           "Operador (declarado)" not in diario_sem)
    checar("a conta da estacao e registrada mesmo assim",
           "apurada pela ferramenta" in diario_sem)
    checar("nome so com espacos nao conta como declarado",
           not Operador(nome="   ").declarado)

    # -----------------------------------------------------------------------
    print("\n[4] O caderno le da AQUISICAO, e distingue os tres casos")
    # -----------------------------------------------------------------------
    checar("declarado: mostra o operador gravado",
           "Fulano de Tal" not in _operador_da_aquisicao(pasta)
           and "Outra Pessoa" in _operador_da_aquisicao(pasta))  # le o que esta no disco
    checar("nao declarado: diz NAO DECLARADO", NAO_DECLARADO in _operador_da_aquisicao(pasta_sem))
    antiga = raiz / "CASO_T" / "android_20250101_000000"
    antiga.mkdir()
    checar("aquisicao antiga, sem o registro: diz que nao foi registrado",
           "Não registrado nesta aquisição" in _operador_da_aquisicao(antiga))
    checar("e isso NAO se confunde com 'nao declarado'",
           NAO_DECLARADO not in _operador_da_aquisicao(antiga))

    # -----------------------------------------------------------------------
    print("\n[5] O perfil do examinador: a estacao lembra, e nada e 'verificado'")
    # -----------------------------------------------------------------------
    from services import perfil_service  # noqa: E402

    perfil_service.usar_perfil_em(raiz / "perfil")
    checar("sem perfil gravado, a suite diz NAO DECLARADO",
           not perfil_service.preenchido() and NAO_DECLARADO in perfil_service.resumo())
    checar("e nao entrega operador nenhum a aquisicao",
           perfil_service.perfil_para_a_aquisicao() == {})

    perfil_service.salvar_perfil(dict(PERFIL, email="fulano@exemplo.com"))
    checar("perfil gravado e lido de volta", perfil_service.perfil()["nome"] == "Fulano de Tal")
    checar("e passa a valer para a aquisicao",
           perfil_service.perfil_para_a_aquisicao()["registro_funcional"] == "123.456-7")

    pasta_perfil, resumo_perfil = abrir(
        raiz, "android_20260103_000000", perfil_service.perfil_para_a_aquisicao())
    diario_perfil = (pasta_perfil / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro usa os rotulos de pericia convencional",
           "Registro profissional: 123.456-7" in diario_perfil
           and "Instituição / laboratório: Unidade de Teste" in diario_perfil)
    checar("o operador entra como DECLARADO, nunca como autenticado",
           "Operador (declarado): Fulano de Tal" in diario_perfil
           and "autenticado" not in diario_perfil.lower())
    checar("o contato aparece no registro e no resumo",
           "Contato: fulano@exemplo.com" in diario_perfil and "<fulano@exemplo.com>" in resumo_perfil)
    gravado = json.loads((pasta_perfil / "operador.json").read_text(encoding="utf-8"))
    checar("operador.json nao afirma autenticacao nenhuma", gravado["autenticacao"] == "")

    # -----------------------------------------------------------------------
    print("\n[6] A estacao guarda VARIOS examinadores; a escolha e por extracao")
    # -----------------------------------------------------------------------
    perfil_service.salvar_perfil({"nome": "Beltrana Souza", "unidade": "Laboratório B"})
    nomes = [p["nome"] for p in perfil_service.perfis()]
    checar("o segundo examinador NAO substitui o primeiro",
           nomes == ["Beltrana Souza", "Fulano de Tal"])
    checar("o escolhido passa a ser o ultimo cadastrado",
           perfil_service.perfil()["nome"] == "Beltrana Souza")
    perfil_service.salvar_perfil(dict(PERFIL, unidade="Laboratório A"))
    checar("escolher de novo um existente atualiza, sem duplicar",
           len(perfil_service.perfis()) == 2
           and perfil_service.perfil()["unidade"] == "Laboratório A")
    checar("e os dados do outro continuam como estavam",
           next(p for p in perfil_service.perfis() if p["nome"] == "Beltrana Souza")["unidade"]
           == "Laboratório B")
    checar("a qualificacao nao faz mais parte do cadastro",
           "funcao" not in perfil_service.perfil())

    # Corrigir o NOME de um examinador nao pode deixar o antigo na lista.
    perfil_service.salvar_perfil({"nome": "Beltrana Souza Lima", "unidade": "Laboratório B"},
                                 nome_anterior="Beltrana Souza")
    nomes = [p["nome"] for p in perfil_service.perfis()]
    checar("renomear substitui o cadastro, sem duplicar",
           nomes == ["Beltrana Souza Lima", "Fulano de Tal"])

    # O examinador aparece no caso como ficou gravado NA aquisicao.
    from services.case_service import CaseService, examinador_da_aquisicao  # noqa: E402

    checar("o caso mostra o examinador gravado na aquisicao",
           examinador_da_aquisicao(pasta) == "Outra Pessoa")
    checar("aquisicao sem perfil declarado diz NAO DECLARADO",
           NAO_DECLARADO in examinador_da_aquisicao(pasta_sem))
    checar("aquisicao anterior ao registro diz que nao foi registrado",
           examinador_da_aquisicao(antiga) == "examinador não registrado")
    resumo_do_caso = CaseService(raiz).resumo_do_caso(raiz / "CASO_T")
    checar("o resumo do caso reune os examinadores de todas as aquisicoes",
           "Outra Pessoa" in resumo_do_caso.examinadores
           and "Fulano de Tal" in resumo_do_caso.examinadores)

    # Estacao que ja tinha o arquivo de perfil unico: ele nao se perde.
    antiga = raiz / "perfil_antigo"
    antiga.mkdir()
    (antiga / "examinador.json").write_text(
        json.dumps({"nome": "Perfil Antigo", "funcao": "Perito"}), encoding="utf-8")
    perfil_service.usar_perfil_em(antiga)
    checar("o perfil unico de antes vira o primeiro da lista, ja escolhido",
           [p["nome"] for p in perfil_service.perfis()] == ["Perfil Antigo"]
           and perfil_service.perfil()["nome"] == "Perfil Antigo")
    perfil_service.usar_perfil_em(None)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
