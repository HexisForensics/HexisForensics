"""
Registro do procedimento pericial — o diário de bordo do caso.

Enquanto `extracao.log` responde "o que a ferramenta fez" e
`erros/erros.log` responde "o que não funcionou", este arquivo responde às
três perguntas que a ISO/IEC 27037 exige que o examinador saiba responder
e que nenhum log técnico cobre:

    1. Em que condições o exame foi feito?  (ambiente, versões, relógios)
    2. Que decisões metodológicas foram tomadas, e por quê?
    3. O que foi alterado no dispositivo examinado, e por que era inevitável?

A terceira é a mais sensível. Ativar a Depuração USB, autorizar a chave RSA
da estação, tocar em "Fazer backup dos meus dados" — tudo isso **modifica o
aparelho periciado**. A norma admite a alteração quando ela é inevitável
para a aquisição, mas exige que seja registrada e justificada. Alteração
documentada é metodologia; alteração silenciosa, descoberta depois pela
defesa, é vulnerabilidade.

O arquivo é append-only por construção: cada entrada é acrescentada com seu
próprio carimbo de tempo, e nada é reescrito.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .idioma import IDIOMA_PADRAO, traduzir
from .versao import descrever_ambiente

NOME_ARQUIVO = "registro_procedimento.txt"

LARGURA = 78

# Tipo de entrada do diário -> chave de tradução do título. O título é
# ESCRITO no idioma do caso e PROCURADO por esse mesmo idioma (ver
# `titulo_evento`, usado por `core.protocolos` e `services.dossie_service`).
_EVENTOS = {
    "fundamento": "sl_evt_fundamento",
    "operador": "sl_evt_operador",
    "ambiente": "sl_evt_ambiente",
    "relogio": "sl_evt_relogio",
    "decisao": "sl_evt_decisao",
    "alteracao": "sl_evt_alteracao",
    "observacao": "sl_evt_observacao",
    "encerramento": "sl_evt_encerramento",
}


def titulo_evento(tipo: str, idioma: str = IDIOMA_PADRAO) -> str:
    """O título da entrada do diário no idioma dado. Chave de busca no selado."""
    return traduzir(_EVENTOS[tipo], idioma)


def _agora_iso() -> str:
    """Horário local com fuso explícito — carimbo sem fuso não tem valor probatório."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RegistroProcedimento:
    """
    Escreve `registro_procedimento.txt` na raiz da pasta do caso.

    Todos os métodos são tolerantes a falha de escrita: um problema ao
    gravar o diário nunca pode interromper uma aquisição em andamento —
    perder a evidência seria pior do que perder a anotação. A falha é
    devolvida como `False` para quem quiser reportá-la ao examinador.
    """

    def __init__(self, pasta_caso: Path):
        self.pasta_caso = Path(pasta_caso)
        self.caminho = self.pasta_caso / NOME_ARQUIVO
        # Idioma CARIMBADO no caso (ou o ativo, que será carimbado): o diário
        # é escrito nele, e lido de volta por ele. Resolvido aqui, uma vez, na
        # abertura — não pode mudar no meio de uma aquisição.
        from core.case import idioma_para_selar
        self.idioma = idioma_para_selar(self.pasta_caso)

    def _t(self, chave: str, **campos) -> str:
        return traduzir(chave, self.idioma, **campos)

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def _anexar(self, tipo: str, linhas: list) -> bool:
        bloco = [f"[{_agora_iso()}] {titulo_evento(tipo, self.idioma)}"]
        bloco += [f"    {linha}" for linha in linhas]
        bloco.append("")
        try:
            self.pasta_caso.mkdir(parents=True, exist_ok=True)
            with open(self.caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write("\n".join(bloco) + "\n")
            return True
        except OSError:
            return False

    def abrir(self, identificador_caso: str, plataforma: str, id_dispositivo: str) -> bool:
        """Cabeçalho do registro, gravado na abertura do caso."""
        cabecalho = [
            "=" * LARGURA,
            self._t("sl_reg_titulo"),
            "=" * LARGURA,
            self._t("sl_reg_l_caso", valor=identificador_caso),
            self._t("sl_reg_l_plataforma", valor=plataforma),
            self._t("sl_reg_l_dispositivo", valor=id_dispositivo),
            self._t("sl_reg_l_abertura", valor=_agora_iso()),
            "=" * LARGURA,
            "",
        ]
        try:
            self.pasta_caso.mkdir(parents=True, exist_ok=True)
            with open(self.caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write("\n".join(cabecalho) + "\n")
            return True
        except OSError:
            return False

    def registrar_fundamento(self, resumo: str, detalhe: str = "") -> bool:
        """
        Primeira entrada substantiva do diário: por que o acesso é lícito.

        Vem antes do ambiente e do relógio de propósito. O diário do caso
        abre declarando o fundamento — é a primeira coisa que se questiona
        sobre uma extração, e a última que deveria faltar no registro.
        """
        linhas = [self._t("sl_reg_fundamento", valor=resumo)]
        if detalhe:
            linhas.append(detalhe)
        return self._anexar("fundamento", linhas)

    def registrar_operador(self, linhas_do_operador: list, conta_da_estacao: str) -> bool:
        """
        Quem executou: o que o operador declara de si e, em linha própria, a
        conta do sistema que a ferramenta apurou sozinha. As duas não se
        misturam — uma é declaração, a outra é leitura.
        """
        return self._anexar(
            "operador",
            list(linhas_do_operador)
            + [self._t("sl_reg_conta",
                       valor=conta_da_estacao or self._t("sl_reg_nao_apurada"))],
        )

    def registrar_ambiente(self, versao_adb: Optional[str] = None) -> bool:
        """Ferramenta, Python, sistema operacional, estação e versão do ADB.

        Rótulos e o valor de 'origem' selam no idioma do caso; os demais
        valores (versão, sistema, nó da estação) são dado e saem verbatim.
        """
        ambiente = descrever_ambiente()
        if versao_adb:
            ambiente["adb"] = versao_adb
        rotulos = {
            "ferramenta": "amb_ferramenta", "origem": "amb_origem", "python": "amb_python",
            "sistema": "amb_sistema", "arquitetura": "amb_arquitetura",
            "estacao": "amb_estacao", "adb": "amb_adb",
        }
        origem_valor = {"código-fonte": "amb_origem_fonte", "instalador": "amb_origem_instalador"}
        linhas = []
        for chave, valor in ambiente.items():
            rotulo = self._t(rotulos[chave]) if chave in rotulos else chave
            if chave == "origem" and valor in origem_valor:
                valor = self._t(origem_valor[valor])
            linhas.append(f"{rotulo}: {valor}")
        return self._anexar("ambiente", linhas)

    def registrar_relogio(self, resumo_relogio: str) -> bool:
        """
        Relógio do dispositivo confrontado com o da estação.

        Sem o desvio medido no momento da aquisição, todo carimbo de tempo
        dos artefatos extraídos fica sem âncora.
        """
        return self._anexar("relogio", [resumo_relogio])

    def registrar_decisao(self, decisao: str, justificativa: str) -> bool:
        """
        Decisão metodológica e sua fundamentação.

        Atende ao requisito de **justificabilidade** da ISO/IEC 27037: o
        examinador precisa poder explicar por que escolheu este método e
        não outro. Ex.: "extração física não realizada: aparelho sem root;
        adotada extração lógica via ADB".
        """
        return self._anexar("decisao", [self._t("sl_reg_decisao", valor=decisao),
                                        self._t("sl_reg_motivo", valor=justificativa)])

    def registrar_alteracao(self, alteracao: str, justificativa: str) -> bool:
        """
        Alteração provocada no dispositivo examinado, com a razão de ser
        inevitável. Ver a nota no topo deste módulo.
        """
        return self._anexar(
            "alteracao",
            [self._t("sl_reg_alteracao", valor=alteracao),
             self._t("sl_reg_justificativa", valor=justificativa)],
        )

    def registrar_observacao(self, texto: str) -> bool:
        """Anotação livre do procedimento."""
        return self._anexar("observacao", [texto])

    def encerrar(self, resumo: str) -> bool:
        """Fecha o registro com o desfecho consolidado da aquisição."""
        return self._anexar("encerramento", [resumo])
