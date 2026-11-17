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

from .idioma import traduzir
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

    # Idioma em que a narração deste módulo é escrita (ver __init__). Atributo
    # de classe para que exista mesmo quando um teste constrói o extrator por
    # um caminho que não passa pelo __init__; None cai para o idioma ativo.
    _idi_selo: Optional[str] = None

    # ------------------------------------------------------------------
    # Metadados no idioma pedido (i18n — Fase 4).
    #
    # O nome, a descrição, as limitações e as alterações são declarados em
    # português nos atributos acima. Eles continuam sendo a FONTE e o
    # fallback: quando o catálogo ainda não traz a chave do módulo, sai o
    # texto do código, e nada quebra — a migração é módulo a módulo.
    #
    # A chave segue o `id` estável do módulo (`mod_<id>_nome`, `_desc`,
    # `_lim_<i>`, `_alt_<i>_o`/`_alt_<i>_j`), nunca o nome de exibição: o
    # texto muda de idioma, o `id` não. Quem sela o método (ver
    # `core.metodo.descrever`) resolve no idioma CARIMBADO no caso; a tela
    # resolve no idioma ATIVO.
    # ------------------------------------------------------------------
    @classmethod
    def _texto_do_modulo(cls, sufixo: str, padrao: str, idioma=None) -> str:
        """Texto da chave `mod_<id>_<sufixo>`, ou o `padrao` (o literal em PT)."""
        chave = f"mod_{cls.id}_{sufixo}"
        texto = traduzir(chave, idioma)
        return padrao if texto == chave else texto

    @classmethod
    def nome_no_idioma(cls, idioma=None) -> str:
        return cls._texto_do_modulo("nome", cls.nome_exibicao, idioma)

    @classmethod
    def descricao_no_idioma(cls, idioma=None) -> str:
        return cls._texto_do_modulo("desc", cls.descricao, idioma)

    @classmethod
    def limitacoes_no_idioma(cls, idioma=None) -> list:
        return [
            cls._texto_do_modulo(f"lim_{i}", bruta, idioma)
            for i, bruta in enumerate(cls.limitacoes_conhecidas)
        ]

    # O rótulo de privilégio ("requer root/administrador/jailbreak") é um dos
    # três literais fixos da plataforma, não texto por módulo: mapeia-se o
    # literal para a chave do catálogo. Literal fora dos três (um módulo que
    # invente o seu) sai como está, sem quebrar.
    _CHAVE_DO_PRIVILEGIO = {
        "requer root": "xp_requer_root",
        "requer administrador": "xp_requer_admin",
        "requer jailbreak": "xp_requer_jailbreak",
    }

    @classmethod
    def rotulo_privilegio_no_idioma(cls, idioma=None) -> str:
        bruto = cls.rotulo_privilegio
        chave = cls._CHAVE_DO_PRIVILEGIO.get(bruto)
        if chave is None:
            return bruto
        texto = traduzir(chave, idioma)
        return bruto if texto == chave else texto

    @classmethod
    def alteracoes_no_idioma(cls, idioma=None) -> list:
        return [
            (
                cls._texto_do_modulo(f"alt_{i}_o", alteracao, idioma),
                cls._texto_do_modulo(f"alt_{i}_j", justificativa, idioma),
            )
            for i, (alteracao, justificativa) in enumerate(cls.alteracoes_no_dispositivo)
        ]

    def __init__(
        self,
        log_callback: Optional[LogCallback] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self._log_callback: LogCallback = log_callback or (lambda mensagem: None)
        self._progress_callback: ProgressCallback = progress_callback or (lambda percentual: None)
        self._cancelado = False
        # Idioma em que a narração deste módulo é escrita. É SELADO (vai para o
        # extracao.log e a mensagem do resultado entra no desfecho), por isso
        # segue o carimbo do caso. Definido no início de `executar` por
        # `definir_idioma_do_selo`; None até lá cai para o idioma ativo.
        self._idi_selo: Optional[str] = None

    def definir_idioma_do_selo(self, pasta_caso) -> None:
        """Lê o idioma carimbado no caso e o fixa para a narração deste módulo."""
        from core.case import idioma_para_selar
        self._idi_selo = idioma_para_selar(pasta_caso)

    def _t(self, chave: str, **campos) -> str:
        """Texto da `chave` no idioma do selo deste módulo (ou no ativo)."""
        return traduzir(chave, self._idi_selo, **campos)

    def log_t(self, chave: str, **campos) -> None:
        """Loga uma frase do catálogo no idioma do selo. A saída crua do
        aparelho NÃO passa por aqui — vai por `self.log`, intocada."""
        self.log(self._t(chave, **campos))

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
