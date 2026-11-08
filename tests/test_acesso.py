"""
Testes do acesso: senha de cada examinador, a recuperação pelo próprio
código, a conta de testes (Forensic Admin) e o que a aquisição registra.

O registro precisa dizer exatamente o que a senha garante — "sessão aberta
com a senha do examinador nesta estação" — e nada além: nem "autenticado",
nem "verificado". E o que a conta de testes produz precisa sair marcado
como TESTE, sob o selo e em cada página.
"""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core import acesso  # noqa: E402
from core.acesso import ErroDeAcesso  # noqa: E402
from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from core.operador import ler_da_aquisicao  # noqa: E402
from services import laudo_service, relatorio_extracao_service, sessao_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402

aplicacao = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def recusa(funcao, *args) -> str:
    try:
        funcao(*args)
    except ErroDeAcesso as erro:
        return str(erro)
    return ""


def texto_do_pdf(caminho: Path) -> str:
    documento = QPdfDocument()
    documento.load(str(caminho))
    return " ".join(" ".join(documento.getAllText(p).text().split())
                    for p in range(documento.pageCount()))


def aquisicao(raiz: Path, minuto: int) -> Path:
    pasta = criar_pasta_aquisicao(raiz, "CASO_A", "Android", datetime(2026, 10, 24, 10, minuto))
    servico = CaseService(raiz)
    servico.abrir_registro_procedimento(pasta, "CASO_A", "Android", "SERIAL")
    servico.registrar_operador(pasta, sessao_service.perfil_para_a_aquisicao())
    servico.encerrar_registro_procedimento("0 módulo(s).")
    gerar_manifesto(pasta)
    return pasta


FILIPE = {"nome": "Filipe de Morais", "registro_funcional": "123", "unidade": "Lab Central"}
ANA = {"nome": "Ana Souza", "registro_funcional": "456", "unidade": "Lab Central"}

