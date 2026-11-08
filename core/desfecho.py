"""
Desfecho da coleta: o que cada módulo obteve, ou deixou de obter.

O `registro_procedimento.txt` já encerra com o total consolidado, em prosa.
Isso serve a quem lê o caso, mas não a quem monta o laudo: extrair números
de um texto formatado é frágil, e frágil aqui significa laudo afirmando
coisa errada.

Este módulo grava o mesmo desfecho em forma estruturada, dentro da
aquisição e antes do selo, seguindo o mesmo arranjo do método declarado e
da autorização. O laudo lê daqui.

**Três desfechos, não dois.** Sucesso pleno, sucesso COM RESSALVA e falha
são estados distintos, e reduzi-los a "deu certo / não deu" é o defeito que
esta suíte existe para evitar: módulo que copiou parte do material e
declarou o que não alcançou não é equivalente a módulo que copiou tudo. O
laudo precisa dos três para não afirmar completude que não houve.

Módulo previsto e **não executado** também entra, com o motivo. Ausência de
coleta não é ausência de dado no aparelho, e o exame precisa saber a
diferença sem cruzar dois arquivos de log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PASTA_DESFECHO = "desfecho"
NOME_DESFECHO = "desfecho_da_coleta.txt"
NOME_DESFECHO_DADOS = "desfecho_da_coleta.json"

LARGURA = 70

SUCESSO = "sucesso"
RESSALVA = "ressalva"
FALHA = "falha"

ROTULOS = {
    SUCESSO: "Concluído",
    RESSALVA: "Concluído com ressalva",
    FALHA: "Não obteve dado",
}


@dataclass
class ModuloExecutado:
    """O que um módulo produziu nesta coleta."""

    identificador: str
    nome: str
    situacao: str = FALHA
    mensagem: str = ""
    ressalvas: list = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return ROTULOS.get(self.situacao, self.situacao)


@dataclass
class DesfechoDaColeta:
    """Desfecho consolidado, para o laudo não precisar interpretar prosa."""

    modulos: list = field(default_factory=list)
    cancelada: bool = False

    @property
    def vazio(self) -> bool:
        return not self.modulos

    def _contar(self, situacao: str) -> int:
        return sum(1 for m in self.modulos if m.situacao == situacao)

    @property
    def total(self) -> int:
        return len(self.modulos)

    @property
    def concluidos(self) -> int:
        return self._contar(SUCESSO)

    @property
    def com_ressalva(self) -> int:
        return self._contar(RESSALVA)

    @property
    def falharam(self) -> int:
        return self._contar(FALHA)

    @property
    def integral(self) -> bool:
        """
        `True` só quando todos os módulos concluíram sem ressalva e nada foi
        cancelado. É a única situação em que o laudo pode falar de coleta
        completa — qualquer outra exige dizer o que faltou.
        """
        return (
            not self.vazio
            and not self.cancelada
            and self.com_ressalva == 0
            and self.falharam == 0
        )

    @property
    def resumo(self) -> str:
        if self.vazio:
            return "Nenhum módulo foi executado nesta aquisição."
        partes = [f"{self.total} módulo(s) executado(s)"]
        partes.append(f"{self.concluidos} concluído(s)")
        if self.com_ressalva:
            partes.append(f"{self.com_ressalva} com ressalva")
        if self.falharam:
            partes.append(f"{self.falharam} sem obter dado")
        texto = ": ".join([partes[0], ", ".join(partes[1:])])
        if self.cancelada:
            texto += ". A execução foi INTERROMPIDA antes de percorrer todos os módulos."
        return texto + "."


def descrever_execucao(registros, cancelada: bool = False) -> DesfechoDaColeta:
    """
    Monta o desfecho a partir do que a execução observou.

    `registros` é uma sequência de `(id, nome, sucesso, mensagem, detalhes)`
    — a mesma tupla que o serviço já emite por módulo, para não haver duas
    fontes do mesmo fato.
    """
    modulos = []
    for identificador, nome, sucesso, mensagem, detalhes in registros:
        detalhes = detalhes or {}
        ressalvas = [chave for chave, valor in detalhes.items() if _e_ressalva(chave, valor)]
        if not sucesso:
            situacao = FALHA
        elif ressalvas:
            situacao = RESSALVA
        else:
            situacao = SUCESSO
        modulos.append(
            ModuloExecutado(
                identificador=identificador,
                nome=nome,
                situacao=situacao,
                mensagem=(mensagem or "").strip(),
                ressalvas=ressalvas,
            )
        )
    return DesfechoDaColeta(modulos=modulos, cancelada=cancelada)


def _e_ressalva(chave: str, valor) -> bool:
    """
    Quais chaves de `detalhes` indicam ressalva.

    Importada de `services.extraction_service` em tempo de chamada para não
    duplicar a lista: uma segunda cópia divergiria na primeira vez que a
    original ganhasse uma chave nova.
    """
    from services.extraction_service import CHAVES_RESSALVA

    return chave in CHAVES_RESSALVA and bool(valor)


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------
def gravar_desfecho(pasta_aquisicao: Path, desfecho: DesfechoDaColeta) -> Path:
    """Grava o desfecho na aquisição, antes do selo, como o método."""
    pasta = Path(pasta_aquisicao) / PASTA_DESFECHO
    pasta.mkdir(parents=True, exist_ok=True)

    caminho = pasta / NOME_DESFECHO
    caminho.write_text("\n".join(_linhas(desfecho)) + "\n", encoding="utf-8")
    (pasta / NOME_DESFECHO_DADOS).write_text(
        json.dumps(_para_dicionario(desfecho), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return caminho


def ler_desfecho(pasta_aquisicao: Path) -> DesfechoDaColeta:
    """Desfecho desta aquisição — vazio se não houver registro."""
    caminho = Path(pasta_aquisicao) / PASTA_DESFECHO / NOME_DESFECHO_DADOS
    if not caminho.is_file():
        return DesfechoDaColeta()

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DesfechoDaColeta()

    modulos = [
        ModuloExecutado(
            identificador=bruto.get("id", ""),
            nome=bruto.get("nome", ""),
            situacao=bruto.get("situacao", FALHA),
            mensagem=bruto.get("mensagem", ""),
            ressalvas=list(bruto.get("ressalvas", [])),
        )
        for bruto in dados.get("modulos", [])
    ]
    return DesfechoDaColeta(modulos=modulos, cancelada=bool(dados.get("cancelada")))


def _para_dicionario(desfecho: DesfechoDaColeta) -> dict:
    return {
        "cancelada": desfecho.cancelada,
        "modulos": [
            {
                "id": m.identificador,
                "nome": m.nome,
                "situacao": m.situacao,
                "mensagem": m.mensagem,
                "ressalvas": list(m.ressalvas),
            }
            for m in desfecho.modulos
        ],
    }


def _linhas(desfecho: DesfechoDaColeta) -> list:
    linhas = [
        "=" * LARGURA,
        "DESFECHO DA COLETA".center(LARGURA),
        "=" * LARGURA,
        "",
        desfecho.resumo,
        "",
    ]

    for ordem, modulo in enumerate(desfecho.modulos, start=1):
        linhas.append(f"[{ordem}] {modulo.nome}")
        linhas.append(f"      Situação: {modulo.rotulo}")
        if modulo.mensagem:
            linhas.append(f"      {modulo.mensagem}")
        if modulo.ressalvas:
            linhas.append(f"      Ressalvas: {', '.join(modulo.ressalvas)}")
        linhas.append("")

    linhas += [
        "-" * LARGURA,
        "COMO LER ESTE REGISTRO",
        "",
        "  'Concluído com ressalva' NÃO é equivalente a 'Concluído'. Significa",
        "  que o módulo obteve parte do material e declarou o que não alcançou",
        "  — o detalhe está na mensagem e em erros/erros.log.",
        "",
        "  'Não obteve dado' significa que aquele material não foi adquirido.",
        "  Não significa que ele não exista no aparelho.",
        "-" * LARGURA,
        "=" * LARGURA,
    ]
    return linhas
