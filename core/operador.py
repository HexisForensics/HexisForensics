"""
Quem executou a aquisição.

O registro do procedimento dizia o caso, o aparelho, a estação, o relógio e
a versão da ferramenta — e não dizia QUEM. O campo "Perito / Operador" do
caderno saía em branco, e mesmo preenchido viria de um formulário aberto
dias depois da coleta: declaração posterior, fora do selo.

Aqui o operador entra no momento da aquisição, por duas vias que não se
confundem:

- o que ele DECLARA de si no perfil do examinador (nome, registro
  profissional, instituição) — a suíte não autentica ninguém, e
  por isso o registro diz "declarado", nunca "verificado";
- o que a ferramenta APURA sozinha: a conta do sistema em que a suíte está
  rodando.

As duas são gravadas no registro do procedimento e em `operador.json`
dentro da aquisição — antes do selo, portanto cobertas pelo manifesto. O
caderno lê daqui, e não de formulário.

Perfil não preenchido não impede a aquisição: o registro declara que o
operador NÃO FOI DECLARADO, e a conta da estação continua registrada.
Ausência dita é melhor que campo em branco.

Os nomes dos campos (`funcao`, `registro_funcional`, `unidade`) são os das
aquisições já gravadas e por isso não mudam; o que mudou foram os rótulos.
"""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

NOME_ARQUIVO = "operador.json"

NOME_ARQUIVO_PERFIL = "examinador.json"  # formato antigo, de perfil único
NOME_ARQUIVO_PERFIS = "examinadores.json"

NAO_DECLARADO = "NÃO DECLARADO"

# Papel do operador quando a aquisição foi feita pela conta de testes
# (Forensic Admin). Gravado sob o selo: um teste não vira exame depois.
PAPEL_TESTE = "teste"

# Chaves do cadastro que pertencem a `core.acesso` e sobrevivem à edição.
CHAVES_DE_ACESSO = ("senha", "administrador", "recuperacao", "falhas", "bloqueado_ate",
                    # O aceite dos termos de uso: editar os dados não o apaga.
                    "termos_aceitos", "termos_aceitos_em")


@dataclass
class Operador:
    nome: str = ""
    funcao: str = ""
    registro_funcional: str = ""
    unidade: str = ""
    email: str = ""
    # Só existem em aquisições feitas quando a suíte tinha tela de acesso.
    # Continuam sendo LIDOS, para que essas aquisições digam o que dizem.
    papel: str = ""
    autenticacao: str = ""

    @property
    def declarado(self) -> bool:
        return bool(self.nome.strip())

    @property
    def de_teste(self) -> bool:
        return self.papel.strip().lower() == PAPEL_TESTE

    def resumo(self) -> str:
        """Uma linha, para o caderno e para o console."""
        if not self.declarado:
            return NAO_DECLARADO
        complementos = [
            parte.strip()
            for parte in (self.funcao, self.registro_funcional, self.unidade)
            if parte.strip()
        ]
        identidade = self.nome.strip() + (f" <{self.email.strip()}>" if self.email.strip() else "")
        return identidade + (f" ({', '.join(complementos)})" if complementos else "")

    def em_linhas(self) -> list:
        """Linhas para o registro do procedimento."""
        if not self.declarado:
            return [
                f"Operador: {NAO_DECLARADO} — o perfil do examinador não estava "
                "preenchido na suíte no momento da aquisição."
            ]
        # Com sessão aberta por senha, o registro diz EXATAMENTE isso — e não
        # "autenticado" nem "verificado": senha emprestada também entra.
        primeira = (
            [f"Operador: {self.nome.strip()}", f"Acesso: {self.autenticacao.strip()}"]
            if self.autenticacao.strip() else
            [f"Operador (declarado): {self.nome.strip()}"]
        )
        linhas = primeira + [
            f"Registro profissional: {self.registro_funcional.strip() or 'não informado'}",
            f"Instituição / laboratório: {self.unidade.strip() or 'não informada'}",
        ]
        # A qualificação saiu do cadastro; só aparece no registro de quem a
        # trouxe de um cadastro antigo.
        if self.funcao.strip():
            linhas.insert(1, f"Qualificação: {self.funcao.strip()}")
        if self.email.strip():
            linhas.append(f"Contato: {self.email.strip()}")
        return linhas


def de_dicionario(dados) -> Operador:
    dados = dados if isinstance(dados, dict) else {}
    return Operador(
        nome=str(dados.get("nome", "") or ""),
        funcao=str(dados.get("funcao", "") or ""),
        registro_funcional=str(dados.get("registro_funcional", "") or ""),
        unidade=str(dados.get("unidade", "") or ""),
        email=str(dados.get("email", "") or ""),
        papel=str(dados.get("papel", "") or ""),
        autenticacao=str(dados.get("autenticacao", "") or ""),
    )


def conta_da_estacao() -> str:
    """Conta do sistema em que a suíte roda, ou vazio se não foi possível ler."""
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return ""


def gravar_na_aquisicao(pasta_aquisicao: Path, operador: Operador, conta: str) -> Path:
    """Grava `operador.json` na aquisição. Chamado na abertura, antes do selo."""
    caminho = Path(pasta_aquisicao) / NOME_ARQUIVO
    dados = dict(asdict(operador), declarado=operador.declarado, conta_da_estacao=conta)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


