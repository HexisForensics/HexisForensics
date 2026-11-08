"""
Acesso à suíte: a senha de cada examinador e a recuperação dela.

O que a senha garante, e o registro diz exatamente isto: que a sessão foi
aberta com a senha de um examinador cadastrado NESTA estação. Não é prova
de identidade (senha emprestada continua entrando) e não protege arquivo
nenhum (as pastas dos casos ficam abertas a quem usa o Windows). Serve à
AUTORIA: ninguém opera em nome de outro examinador por descuido.

Regras:

- A senha nunca é guardada: só a derivação scrypt com sal. O mesmo vale
  para o código de recuperação.
- Cada examinador recebe, ao criar a senha, o PRÓPRIO código de
  recuperação, mostrado uma vez. Usado, ele é substituído por outro.
- Não há administrador na versão distribuída: ninguém, nem o fabricante,
  mexe na senha de outro examinador. Quem perde a senha e o código cria
  um perfil novo; as aquisições antigas continuam no nome dele, sob o selo.
- Cinco senhas erradas seguidas travam aquele examinador por dez minutos.

**Forensic Admin** é a conta dos testes de quem desenvolve a suíte. Só
existe na versão de desenvolvimento (`core.instalacao.modo_desenvolvimento`):
o instalador e a pasta portátil não a oferecem. Tudo o que ela produz sai
marcado como TESTE, dentro do selo. Não é porta dos fundos: não há senha
fixa nem conta em estação de usuário — quem roda o código-fonte cria a
própria senha dela, na própria máquina.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from core import termos
from core.instalacao import modo_desenvolvimento
from core.operador import (  # noqa: F401
    PAPEL_TESTE,
    de_dicionario,
    gravar_cadastro,
    ler_cadastro,
    pasta_do_perfil,
)

TAMANHO_MINIMO_DA_SENHA = 6
TENTATIVAS_ANTES_DO_BLOQUEIO = 5
MINUTOS_DE_BLOQUEIO = 10
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
NOME_REGISTRO = "acessos.log"
ALFABETO_DO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I

AUTENTICACAO = "sessão aberta com a senha do examinador nesta estação"

NOME_FORENSIC_ADMIN = "Forensic Admin"
CHAVE_FORENSIC_ADMIN = "forensic_admin"
AUTENTICACAO_DE_TESTE = (
    "conta Forensic Admin da versão de desenvolvimento — uso de TESTE, sem valor pericial"
)


class ErroDeAcesso(Exception):
    """Operação recusada. A mensagem é para quem a pediu."""


@dataclass
class Situacao:
    nome: str
    tem_senha: bool
    bloqueado_ate: Optional[datetime]


# ---------------------------------------------------------------------------
# Derivação
# ---------------------------------------------------------------------------
def derivar(segredo: str, sal: Optional[bytes] = None) -> dict:
    sal = sal or secrets.token_bytes(16)
    derivada = hashlib.scrypt(segredo.encode("utf-8"), salt=sal,
                              n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return {"algoritmo": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
            "sal": sal.hex(), "derivada": derivada.hex()}


def confere(segredo: str, guardada) -> bool:
    try:
        calculada = hashlib.scrypt(
            segredo.encode("utf-8"), salt=bytes.fromhex(guardada["sal"]),
            n=int(guardada["n"]), r=int(guardada["r"]), p=int(guardada["p"]), dklen=32,
        )
        return hmac.compare_digest(calculada, bytes.fromhex(guardada["derivada"]))
    except (KeyError, ValueError, TypeError):
        return False


def validar_senha(senha: str) -> None:
    if len(senha or "") < TAMANHO_MINIMO_DA_SENHA:
        raise ErroDeAcesso(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_DA_SENHA} caracteres.")


def gerar_codigo() -> str:
    """Código de recuperação: 16 caracteres em 4 grupos, fáceis de ditar."""
    return "-".join("".join(secrets.choice(ALFABETO_DO_CODIGO) for _ in range(4))
                    for _ in range(4))


def normalizar_codigo(codigo: str) -> str:
    limpo = "".join(c for c in (codigo or "").upper() if c.isalnum())
    return "-".join(limpo[i:i + 4] for i in range(0, len(limpo), 4))


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------
def _agora() -> datetime:
    return datetime.now().astimezone()


def _pasta(pasta) -> Path:
    return Path(pasta or pasta_do_perfil())


def _registrar(pasta, evento: str, nome: str, detalhe: str = "") -> None:
    try:
        caminho = _pasta(pasta) / NOME_REGISTRO
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"{_agora().isoformat(timespec='seconds')}  {evento:<26} {nome}"
                          + (f"  — {detalhe}" if detalhe else "") + "\n")
    except OSError:
        pass  # registro de acesso não impede o acesso


def registrar_evento(evento: str, nome: str, detalhe: str = "", pasta=None) -> None:
    """Anota no registro de acessos um evento da sessão (bloqueio, saída)."""
    _registrar(pasta, evento, nome, detalhe)


def _achar(dados: dict, nome: str) -> dict:
    chave = (nome or "").strip().lower()
    for bruto in dados["perfis"]:
        if str(bruto.get("nome", "")).strip().lower() == chave:
            return bruto
    raise ErroDeAcesso(f"Examinador '{nome}' não cadastrado nesta estação.")


def _bloqueio(registro: dict) -> Optional[datetime]:
    try:
        ate = datetime.fromisoformat(str(registro.get("bloqueado_ate") or ""))
    except ValueError:
        return None
    return ate if ate > _agora() else None


def _definir(registro: dict, senha: str) -> str:
    """Grava a senha e um código de recuperação novo. Devolve o código."""
    validar_senha(senha)
    codigo = gerar_codigo()
    registro["senha"] = derivar(senha)
    registro["recuperacao"] = derivar(codigo)
    registro.pop("falhas", None)
    registro.pop("bloqueado_ate", None)
    return codigo


def _conferir(dados: dict, registro: dict, rotulo: str, senha: str, pasta) -> None:
    """Confere a senha de um registro, com a trava por tentativas."""
    ate = _bloqueio(registro)
    if ate:
        raise ErroDeAcesso(
            f"Senha errada {TENTATIVAS_ANTES_DO_BLOQUEIO} vezes seguidas. Tente de novo às "
            f"{ate.strftime('%H:%M')}."
        )
    if confere(senha, registro.get("senha")):
        if registro.pop("falhas", None) is not None or registro.pop("bloqueado_ate", None):
            gravar_cadastro(_pasta(pasta), dados)
        _registrar(pasta, "ENTRADA", rotulo)
        return
    registro["falhas"] = int(registro.get("falhas") or 0) + 1
    if registro["falhas"] >= TENTATIVAS_ANTES_DO_BLOQUEIO:
        registro["falhas"] = 0
        registro["bloqueado_ate"] = (_agora() + timedelta(minutes=MINUTOS_DE_BLOQUEIO)).isoformat(
            timespec="seconds")
        _registrar(pasta, "BLOQUEIO POR TENTATIVAS", rotulo,
                   f"{TENTATIVAS_ANTES_DO_BLOQUEIO} senhas erradas seguidas")
    else:
        _registrar(pasta, "SENHA INCORRETA", rotulo)
    gravar_cadastro(_pasta(pasta), dados)
    raise ErroDeAcesso("Senha incorreta.")


def _recuperar(dados: dict, registro: dict, rotulo: str, codigo: str, nova: str, pasta) -> str:
    if not registro.get("recuperacao"):
        raise ErroDeAcesso("Não há código de recuperação para este acesso.")
    if not confere(normalizar_codigo(codigo), registro["recuperacao"]):
        _registrar(pasta, "CÓDIGO INCORRETO", rotulo)
        raise ErroDeAcesso("Código de recuperação incorreto.")
    novo = _definir(registro, nova)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "SENHA RECUPERADA", rotulo, "com o código de recuperação; novo código emitido")
    return novo


# ---------------------------------------------------------------------------
# Examinadores
# ---------------------------------------------------------------------------
def situacoes(pasta=None) -> list:
    """Cada examinador: se tem senha e se está travado."""
    lista = []
    for bruto in ler_cadastro(_pasta(pasta))["perfis"]:
        nome = str(bruto.get("nome", "")).strip()
        if nome:
            lista.append(Situacao(nome, bool(bruto.get("senha")), _bloqueio(bruto)))
    return sorted(lista, key=lambda s: s.nome.lower())


def cadastrar(dados_do_examinador: dict, senha: str, pasta=None) -> str:
    """Cadastra um examinador novo, já com senha. Devolve o código de recuperação."""
    operador = de_dicionario(dados_do_examinador)
    if not operador.declarado:
        raise ErroDeAcesso("Informe o nome do examinador.")
    if operador.nome.strip().lower() == NOME_FORENSIC_ADMIN.lower():
        raise ErroDeAcesso(f"'{NOME_FORENSIC_ADMIN}' é nome reservado.")
    dados = ler_cadastro(_pasta(pasta))
    nomes = {str(b.get("nome", "")).strip().lower() for b in dados["perfis"]}
    if operador.nome.strip().lower() in nomes:
        raise ErroDeAcesso(f"Já existe um examinador chamado '{operador.nome.strip()}'.")
    bruto = {chave: valor for chave, valor in dados_do_examinador.items()
             if chave in ("nome", "registro_funcional", "unidade", "email", "funcao")}
    bruto["nome"] = operador.nome.strip()
    codigo = _definir(bruto, senha)
    dados["perfis"].append(bruto)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "EXAMINADOR CADASTRADO", bruto["nome"])
    return codigo


def criar_senha(nome: str, senha: str, pasta=None) -> str:
    """Primeiro acesso de quem já estava cadastrado sem senha."""
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    if bruto.get("senha"):
        raise ErroDeAcesso("Este examinador já tem senha.")
    codigo = _definir(bruto, senha)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "SENHA CRIADA", bruto["nome"], "primeiro acesso")
    return codigo


def autenticar(nome: str, senha: str, pasta=None) -> None:
    """Confere a senha. Levanta `ErroDeAcesso` com a mensagem para a tela."""
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    if not bruto.get("senha"):
        raise ErroDeAcesso("Este examinador ainda não tem senha: crie-a no primeiro acesso.")
    _conferir(dados, bruto, bruto["nome"], senha, pasta)


def trocar_senha(nome: str, atual: str, nova: str, pasta=None) -> None:
    autenticar(nome, atual, pasta)
    validar_senha(nova)
    dados = ler_cadastro(_pasta(pasta))
    _achar(dados, nome)["senha"] = derivar(nova)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "SENHA TROCADA", nome.strip(), "pelo próprio examinador")


def recuperar(nome: str, codigo: str, nova: str, pasta=None) -> str:
    """Quem esqueceu a senha entra com o código. Devolve o código novo."""
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    return _recuperar(dados, bruto, bruto["nome"], codigo, nova, pasta)


def novo_codigo(nome: str, pasta=None) -> str:
    """O examinador, na própria sessão, gera um código novo (o antigo deixa de valer)."""
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    codigo = gerar_codigo()
    bruto["recuperacao"] = derivar(codigo)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "NOVO CÓDIGO DE RECUPERAÇÃO", bruto["nome"])
    return codigo


def excluir(nome: str, motivo: str, pasta=None) -> None:
    """
    Tira o examinador do cadastro desta estação. As aquisições que ele fez
    NÃO mudam: o nome está gravado sob o selo de cada uma, e não é lido daqui.
    """
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    dados["perfis"] = [b for b in dados["perfis"] if b is not bruto]
    if str(dados.get("ultimo", "")).strip().lower() == bruto["nome"].lower():
        dados["ultimo"] = ""
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "EXAMINADOR EXCLUÍDO", bruto["nome"], motivo)


def _registro_para_termos(dados: dict, nome: str) -> dict:
    if (nome or "").strip().lower() == NOME_FORENSIC_ADMIN.lower():
        return _registro_do_admin(dados)
    return _achar(dados, nome)


def aceitou_os_termos(nome: str, pasta=None) -> bool:
    """`True` se o examinador já aceitou, em nome próprio, a versão atual dos termos."""
    try:
        return termos.aceite_vigente(_registro_para_termos(ler_cadastro(_pasta(pasta)), nome))
    except ErroDeAcesso:
        return False


def aceitar_os_termos(nome: str, pasta=None) -> None:
    """Guarda no cadastro o aceite da versão atual e o anota no registro de acessos."""
    dados = ler_cadastro(_pasta(pasta))
    registro = _registro_para_termos(dados, nome)
    registro["termos_aceitos"] = termos.VERSAO_DOS_TERMOS
    registro["termos_aceitos_em"] = _agora().isoformat(timespec="seconds")
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "TERMOS DE USO ACEITOS", str(registro.get("nome") or nome).strip(),
               f"versão {termos.VERSAO_DOS_TERMOS}, de {termos.DATA_DOS_TERMOS}")


def resumo_do_cadastro(nome: str, pasta=None) -> Tuple[dict, Situacao]:
    """Os dados de um examinador e a situação de acesso dele."""
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, nome)
    return ({c: str(bruto.get(c, "") or "") for c in
             ("nome", "registro_funcional", "unidade", "email")},
            Situacao(str(bruto["nome"]), bool(bruto.get("senha")), _bloqueio(bruto)))


# ---------------------------------------------------------------------------
# Forensic Admin — só na versão de desenvolvimento
# ---------------------------------------------------------------------------
def forensic_admin_disponivel() -> bool:
    return modo_desenvolvimento()


def _exigir_desenvolvimento() -> None:
    if not forensic_admin_disponivel():
        raise ErroDeAcesso("A conta Forensic Admin só existe na versão de desenvolvimento.")


def _registro_do_admin(dados: dict) -> dict:
    return dados.setdefault(CHAVE_FORENSIC_ADMIN, {})


def forensic_admin_configurado(pasta=None) -> bool:
    return bool(ler_cadastro(_pasta(pasta)).get(CHAVE_FORENSIC_ADMIN, {}).get("senha"))


def configurar_forensic_admin(senha: str, pasta=None) -> str:
    _exigir_desenvolvimento()
    dados = ler_cadastro(_pasta(pasta))
    registro = _registro_do_admin(dados)
    if registro.get("senha"):
        raise ErroDeAcesso("O Forensic Admin já está configurado nesta máquina.")
    codigo = _definir(registro, senha)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "FORENSIC ADMIN CONFIGURADO", NOME_FORENSIC_ADMIN)
    return codigo


def autenticar_forensic_admin(senha: str, pasta=None) -> None:
    _exigir_desenvolvimento()
    dados = ler_cadastro(_pasta(pasta))
    registro = _registro_do_admin(dados)
    if not registro.get("senha"):
        raise ErroDeAcesso("O Forensic Admin ainda não foi configurado nesta máquina.")
    _conferir(dados, registro, NOME_FORENSIC_ADMIN, senha, pasta)


def recuperar_forensic_admin(codigo: str, nova: str, pasta=None) -> str:
    _exigir_desenvolvimento()
    dados = ler_cadastro(_pasta(pasta))
    return _recuperar(dados, _registro_do_admin(dados), NOME_FORENSIC_ADMIN, codigo, nova, pasta)


def redefinir_senha(alvo: str, nova: str, pasta=None) -> None:
    """Só o Forensic Admin (na sessão, em desenvolvimento) redefine senha de examinador."""
    _exigir_desenvolvimento()
    validar_senha(nova)
    dados = ler_cadastro(_pasta(pasta))
    bruto = _achar(dados, alvo)
    bruto["senha"] = derivar(nova)
    bruto.pop("falhas", None)
    bruto.pop("bloqueado_ate", None)
    gravar_cadastro(_pasta(pasta), dados)
    _registrar(pasta, "SENHA REDEFINIDA", bruto["nome"], f"pelo {NOME_FORENSIC_ADMIN}")
