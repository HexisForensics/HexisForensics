"""
A sessão: quem entrou na suíte, com a própria senha.

A interface fala com este serviço, e não com `core.acesso`. Ele guarda quem
está na sessão e o entrega à aquisição com a marca exata do que se sabe:
"sessão aberta com a senha do examinador nesta estação" — ou, para a conta
de testes, que é TESTE, sem valor pericial.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from core import acesso
from core.acesso import (  # noqa: F401
    NOME_FORENSIC_ADMIN,
    TAMANHO_MINIMO_DA_SENHA,
    ErroDeAcesso,
)
from core.operador import de_dicionario, gravar_perfil, ler_perfil

_pasta: Optional[Path] = None
_examinador: Optional[str] = None
_forensic_admin = False
_inicio: Optional[datetime] = None


def usar_pasta(pasta: Optional[Path]) -> None:
    """Aponta para outra pasta de cadastro. Existe para os testes."""
    global _pasta
    _pasta = Path(pasta) if pasta else None


# ---------------------------------------------------------------------------
# Tela de entrada
# ---------------------------------------------------------------------------
def examinadores() -> list:
    """Para a tela de entrada: dados e situação de acesso de cada examinador."""
    lista = []
    for situacao in acesso.situacoes(_pasta):
        dados, _ = acesso.resumo_do_cadastro(situacao.nome, _pasta)
        lista.append(dict(
            dados, tem_senha=situacao.tem_senha,
            bloqueado_ate=situacao.bloqueado_ate.strftime("%H:%M") if situacao.bloqueado_ate else "",
        ))
    return lista


def ultimo() -> str:
    """Quem entrou por último nesta estação: o pré-selecionado da tela de entrada."""
    return ler_perfil(_pasta).nome.strip()


def _abrir(nome: str) -> None:
    global _examinador, _forensic_admin, _inicio
    _examinador, _forensic_admin = nome.strip(), False
    _inicio = datetime.now()
    # O cadastro lembra o último a entrar: é o pré-selecionado da próxima vez.
    dados, _ = acesso.resumo_do_cadastro(_examinador, _pasta)
    gravar_perfil(de_dicionario(dados), _pasta)


def entrar(nome: str, senha: str) -> None:
    acesso.autenticar(nome, senha, _pasta)
    _abrir(nome)


def cadastrar_e_entrar(dados: dict, senha: str) -> str:
    """Cadastra e abre a sessão. Devolve o código de recuperação."""
    codigo = acesso.cadastrar(dados, senha, _pasta)
    _abrir(dados["nome"])
    return codigo


def criar_senha_e_entrar(nome: str, senha: str) -> str:
    codigo = acesso.criar_senha(nome, senha, _pasta)
    _abrir(nome)
    return codigo


def recuperar_e_entrar(nome: str, codigo: str, nova: str) -> str:
    novo = acesso.recuperar(nome, codigo, nova, _pasta)
    _abrir(nome)
    return novo


# --- Forensic Admin (só na versão de desenvolvimento)
def forensic_admin_disponivel() -> bool:
    return acesso.forensic_admin_disponivel()


def forensic_admin_configurado() -> bool:
    return acesso.forensic_admin_configurado(_pasta)


def _abrir_forensic_admin() -> None:
    global _examinador, _forensic_admin, _inicio
    _examinador, _forensic_admin, _inicio = NOME_FORENSIC_ADMIN, True, datetime.now()


def configurar_forensic_admin(senha: str) -> str:
    codigo = acesso.configurar_forensic_admin(senha, _pasta)
    _abrir_forensic_admin()
    return codigo


def entrar_forensic_admin(senha: str) -> None:
    acesso.autenticar_forensic_admin(senha, _pasta)
    _abrir_forensic_admin()


def recuperar_forensic_admin(codigo: str, nova: str) -> str:
    novo = acesso.recuperar_forensic_admin(codigo, nova, _pasta)
    _abrir_forensic_admin()
    return novo


def termos_aceitos() -> bool:
    """O examinador da sessão já aceitou a versão atual dos termos de uso?"""
    return ativa() and acesso.aceitou_os_termos(nome(), _pasta)


def aceitar_termos() -> None:
    """Registra o aceite dos termos pelo examinador da sessão, em nome próprio."""
    if not ativa():
        raise ErroDeAcesso("Não há sessão aberta para aceitar os termos.")
    acesso.aceitar_os_termos(nome(), _pasta)


def registrar_evento(evento: str, detalhe: str = "") -> None:
    acesso.registrar_evento(evento, nome() or "(sem sessão)", detalhe, _pasta)


def encerrar() -> None:
    global _examinador, _forensic_admin, _inicio
    _examinador, _forensic_admin, _inicio = None, False, None


# ---------------------------------------------------------------------------
# Durante a sessão
# ---------------------------------------------------------------------------
def ativa() -> bool:
    return _examinador is not None


def e_forensic_admin() -> bool:
    return _forensic_admin


def nome() -> str:
    return _examinador or ""


def inicio() -> str:
    return _inicio.strftime("%H:%M") if _inicio else ""


def iniciais() -> str:
    partes = [p for p in nome().split() if p[:1].isalpha()]
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def dados() -> dict:
    """Quem subscreve ou opera. Para o Forensic Admin, marcado como TESTE."""
    if not _examinador:
        return {}
    if _forensic_admin:
        return {"nome": NOME_FORENSIC_ADMIN, "unidade": "conta de testes da versão de desenvolvimento",
                "papel": acesso.PAPEL_TESTE}
    cadastro, _ = acesso.resumo_do_cadastro(_examinador, _pasta)
    return cadastro


def perfil_para_a_aquisicao() -> dict:
    """O operador, com a marca do acesso. Vazio sem sessão."""
    if not _examinador:
        return {}
    return dict(dados(), autenticacao=(
        acesso.AUTENTICACAO_DE_TESTE if _forensic_admin else acesso.AUTENTICACAO))


def resumo() -> str:
    if not _examinador:
        return "Nenhum examinador na sessão"
    if _forensic_admin:
        return f"{NOME_FORENSIC_ADMIN} · MODO DE TESTE · sessão desde {inicio()}"
    return f"Examinador: {_examinador} · sessão desde {inicio()}"


def trocar_minha_senha(atual: str, nova: str) -> None:
    acesso.trocar_senha(nome(), atual, nova, _pasta)


def novo_codigo_de_recuperacao() -> str:
    return acesso.novo_codigo(nome(), _pasta)


def redefinir_senha(alvo: str, nova: str) -> None:
    if not _forensic_admin:
        raise ErroDeAcesso("Ninguém redefine a senha de outro examinador. Quem esqueceu a "
                           "senha entra com o próprio código de recuperação.")
    acesso.redefinir_senha(alvo, nova, _pasta)


def cadastrar_examinador(dados_do_examinador: dict, senha: str) -> str:
    """Pelo Forensic Admin, em desenvolvimento. Devolve o código do novo examinador."""
    if not _forensic_admin:
        raise ErroDeAcesso("Novos examinadores se cadastram na tela de entrada.")
    return acesso.cadastrar(dados_do_examinador, senha, _pasta)


def excluir_examinador(alvo: str, minha_senha: str = "") -> bool:
    """
    O Forensic Admin exclui qualquer examinador; o examinador exclui só o
    próprio perfil, confirmando com a senha. Devolve `True` quando quem saiu
    foi o da sessão — a sessão termina junto.
    """
    proprio = not _forensic_admin and alvo.strip().lower() == nome().lower()
    if not _forensic_admin and not proprio:
        raise ErroDeAcesso("Você só pode excluir o seu próprio perfil.")
    if proprio:
        acesso.autenticar(alvo, minha_senha, _pasta)
    acesso.excluir(alvo, "pelo próprio examinador" if proprio else f"pelo {NOME_FORENSIC_ADMIN}",
                   _pasta)
    if proprio:
        encerrar()
    return proprio


def atualizar_dados(dados_do_examinador: dict, nome_anterior: str) -> None:
    """Corrige os dados de um examinador. A senha não é tocada."""
    if not _forensic_admin and nome_anterior.strip().lower() != nome().lower():
        raise ErroDeAcesso("Você só pode editar os seus próprios dados.")
    novo_nome = str(dados_do_examinador.get("nome", "")).strip()
    if not novo_nome:
        raise ErroDeAcesso("Informe o nome do examinador.")
    if novo_nome.lower() == NOME_FORENSIC_ADMIN.lower():
        raise ErroDeAcesso(f"'{NOME_FORENSIC_ADMIN}' é nome reservado.")
    outros = {s.nome.lower() for s in acesso.situacoes(_pasta)} - {nome_anterior.strip().lower()}
    if novo_nome.lower() in outros:
        raise ErroDeAcesso(f"Já existe um examinador chamado '{novo_nome}'.")
    anterior_ultimo = ultimo()
    gravar_perfil(de_dicionario(dados_do_examinador), _pasta, nome_anterior)
    global _examinador
    if not _forensic_admin and nome_anterior.strip().lower() == nome().lower():
        _examinador = novo_nome
    elif anterior_ultimo and anterior_ultimo.lower() != nome_anterior.strip().lower():
        # `gravar_perfil` marca o editado como "último"; o pré-selecionado
        # da próxima entrada continua sendo quem era.
        gravar_perfil(de_dicionario(acesso.resumo_do_cadastro(anterior_ultimo, _pasta)[0]), _pasta)