def ler_da_aquisicao(pasta_aquisicao: Path):
    """
    Devolve `(Operador, conta_da_estacao)` como gravados na aquisição, ou
    `None` quando a aquisição não tem o registro — o que acontece em toda
    aquisição anterior a este módulo. `None` e "não declarado" são coisas
    diferentes, e o caderno diz qual das duas.
    """
    caminho = Path(pasta_aquisicao) / NOME_ARQUIVO
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    return de_dicionario(dados), str(dados.get("conta_da_estacao", "") or "")


# ---------------------------------------------------------------------------
# Perfis de examinador — o que a estação lembra entre uma aquisição e outra.
#
# Uma estação é usada por mais de uma pessoa. Com um perfil só, quem
# começava a extração herdava em silêncio o nome de quem a usou por último —
# e a aquisição saía assinada pela pessoa errada. Por isso são VÁRIOS
# perfis, e a escolha é feita a cada extração.
# ---------------------------------------------------------------------------
def pasta_do_perfil() -> Path:
    """
    Onde moram os perfis: a pasta `HexisForensics` dentro de `%APPDATA%`,
    por conta do Windows.

    Fora da pasta do programa de propósito: reinstalar ou atualizar a suíte
    não pode apagá-los, e uma instalação em pasta protegida não teria como
    gravá-los.
    """
    base = Path(os.environ.get("APPDATA") or str(Path.home()))
    # Antes de 01/11/2026 a suíte se chamava Forensic Extractor. Estação que
    # já tem perfis na pasta antiga continua com ela: trocar de pasta faria
    # os examinadores cadastrados (e as senhas) sumirem da tela de entrada.
    anterior = base / "ForensicExtractor"
    atual = base / "HexisForensics"
    return anterior if anterior.is_dir() and _vazia_ou_ausente(atual) else atual


def _ler_arquivo_de_perfis(pasta: Path) -> dict:
    """`{"ultimo": nome, "perfis": [...]}`, migrando o arquivo de perfil único."""
    try:
        dados = json.loads((pasta / NOME_ARQUIVO_PERFIS).read_text(encoding="utf-8"))
        if isinstance(dados, dict) and isinstance(dados.get("perfis"), list):
            return dados
    except (OSError, ValueError):
        pass
    # Estação que já tinha o perfil único: ele vira o primeiro da lista.
    try:
        antigo = json.loads((pasta / NOME_ARQUIVO_PERFIL).read_text(encoding="utf-8"))
        if isinstance(antigo, dict) and str(antigo.get("nome", "")).strip():
            return {"ultimo": antigo["nome"], "perfis": [antigo]}
    except (OSError, ValueError):
        pass
    return {"ultimo": "", "perfis": []}


def ler_cadastro(pasta: Path | None = None) -> dict:
    """O arquivo inteiro de examinadores, com as chaves de acesso (`core.acesso`)."""
    return _ler_arquivo_de_perfis(Path(pasta or pasta_do_perfil()))


def gravar_cadastro(pasta: Path | None, dados: dict) -> Path:
    pasta = Path(pasta or pasta_do_perfil())
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_ARQUIVO_PERFIS
    # Grava ao lado e troca: um arquivo cortado no meio apagaria as senhas.
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)
    return caminho


def listar_perfis(pasta: Path | None = None) -> list:
    """Os examinadores cadastrados nesta estação, em ordem alfabética."""
    dados = _ler_arquivo_de_perfis(Path(pasta or pasta_do_perfil()))
    perfis = [de_dicionario(bruto) for bruto in dados["perfis"]]
    return sorted((p for p in perfis if p.declarado), key=lambda p: p.nome.strip().lower())


def ler_perfil(pasta: Path | None = None) -> Operador:
    """O examinador escolhido por último, ou um operador vazio (não declarado)."""
    pasta = Path(pasta or pasta_do_perfil())
    ultimo = str(_ler_arquivo_de_perfis(pasta).get("ultimo", "")).strip().lower()
    for perfil in listar_perfis(pasta):
        if perfil.nome.strip().lower() == ultimo:
            return perfil
    return Operador()


def gravar_perfil(
    operador: Operador, pasta: Path | None = None, nome_anterior: str = ""
) -> Path:
    """
    Cadastra ou atualiza o examinador (pelo nome) e o torna o escolhido.

    `nome_anterior` é para a edição que corrige o próprio nome: sem ele, a
    correção criaria um segundo examinador e deixaria o antigo na lista.
    """
    pasta = Path(pasta or pasta_do_perfil())
    pasta.mkdir(parents=True, exist_ok=True)
    novo = {
        chave: valor
        for chave, valor in asdict(operador).items()
        if chave not in ("papel", "autenticacao")
    }
    substituidos = {operador.nome.strip().lower(), nome_anterior.strip().lower()} - {""}
    perfis, acesso = [], {}
    for bruto in _ler_arquivo_de_perfis(pasta)["perfis"]:
        if str(bruto.get("nome", "")).strip().lower() in substituidos:
            # Editar os dados não pode apagar a senha nem o papel de
            # Administrador (chaves de `core.acesso`).
            acesso.update({c: v for c, v in bruto.items() if c in CHAVES_DE_ACESSO})
        else:
            perfis.append(bruto)
    perfis.append(dict(novo, **acesso))
    # As demais chaves do arquivo (a conta de testes, por exemplo) ficam.
    dados = _ler_arquivo_de_perfis(pasta)
    dados.update(ultimo=operador.nome.strip(), perfis=perfis)
    return gravar_cadastro(pasta, dados)


def _vazia_ou_ausente(pasta: Path) -> bool:
    """A pasta com o nome novo ainda não tem nada (o instalador a cria vazia)."""
    return not pasta.is_dir() or not any(pasta.iterdir())
