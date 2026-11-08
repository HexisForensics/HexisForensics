"""
Método declarado de uma aquisição: o que os módulos escolhidos alcançam,
o que não alcançam e o que alteram no aparelho.

Cada extrator declara isso sobre si em `limitacoes_conhecidas`,
`alteracoes_no_dispositivo` e `perfil_minimo` (ver `core.base_extractor`).
Este módulo consolida a declaração dos módulos **efetivamente escolhidos**
para esta coleta e a grava dentro da aquisição, antes do selo.

Por que fica gravado, em vez de ser montado na hora do laudo: a combinação
de módulos muda de exame para exame, e é ela que define o alcance daquela
coleta. Reconstruir isso depois exigiria adivinhar o que foi selecionado —
e um laudo emitido meses adiante, com a ferramenta já atualizada, exibiria
as limitações da versão nova como se fossem as da coleta antiga. Gravado no
dia e coberto pelo manifesto, o alcance declarado fica preso ao exame que
de fato ocorreu.

O que este registro NÃO faz: dizer que uma alteração ocorreu. Ele declara o
que a execução **pode** alterar, para o examinador saber antes de começar.
A alteração que efetivamente aconteceu é registrada pelo próprio módulo, no
`registro_procedimento.txt`, no momento em que acontece. Confundir as duas
faria o caso afirmar que se mexeu no aparelho quando talvez não se tenha
mexido.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PASTA_METODO = "metodo"
NOME_METODO = "metodo_declarado.txt"
NOME_METODO_DADOS = "metodo_declarado.json"

LARGURA = 70


@dataclass
class ModuloDeclarado:
    """O que um módulo declara sobre o próprio alcance."""

    identificador: str
    nome: str
    perfil: str = ""
    limitacoes: list = field(default_factory=list)
    alteracoes: list = field(default_factory=list)


@dataclass
class MetodoDeclarado:
    """Declaração consolidada dos módulos escolhidos para esta aquisição."""

    modulos: list = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not self.modulos

    @property
    def tem_limitacao(self) -> bool:
        return any(modulo.limitacoes for modulo in self.modulos)

    @property
    def tem_alteracao(self) -> bool:
        return any(modulo.alteracoes for modulo in self.modulos)

    @property
    def perfis_exigidos(self) -> list:
        """Perfis distintos exigidos, preservando a ordem de aparição."""
        vistos = []
        for modulo in self.modulos:
            if modulo.perfil and modulo.perfil not in vistos:
                vistos.append(modulo.perfil)
        return vistos


def resumir_modulos(pasta_aquisicao) -> str:
    """
    Nomes dos módulos declarados nesta aquisição, em uma linha.

    Existe para o campo de modalidade do formulário parar de vir com uma
    constante escrita no código. Ele trazia, sempre, "Lógico (Backup ADB /
    API do Sistema)" — e o rótulo do grupo ainda dizia "Pré-detectado",
    prometendo uma detecção que nunca houve. Uma aquisição de imagem
    bit-a-bit de volume, sem ADB nenhum envolvido, saía no documento
    descrita como backup lógico via ADB, e o examinador que aceitasse o
    padrão assinava um método que não foi o empregado.

    Devolve string vazia quando não há registro: o formulário deixa o
    campo em branco e avisa, em vez de oferecer um palpite plausível que
    ninguém tem motivo para questionar.
    """
    metodo = ler_metodo(pasta_aquisicao)
    if metodo.vazio:
        return ""
    return "; ".join(modulo.nome for modulo in metodo.modulos if modulo.nome)


def descrever(extratores) -> MetodoDeclarado:
    """
    Lê a declaração de cada extrator escolhido.

    Aceita classes ou instâncias, e usa `getattr` com padrão: um módulo que
    ainda não declare nada entra na lista com o alcance em branco, em vez de
    derrubar a coleta. A cobrança de que ele declare é da suíte de testes,
    não do meio de uma extração em andamento.
    """
    modulos = []
    for extrator in extratores:
        perfil = getattr(extrator, "perfil_minimo", None)
        modulos.append(
            ModuloDeclarado(
                identificador=getattr(extrator, "id", ""),
                nome=getattr(extrator, "nome_exibicao", ""),
                perfil=getattr(perfil, "value", "") if perfil is not None else "",
                limitacoes=[str(item) for item in getattr(extrator, "limitacoes_conhecidas", ())],
                alteracoes=[
                    (str(alteracao), str(justificativa))
                    for alteracao, justificativa in getattr(
                        extrator, "alteracoes_no_dispositivo", ()
                    )
                ],
            )
        )
    return MetodoDeclarado(modulos=modulos)


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------
def gravar_metodo(pasta_aquisicao: Path, metodo: MetodoDeclarado) -> Path:
    """Grava o método declarado na aquisição, para ser coberto pelo selo."""
    pasta = Path(pasta_aquisicao) / PASTA_METODO
    pasta.mkdir(parents=True, exist_ok=True)

    caminho = pasta / NOME_METODO
    caminho.write_text("\n".join(_linhas(metodo)) + "\n", encoding="utf-8")
    (pasta / NOME_METODO_DADOS).write_text(
        json.dumps(_para_dicionario(metodo), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return caminho


def ler_metodo(pasta_aquisicao: Path) -> MetodoDeclarado:
    """Método declarado desta aquisição — vazio se não houver registro."""
    caminho = Path(pasta_aquisicao) / PASTA_METODO / NOME_METODO_DADOS
    if not caminho.is_file():
        return MetodoDeclarado()

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MetodoDeclarado()

    modulos = []
    for bruto in dados.get("modulos", []):
        modulos.append(
            ModuloDeclarado(
                identificador=bruto.get("id", ""),
                nome=bruto.get("nome", ""),
                perfil=bruto.get("perfil", ""),
                limitacoes=list(bruto.get("limitacoes", [])),
                alteracoes=[
                    (par[0], par[1])
                    for par in bruto.get("alteracoes", [])
                    if isinstance(par, (list, tuple)) and len(par) == 2
                ],
            )
        )
    return MetodoDeclarado(modulos=modulos)


def _para_dicionario(metodo: MetodoDeclarado) -> dict:
    return {
        "modulos": [
            {
                "id": modulo.identificador,
                "nome": modulo.nome,
                "perfil": modulo.perfil,
                "limitacoes": list(modulo.limitacoes),
                "alteracoes": [list(par) for par in modulo.alteracoes],
            }
            for modulo in metodo.modulos
        ]
    }


# ---------------------------------------------------------------------------
# Texto para quem lê o caso
# ---------------------------------------------------------------------------
def _quebrar(texto: str, recuo: str = "      ") -> list:
    """Quebra o texto em linhas de largura fixa, para o arquivo do caso."""
    palavras = texto.split()
    linhas, atual = [], recuo
    for palavra in palavras:
        candidata = f"{atual} {palavra}".rstrip() if atual.strip() else f"{recuo}{palavra}"
        if len(candidata) > LARGURA and atual.strip():
            linhas.append(atual)
            atual = f"{recuo}{palavra}"
        else:
            atual = candidata
    if atual.strip():
        linhas.append(atual)
    return linhas


def _linhas(metodo: MetodoDeclarado) -> list:
    linhas = [
        "=" * LARGURA,
        "MÉTODO DECLARADO DESTA AQUISIÇÃO".center(LARGURA),
        "=" * LARGURA,
        "",
    ]

    if metodo.vazio:
        linhas += ["Nenhum módulo foi registrado para esta aquisição.", ""]
        return linhas + _nota() + ["=" * LARGURA]

    perfis = metodo.perfis_exigidos
    if perfis:
        linhas += ["Competência exigida: " + "; ".join(perfis), ""]

    for ordem, modulo in enumerate(metodo.modulos, start=1):
        linhas.append(f"[{ordem}] {modulo.nome}")
        if modulo.perfil:
            linhas.append(f"      Perfil: {modulo.perfil}")

        if modulo.limitacoes:
            linhas.append("      Não alcança:")
            for limitacao in modulo.limitacoes:
                linhas += _quebrar(f"- {limitacao}", "        ")
        else:
            linhas.append("      Não alcança: (nada declarado por este módulo)")

        for alteracao, justificativa in modulo.alteracoes:
            linhas.append("      Pode alterar no aparelho:")
            linhas += _quebrar(f"- {alteracao}", "        ")
            linhas.append("      Justificativa:")
            linhas += _quebrar(f"- {justificativa}", "        ")

        linhas.append("")

    return linhas + _nota() + ["=" * LARGURA]


def _nota() -> list:
    return [
        "-" * LARGURA,
        "ALCANCE DESTE REGISTRO",
        "",
        "  As limitações acima são do MÉTODO, não deste exame em particular:",
        "  descrevem o que os módulos escolhidos não alcançam, seja qual for o",
        "  aparelho. Elas existem para que a ausência de um dado no material",
        "  coletado não seja lida como ausência do dado no aparelho.",
        "",
        "  As alterações listadas são as que a execução PODE provocar. A que",
        "  efetivamente ocorreu está no registro_procedimento.txt, anotada no",
        "  momento em que ocorreu.",
        "-" * LARGURA,
    ]
