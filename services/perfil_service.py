"""
Perfil do examinador que está usando a suíte.

A suíte não tem tela de acesso: quem opera a estação já responde por ela.
O que a cadeia de custódia precisa é saber QUEM executou cada aquisição, e
isso vem do perfil do examinador — a estação guarda VÁRIOS, e o examinador
é escolhido ou cadastrado no início de cada extração. O escolhido é gravado
na aquisição, sob o selo, como DECLARAÇÃO do operador. A ferramenta
não confere identidade e por isso nunca escreve que conferiu.

A UI não fala com `core.operador`: fala com este serviço, que devolve
dicionários simples.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from core.operador import (
    NAO_DECLARADO,
    de_dicionario,
    gravar_perfil,
    ler_perfil,
    listar_perfis,
    pasta_do_perfil,
)

CAMPOS = (
    ("nome", "Nome completo"),
    ("registro_funcional", "Registro profissional"),
    ("unidade", "Instituição / laboratório"),
    ("email", "Contato (e-mail)"),
)

_pasta: Optional[Path] = None


def usar_perfil_em(pasta: Optional[Path]) -> None:
    """Aponta o serviço para outra pasta. Existe para os testes."""
    global _pasta
    _pasta = Path(pasta) if pasta else None


def local_do_perfil() -> str:
    return str(_pasta or pasta_do_perfil())


def _campos_de(operador) -> dict:
    dados = asdict(operador)
    return {chave: dados.get(chave, "") for chave, _ in CAMPOS}


def perfil() -> dict:
    """O examinador escolhido por último. Campos vazios quando não há nenhum."""
    return _campos_de(ler_perfil(_pasta))


def perfis() -> list:
    """Todos os examinadores cadastrados nesta estação, em ordem alfabética."""
    return [_campos_de(operador) for operador in listar_perfis(_pasta)]


def salvar_perfil(dados: dict, nome_anterior: str = "") -> None:
    """
    Cadastra ou atualiza o examinador (pelo nome) e o torna o escolhido.
    `nome_anterior` substitui o cadastro de quem teve o nome corrigido.
    """
    gravar_perfil(de_dicionario(dados), _pasta, nome_anterior)


def preenchido() -> bool:
    return ler_perfil(_pasta).declarado


def resumo() -> str:
    operador = ler_perfil(_pasta)
    if not operador.declarado:
        return f"Examinador: {NAO_DECLARADO}"
    return f"Examinador: {operador.resumo()}"


def perfil_para_a_aquisicao() -> dict:
    """Quem executa a aquisição, como declarado no perfil. Vazio se não preenchido."""
    return perfil() if preenchido() else {}