with tempfile.TemporaryDirectory() as temporario:
    pasta = Path(temporario) / "cadastro"
    raiz = Path(temporario) / "extracoes"
    sessao_service.usar_pasta(pasta)

    # -----------------------------------------------------------------------
    print("\n[1] Cada examinador recebe o PRÓPRIO código de recuperação")
    # -----------------------------------------------------------------------
    codigo = sessao_service.cadastrar_e_entrar(FILIPE, "segredo1")
    checar("o cadastro devolve o código (16 caracteres em 4 grupos)",
           len(codigo) == 19 and codigo.count("-") == 3)
    checar("e a sessão fica aberta com ele", sessao_service.nome() == "Filipe de Morais")
    codigo_ana = acesso.cadastrar(ANA, "senhaana", pasta)
    checar("o segundo examinador também recebe o seu", bool(codigo_ana) and codigo_ana != codigo)
    bruto = (pasta / "examinadores.json").read_text(encoding="utf-8")
    checar("nem senha nem código ficam gravados em texto",
           "segredo1" not in bruto and codigo not in bruto and "scrypt" in bruto)
    checar("não existe papel de administrador entre os examinadores", "administrador" not in bruto)
    checar("senha curta é recusada",
           "pelo menos 6" in recusa(acesso.cadastrar, {"nome": "Beto"}, "123", pasta))
    checar("nome repetido é recusado", "Já existe" in recusa(acesso.cadastrar, FILIPE, "xxxxxx", pasta))
    checar("'Forensic Admin' é nome reservado",
           "reservado" in recusa(acesso.cadastrar, {"nome": "forensic admin"}, "xxxxxx", pasta))

    # -----------------------------------------------------------------------
    print("\n[2] Entrar, errar e travar")
    # -----------------------------------------------------------------------
    sessao_service.entrar("Ana Souza", "senhaana")
    checar("senha certa abre a sessão", sessao_service.nome() == "Ana Souza")
    checar("senha errada é recusada sem dizer mais nada",
           recusa(acesso.autenticar, "Ana Souza", "errada", pasta) == "Senha incorreta.")
    for _ in range(4):
        recusa(acesso.autenticar, "Ana Souza", "errada", pasta)
    checar("cinco erros seguidos travam o examinador",
           "Tente de novo às" in recusa(acesso.autenticar, "Ana Souza", "senhaana", pasta))
    checar("o bloqueio vai para o registro de acessos",
           "BLOQUEIO POR TENTATIVAS" in (pasta / acesso.NOME_REGISTRO).read_text(encoding="utf-8"))

    # -----------------------------------------------------------------------
    print("\n[3] Ninguém mexe na senha nem nos dados de outro examinador")
    # -----------------------------------------------------------------------
    sessao_service.entrar("Filipe de Morais", "segredo1")
    checar("examinador não redefine a senha de outro",
           "Ninguém redefine" in recusa(sessao_service.redefinir_senha, "Ana Souza", "tomada1"))
    checar("nem edita os dados de outro",
           "próprios dados" in recusa(sessao_service.atualizar_dados, ANA, "Ana Souza"))

    # -----------------------------------------------------------------------
    print("\n[4] Quem esqueceu a senha entra com o próprio código")
    # -----------------------------------------------------------------------
    checar("código errado é recusado",
           "incorreto" in recusa(acesso.recuperar, "Ana Souza", "AAAA-AAAA-AAAA-AAAA",
                                  "outra12", pasta))
    novo = sessao_service.recuperar_e_entrar("Ana Souza", codigo_ana.lower().replace("-", " "),
                                            "outra12")
    checar("o código certo (em minúsculas, sem traços) redefine, destrava e entra",
           sessao_service.nome() == "Ana Souza"
           and not recusa(acesso.autenticar, "Ana Souza", "outra12", pasta))
    checar("e o código usado deixa de valer, trocado por outro",
           novo != codigo_ana and "incorreto" in recusa(acesso.recuperar, "Ana Souza", codigo_ana,
                                                         "outra13", pasta))
    terceiro = sessao_service.novo_codigo_de_recuperacao()
    checar("o examinador gera um código novo na própria sessão, e o anterior cai",
           "incorreto" in recusa(acesso.recuperar, "Ana Souza", novo, "outra14", pasta)
           and not recusa(acesso.recuperar, "Ana Souza", terceiro, "outra15", pasta))

    # -----------------------------------------------------------------------
    print("\n[5] Editar os próprios dados não apaga a senha")
    # -----------------------------------------------------------------------
    sessao_service.entrar("Filipe de Morais", "segredo1")
    sessao_service.atualizar_dados(dict(FILIPE, unidade="Lab Novo"), "Filipe de Morais")
    dados, situacao = acesso.resumo_do_cadastro("Filipe de Morais", pasta)
    checar("os dados mudam", dados["unidade"] == "Lab Novo")
    checar("e a senha continua",
           situacao.tem_senha and not recusa(acesso.autenticar, "Filipe de Morais", "segredo1", pasta))
    sessao_service.atualizar_dados(dict(FILIPE, nome="Filipe M. de Morais"), "Filipe de Morais")
    checar("corrigir o próprio nome mantém a sessão e a senha",
           sessao_service.nome() == "Filipe M. de Morais"
           and not recusa(acesso.autenticar, "Filipe M. de Morais", "segredo1", pasta))

    # -----------------------------------------------------------------------
    print("\n[6] Quem já estava cadastrado sem senha cria no primeiro acesso")
    # -----------------------------------------------------------------------
    antiga = Path(temporario) / "estacao_antiga"
    antiga.mkdir()
    (antiga / "examinadores.json").write_text(json.dumps({
        "ultimo": "Carla", "perfis": [{"nome": "Carla"}, {"nome": "Davi"}]}), encoding="utf-8")
    sessao_service.usar_pasta(antiga)
    checar("os cadastros antigos aparecem sem senha",
           [e["tem_senha"] for e in sessao_service.examinadores()] == [False, False])
    checar("e o último a usar vem pré-selecionado", sessao_service.ultimo() == "Carla")
    checar("sem senha não se entra",
           "ainda não tem senha" in recusa(sessao_service.entrar, "Davi", "qualquer"))
    checar("criar a senha devolve o código de recuperação",
           bool(sessao_service.criar_senha_e_entrar("Carla", "senhacarla")))

    print("\n[6b] Excluir: o próprio perfil, com a senha; nunca o de outro")
    checar("examinador não exclui o perfil de outro",
           "próprio perfil" in recusa(sessao_service.excluir_examinador, "Davi", ""))
    checar("excluir o próprio exige a senha certa",
           recusa(sessao_service.excluir_examinador, "Carla", "errada") == "Senha incorreta.")
    feita_por_carla = aquisicao(raiz, 9)
    checar("com a senha, exclui e encerra a sessão",
           sessao_service.excluir_examinador("Carla", "senhacarla") is True
           and not sessao_service.ativa()
           and "Carla" not in {e["nome"] for e in sessao_service.examinadores()})
    checar("a exclusão fica no registro de acessos",
           "EXAMINADOR EXCLUÍDO" in (antiga / acesso.NOME_REGISTRO).read_text(encoding="utf-8"))
    checar("e a aquisição que ela fez continua no nome dela",
           ler_da_aquisicao(feita_por_carla)[0].nome == "Carla")
    sessao_service.criar_senha_e_entrar("Davi", "senhadavi")

    # -----------------------------------------------------------------------
    print("\n[7] A aquisição registra a sessão, e só o que ela garante")
    # -----------------------------------------------------------------------
    real = aquisicao(raiz, 0)
    diario = (real / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro diz quem e como a sessão foi aberta",
           "Operador: Davi" in diario
           and "Acesso: sessão aberta com a senha do examinador nesta estação" in diario)
    checar("e não afirma autenticação nem verificação de identidade",
           "autenticad" not in diario.lower() and "verificad" not in diario.lower())
    operador, _ = ler_da_aquisicao(real)
    checar("operador.json guarda a marca do acesso, sem papel de teste",
           operador.autenticacao == acesso.AUTENTICACAO and not operador.de_teste)
    relatorio = relatorio_extracao_service.gerar(real)
    checar("documento de examinador NÃO leva a tarja de teste",
           "DOCUMENTO DE TESTE" not in texto_do_pdf(relatorio.caminho))

    # -----------------------------------------------------------------------
    print("\n[8] Forensic Admin: só em desenvolvimento, e tudo sai como TESTE")
    # -----------------------------------------------------------------------
    sessao_service.usar_pasta(pasta)
    original = acesso.modo_desenvolvimento
    acesso.modo_desenvolvimento = lambda: False
    checar("fora da versão de desenvolvimento a conta NÃO existe",
           not sessao_service.forensic_admin_disponivel()
           and "desenvolvimento" in recusa(sessao_service.configurar_forensic_admin, "admin123")
           and "desenvolvimento" in recusa(sessao_service.entrar_forensic_admin, "admin123"))
    acesso.modo_desenvolvimento = lambda: True
    codigo_admin = sessao_service.configurar_forensic_admin("admin123")
    checar("em desenvolvimento, quem roda o código cria a senha dela e recebe código",
           bool(codigo_admin) and sessao_service.e_forensic_admin())
    checar("não há senha fixa: configurar de novo é recusado",
           "já está configurado" in recusa(sessao_service.configurar_forensic_admin, "outra123"))
    checar("os examinadores continuam no cadastro, intocados",
           {"Ana Souza", "Filipe M. de Morais"} <= {e["nome"] for e in sessao_service.examinadores()})
    sessao_service.redefinir_senha("Ana Souza", "redefinida1")
    checar("a conta de testes redefine senha de examinador, e fica registrado",
           not recusa(acesso.autenticar, "Ana Souza", "redefinida1", pasta)
           and "pelo Forensic Admin" in (pasta / acesso.NOME_REGISTRO).read_text(encoding="utf-8"))
    sessao_service.entrar_forensic_admin("admin123")
    checar("a conta de testes exclui qualquer examinador, sem encerrar a própria sessão",
           sessao_service.excluir_examinador("Ana Souza") is False
           and sessao_service.e_forensic_admin()
           and "Ana Souza" not in {e["nome"] for e in sessao_service.examinadores()})

    teste = aquisicao(raiz, 1)
    diario = (teste / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro da aquisição diz TESTE, sem valor pericial",
           "Operador: Forensic Admin" in diario and "uso de TESTE, sem valor pericial" in diario)
    operador, _ = ler_da_aquisicao(teste)
    checar("e operador.json, sob o selo, marca o papel de teste", operador.de_teste)
    texto = texto_do_pdf(relatorio_extracao_service.gerar(teste).caminho)
    checar("o Relatório de Extração leva a tarja em cada página",
           texto.count("DOCUMENTO DE TESTE — SEM VALOR PERICIAL") >= 2)
    laudo = laudo_service.gerar(real, {}, examinador=sessao_service.dados())
    checar("laudo subscrito pela conta de testes, mesmo sobre aquisição real, leva a tarja",
           "DOCUMENTO DE TESTE" in texto_do_pdf(laudo.caminho))
    acesso.modo_desenvolvimento = original
    sessao_service.encerrar()
    checar("sem sessão, nada é entregue à aquisição",
           sessao_service.perfil_para_a_aquisicao() == {})
    sessao_service.usar_pasta(None)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
