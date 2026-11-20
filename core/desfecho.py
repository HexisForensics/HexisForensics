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

from core.idioma import idioma_ativo, traduzir

PASTA_DESFECHO = "desfecho"
NOME_DESFECHO = "desfecho_da_coleta.txt"
NOME_DESFECHO_DADOS = "desfecho_da_coleta.json"

LARGURA = 70

SUCESSO = "sucesso"
RESSALVA = "ressalva"
FALHA = "falha"

# A situação é a CHAVE estável (sucesso/ressalva/falha); o rótulo é por idioma.
ROTULOS = {
    SUCESSO: "Concluído",
    RESSALVA: "Concluído com ressalva",
    FALHA: "Não obteve dado",
}
_CHAVE_ROTULO = {
    SUCESSO: "df_rotulo_concluido",
    RESSALVA: "df_rotulo_ressalva",
    FALHA: "df_rotulo_falha",
}

# Motivos de ressalva: a CHAVE é a sentinela estável (services.extraction_service
# .CHAVES_RESSALVA) usada pela lógica; o rótulo que o leitor vê é por idioma.
# Chave sem rótulo cai no próprio texto, para nunca ocultar uma ressalva nova.
_CHAVE_ROTULO_RESSALVA = {
    "acesso_negado": "res_acesso_negado",
    "arquivos_pulados_nuvem": "res_arquivos_pulados_nuvem",
    "campos_nao_apurados": "res_campos_nao_apurados",
    "copia_incompleta": "res_copia_incompleta",
    "itens_fora_do_alcance": "res_itens_fora_do_alcance",
    "restauracao_pendente": "res_restauracao_pendente",
}


def rotulo_de_ressalva(chave: str, idioma=None) -> str:
    """O motivo de ressalva legível no idioma do documento; a chave crua
    quando não houver rótulo (sentinela nova nunca desaparece do documento)."""
    chave_catalogo = _CHAVE_ROTULO_RESSALVA.get(chave)
    return traduzir(chave_catalogo, idioma) if chave_catalogo else chave


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
        """Rótulo da situação no idioma ATIVO (para a tela/laudo ao vivo)."""
        return self.rotulo_no_idioma(idioma_ativo())

    def rotulo_no_idioma(self, idioma: str) -> str:
        chave = _CHAVE_ROTULO.get(self.situacao)
        if chave is None:
            return self.situacao
        texto = traduzir(chave, idioma)
        return ROTULOS.get(self.situacao, self.situacao) if texto == chave else texto


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
        """Resumo no idioma ATIVO. O selo usa `resumo_no_idioma` (carimbo)."""
        return self.resumo_no_idioma(idioma_ativo())

    def resumo_no_idioma(self, idioma: str) -> str:
        if self.vazio:
            return traduzir("df_resumo_vazio", idioma)
        cabeca = traduzir("df_resumo_modulos", idioma, total=self.total)
        partes = [traduzir("df_resumo_concluidos", idioma, n=self.concluidos)]
        if self.com_ressalva:
            partes.append(traduzir("df_resumo_ressalva", idioma, n=self.com_ressalva))
        if self.falharam:
            partes.append(traduzir("df_resumo_falha", idioma, n=self.falharam))
        texto = ": ".join([cabeca, ", ".join(partes)])
        if self.cancelada:
            texto += traduzir("df_resumo_cancelada", idioma)
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
def gravar_desfecho(pasta_aquisicao: Path, desfecho: DesfechoDaColeta,
                    idioma: str = None) -> Path:
    """
    Grava o desfecho na aquisição, antes do selo, como o método.

    O `.txt` é selado: sua moldura, o resumo e o rótulo da situação saem no
    idioma CARIMBADO no caso (passado por `idioma`). A mensagem de cada
    módulo e as chaves de ressalva são conteúdo declarado pelo módulo (dado)
    e seguem como estão.
    """
    pasta = Path(pasta_aquisicao) / PASTA_DESFECHO
    pasta.mkdir(parents=True, exist_ok=True)

    caminho = pasta / NOME_DESFECHO
    caminho.write_text("\n".join(_linhas(desfecho, idioma)) + "\n", encoding="utf-8")
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


def _linhas(desfecho: DesfechoDaColeta, idioma: str = None) -> list:
    def t(chave, **campos):
        return traduzir(chave, idioma, **campos)

    linhas = [
        "=" * LARGURA,
        t("df_txt_titulo").center(LARGURA),
        "=" * LARGURA,
        "",
        desfecho.resumo_no_idioma(idioma or idioma_ativo()),
        "",
    ]

    for ordem, modulo in enumerate(desfecho.modulos, start=1):
        linhas.append(f"[{ordem}] {modulo.nome}")
        linhas.append(t("df_txt_situacao", valor=modulo.rotulo_no_idioma(idioma or idioma_ativo())))
        if modulo.mensagem:
            linhas.append(f"      {modulo.mensagem}")
        if modulo.ressalvas:
            linhas.append(t("df_txt_ressalvas", valor=', '.join(modulo.ressalvas)))
        linhas.append("")

    linhas += ["-" * LARGURA, t("df_txt_como_ler"), ""]
    linhas += t("df_txt_nota_ressalva").split("\n")
    linhas += [""]
    linhas += t("df_txt_nota_falha").split("\n")
    linhas += ["-" * LARGURA, "=" * LARGURA]
    return linhas
