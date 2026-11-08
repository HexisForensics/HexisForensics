"""
Contrato comum para módulos de extração forense.

Qualquer tipo de extração (SMS, WhatsApp, contatos, backup lógico,
filesystem, extração física, etc.) implementa `BaseExtractor`, seja para
Android ou iOS. Isso permite que a GUI trate todos os módulos de forma
genérica (listar, marcar em checkbox, executar em fila, mostrar
progresso) sem precisar conhecer os detalhes de cada plataforma.

As classes concretas de plataforma (`core.android.extractors.base.AndroidExtractor`
e `core.ios.extractors.base.IOSExtractor`) é que sabem *como* falar com o
dispositivo; este módulo só define *o que* é esperado de um extrator.

Extratores concretos se registram automaticamente via o decorator
`@registrar_extrator` (ver `core.registry`), então a lista exibida na GUI
é sempre descoberta dinamicamente — nenhuma lista precisa ser mantida à mão.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

from .procedimento import RegistroProcedimento

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int], None]  # 0-100


class Plataforma(Enum):
    """Plataformas suportadas (ou planejadas) pela suíte."""

    ANDROID = "android"
    IOS = "ios"
    COMPUTADOR = "computador"


class Perfil(Enum):
    """
    Competência técnica mínima para operar um módulo (ISO/IEC 27037).

    São papéis de competência, não cargos de corporação: o mesmo servidor
    pode ser DEFR num procedimento e DES em outro, conforme o que a coleta
    exige dele.

    - **DEFR** (*Digital Evidence First Responder*) — autorizado a
      identificar, coletar e preservar. É o perfil de quem executa uma
      aquisição lógica de rotina seguindo procedimento estabelecido.
    - **DES** (*Digital Evidence Specialist*) — soma ao DEFR a competência
      para decidir diante do que foge do procedimento: imagem física,
      aparelho com privilégio elevado, material que exige interpretação
      técnica do que foi (e do que não foi) obtido.

    Declarar o perfil não bloqueia ninguém — a ferramenta não sabe quem
    está operando e não vai fingir que sabe. Serve para a interface
    advertir e para o laudo registrar o que a coleta exigia.
    """

    DEFR = "DEFR — primeiro respondedor"
    DES = "DES — especialista"


class StatusExtracao(Enum):
    NAO_INICIADA = auto()
    EM_EXECUCAO = auto()
    CONCLUIDA = auto()
    FALHOU = auto()
    NAO_SUPORTADA = auto()


@dataclass
class ResultadoExtracao:
    """Resultado padronizado retornado por qualquer extrator ao final da execução."""

    sucesso: bool
    mensagem: str = ""
    caminho_saida: Optional[Path] = None
    detalhes: dict = field(default_factory=dict)


class BaseExtractor(ABC):
    """
    Classe abstrata que define o contrato de qualquer módulo de extração,
    independente de plataforma.

    Atributos de classe (devem ser sobrescritos pelas subclasses concretas):
        id: identificador estável e único do módulo (usado internamente).
        nome_exibicao: nome amigável mostrado na GUI.
        descricao: texto explicativo (tooltip na GUI).
        plataforma: `Plataforma.ANDROID` ou `Plataforma.IOS`.
        requer_privilegio_root: sinaliza módulos que só funcionam com um
            privilégio elevado (root/jailbreak no Android/iOS,
            Administrador no Windows), para a GUI poder alertar o usuário.
        rotulo_privilegio: texto mostrado ao lado do nome do módulo na GUI
            quando `requer_privilegio_root` é True (ex.: "requer root",
            "requer administrador") — cada plataforma usa o termo correto
            para o seu tipo de privilégio elevado.
        ordem: controla a posição de exibição na GUI (menor = mais acima).
            Extratores com a mesma ordem são desempatados por nome.
        limitacoes_conhecidas: o que o módulo comprovadamente não obtém.
        alteracoes_no_dispositivo: o que a execução muda no alvo, e por quê.
        perfil_minimo: competência técnica exigida (`Perfil.DEFR`/`Perfil.DES`).
    """

    id: str = "base"
    nome_exibicao: str = "Extrator Base"
    descricao: str = ""
    # Raizes que o modulo copia do dispositivo. Serve para detectar quando
    # dois modulos selecionados juntos adquirem o mesmo material -- o que
    # dobra tempo e espaco e cria duas copias da mesma evidencia no caso.
    caminhos_de_origem: tuple = ()
    plataforma: Optional[Plataforma] = None
    requer_privilegio_root: bool = False
    rotulo_privilegio: str = "requer root"
    ordem: int = 100
    # Módulo que só roda quando o examinador o escolhe UM A UM: começa
    # desmarcado e o "Marcar todos" não o alcança. É para o que altera o
    # dispositivo de modo que precisa ser decidido, e não herdado de um
    # clique que queria dizer "o de sempre".
    selecao_expressa: bool = False

    # ------------------------------------------------------------------
    # Metadados de método — o que o módulo sabe sobre os próprios limites.
    #
    # Existem porque esse conhecimento já existia, mas escrito em docstring:
    # o extrator de WhatsApp explica em prosa, no topo do arquivo, que sem
    # root não alcança o msgstore.db. Correto, e invisível para todos que
    # importam — a interface não mostra, o laudo não menciona, e o
    # examinador recebe mídias e backups sem que nada diga que as mensagens
    # em si não vieram.
    #
    # Declarados aqui, um mesmo dado alimenta três consumidores sem
    # redigitação: o aviso na tela ANTES de rodar, a seção de metodologia e
    # limitações do laudo, e o material de treinamento gerado do próprio
    # código — que por isso não envelhece em relação à ferramenta.
    #
    # `limitacoes_conhecidas` é o mais importante dos três. Laudo silencioso
    # sobre o que o método não alcança convida a ler ausência de dado como
    # ausência de fato, que é afirmar além do verificado por omissão.
    # ------------------------------------------------------------------

    # O que este módulo comprovadamente NÃO obtém, e por quê. Uma frase por
    # limitação, escrita para o leitor do laudo — não para o programador.
    limitacoes_conhecidas: tuple = ()

    # O que a execução altera no dispositivo alvo, com a justificativa.
    # Pares `(alteração, justificativa)`. Toda alteração é registrada no
    # `registro_procedimento.txt` durante a execução; declará-la aqui
    # permite advertir ANTES, quando o examinador ainda pode decidir.
    alteracoes_no_dispositivo: tuple = ()

    # Competência técnica que a operação deste módulo exige.
    perfil_minimo: Perfil = Perfil.DEFR

    def __init__(
        self,
        log_callback: Optional[LogCallback] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self._log_callback: LogCallback = log_callback or (lambda mensagem: None)
        self._progress_callback: ProgressCallback = progress_callback or (lambda percentual: None)
        self._cancelado = False

    # ------------------------------------------------------------------
    # Utilitários usados pelas subclasses durante a execução
    # ------------------------------------------------------------------
    def log(self, mensagem: str) -> None:
        self._log_callback(mensagem)

    def progresso(self, percentual: int) -> None:
        self._progress_callback(max(0, min(100, percentual)))

    def registrar_decisao(self, pasta_caso: Path, decisao: str, motivo: str) -> None:
        """
        Anota, no registro do procedimento do caso, uma escolha metodológica
        e sua razão.

        Atende ao requisito de **justificabilidade** da ISO/IEC 27037. Sem
        isso, "extração física não realizada" chega ao exame como uma falha
        no log; com isso, chega como o que de fato é — uma decisão técnica
        fundamentada, que o examinador pode sustentar em contraditório.
        """
        RegistroProcedimento(pasta_caso).registrar_decisao(
            f"[{self.nome_exibicao}] {decisao}", motivo
        )

    def registrar_alteracao(self, pasta_caso: Path, alteracao: str, justificativa: str) -> None:
        """
        Anota uma alteração provocada no dispositivo examinado.

        Alteração documentada é metodologia; alteração silenciosa,
        descoberta depois pela defesa, é vulnerabilidade.
        """
        RegistroProcedimento(pasta_caso).registrar_alteracao(
            f"[{self.nome_exibicao}] {alteracao}", justificativa
        )

    def cancelar(self) -> None:
        """Sinaliza pedido de cancelamento cooperativo; a subclasse deve
        checar `self.cancelado` entre etapas longas e interromper."""
        self._cancelado = True

    @property
    def cancelado(self) -> bool:
        return self._cancelado

    # ------------------------------------------------------------------
    # Contrato que cada extrator concreto precisa implementar
    # ------------------------------------------------------------------
    @abstractmethod
    def disponivel(self) -> tuple[bool, str]:
        """
        Verifica se este extrator pode ser executado agora (ferramenta
        presente, dispositivo conectado e autorizado, etc.).

        Retorna (True, "") se disponível, ou (False, motivo) caso contrário.
        """
        raise NotImplementedError

    @abstractmethod
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        """Executa a extração, gravando os artefatos dentro de `pasta_caso`."""
        raise NotImplementedError
