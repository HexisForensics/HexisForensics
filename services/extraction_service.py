"""
Serviço de extração.

Duas responsabilidades:
    - `listar_extratores(nome_plataforma)`: catálogo de extratores
      disponíveis para "Android" ou "iOS", escondendo da UI que eles vêm
      de `core.android`/`core.ios`.
    - `ExtractionService`: executa uma lista de extratores em sequência,
      em uma `QThread`, para não bloquear a interface. É a única classe
      deste arquivo que toca em Qt (`QThread`/`Signal`) — mesmo assim não
      conhece nenhum widget, só emite sinais para quem quiser ouvir.

Além do log geral (`extracao.log`), todo módulo que falhar ou terminar com
alguma ressalva (ex.: `detalhes["acesso_negado"]`) tem uma entrada gravada
em `erros/erros.log`, dentro da pasta do caso — ver `core.logger`. Os
sinais `extrator_iniciado`/`extrator_concluido` carregam o `id` do
extrator (além do nome de exibição) e, na conclusão, o dicionário
`detalhes` do `ResultadoExtracao`, para que a UI possa mostrar um status
por módulo (sucesso / parcial / falha) — ver `ui.widgets.extraction_panel`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Type

from PySide6.QtCore import QThread, Signal

import core.android as _android
import core.computador as _computador
import core.ios as _ios
from core.base_extractor import BaseExtractor
from core.desfecho import SUCESSO, descrever_execucao, gravar_desfecho
from core.hashing import gerar_manifesto
from core.logger import configurar_logger_arquivo, configurar_logger_erros
from core.metodo import descrever, gravar_metodo
from core.procedimento import RegistroProcedimento
from core.versao import identificacao_ferramenta

ANDROID = "Android"
IOS = "iOS"
COMPUTADOR = "Computador"

_CATALOGOS = {
    ANDROID: _android.listar_extratores,
    IOS: _ios.listar_extratores,
    COMPUTADOR: _computador.listar_extratores,
}

# Chaves de `ResultadoExtracao.detalhes` que, mesmo com `sucesso=True`,
# indicam uma ressalva real que o examinador precisa ver — não escondida
# atrás de um "sucesso" genérico. Começou só com `acesso_negado` (Android:
# provider negou acesso, mas a tentativa foi preservada como evidência);
# `arquivos_pulados_nuvem` (Computador: arquivos do OneDrive/Google Drive
# que não estavam fisicamente no disco) segue a mesma convenção. Qualquer
# extrator futuro pode adotá-la só colocando uma chave truthy em
# `detalhes` e listando-a aqui.
CHAVES_RESSALVA = (
    "acesso_negado",
    "arquivos_pulados_nuvem",
    "campos_nao_apurados",
    "copia_incompleta",
    "itens_fora_do_alcance",
    "restauracao_pendente",
)


def identificacao_da_ferramenta() -> str:
    """Nome e versão da suíte, para a interface exibir sem importar `core`."""
    return identificacao_ferramenta()


def listar_extratores(nome_plataforma: str) -> List[Type[BaseExtractor]]:
    """Retorna as classes de extratores disponíveis para a plataforma informada."""
    funcao_catalogo = _CATALOGOS.get(nome_plataforma)
    return funcao_catalogo() if funcao_catalogo else []


def detectar_sobreposicao(extratores: List[BaseExtractor]) -> List[str]:
    """
    Aponta pares de módulos que adquirem o mesmo material do dispositivo.

    O caso concreto: o Backup Lógico copia `/sdcard/DCIM`, `/sdcard/Download`
    e outras; o Dump do Sistema de Arquivos copia `/sdcard` inteiro. Marcados
    juntos, as mesmas fotos são copiadas duas vezes — dobrando tempo, espaço
    e cálculo de hash, e deixando duas cópias da mesma evidência no caso.

    A sobreposição não é impedida: pode ser deliberada. Mas precisa ser
    declarada, para que o examinador decida sabendo, e para que o exame não
    interprete as duas cópias como dois achados independentes.
    """
    avisos = []
    for posicao, extrator in enumerate(extratores):
        for outro in extratores[posicao + 1:]:
            comuns = _caminhos_sobrepostos(extrator, outro)
            if comuns:
                avisos.append(
                    f"'{extrator.nome_exibicao}' e '{outro.nome_exibicao}' adquirem o mesmo "
                    f"material ({', '.join(comuns)}). O conteúdo será copiado duas vezes."
                )
    return avisos


def _caminhos_sobrepostos(primeiro: BaseExtractor, segundo: BaseExtractor) -> List[str]:
    """Caminhos em que um módulo cobre o territorio do outro."""
    comuns = []
    for caminho_a in getattr(primeiro, "caminhos_de_origem", ()):
        for caminho_b in getattr(segundo, "caminhos_de_origem", ()):
            raiz_a, raiz_b = caminho_a.rstrip("/"), caminho_b.rstrip("/")
            if raiz_a == raiz_b:
                comuns.append(raiz_a)
            elif raiz_a.startswith(raiz_b + "/"):
                comuns.append(raiz_a)
            elif raiz_b.startswith(raiz_a + "/"):
                comuns.append(raiz_b)
    return sorted(set(comuns))


def descrever_metodo(extratores) -> List[dict]:
    """
    Alcance declarado de cada módulo, em campos simples para a interface.

    Existe para que `ui/` possa exibir limitações e alterações sem importar
    nada de `core` — mesma razão de `opcoes_tipo_documento` em
    `services.case_service`.
    """
    return [
        {
            "id": modulo.identificador,
            "nome": modulo.nome,
            "perfil": modulo.perfil,
            "limitacoes": list(modulo.limitacoes),
            "alteracoes": [list(par) for par in modulo.alteracoes],
        }
        for modulo in descrever(extratores).modulos
    ]


def indica_ressalva(detalhes: dict) -> bool:
    """`True` se `detalhes` contém alguma das `CHAVES_RESSALVA` com valor truthy."""
    detalhes = detalhes or {}
    return any(bool(detalhes.get(chave)) for chave in CHAVES_RESSALVA)


class ExtractionService(QThread):
    """Executa uma lista de extratores, em sequência, dentro de uma pasta de caso."""

    log_emitido = Signal(str)
    progresso_emitido = Signal(int)
    extrator_iniciado = Signal(str, str)
    extrator_concluido = Signal(str, str, bool, str, object)
    tudo_concluido = Signal()

    def __init__(
        self,
        extratores: List[BaseExtractor],
        pasta_caso: Path,
        ao_finalizar=None,
        parent=None,
    ):
        super().__init__(parent)
        self.extratores = extratores
        self.pasta_caso = Path(pasta_caso)
        self._cancelar = False
        # Executado depois dos módulos e ANTES de o manifesto selar o caso.
        # Existe porque quem sela precisa ser o último a escrever: uma
        # anotação feita pela interface após o selo torna o caso divergente
        # do próprio manifesto. Deve devolver uma mensagem para o log, ou None.
        self._ao_finalizar = ao_finalizar
        # Desfecho consolidado, montado ao fim de `run` (None até lá).
        self.desfecho = None

    def cancelar(self) -> None:
        self._cancelar = True
        for extrator in self.extratores:
            extrator.cancelar()

    def run(self) -> None:
        logger_arquivo = configurar_logger_arquivo(self.pasta_caso)
        logger_erros = configurar_logger_erros(self.pasta_caso)

        def registrar(mensagem: str) -> None:
            self.log_emitido.emit(mensagem)
            logger_arquivo.info(mensagem)

        def registrar_erro_se_necessario(
            extrator: BaseExtractor, sucesso: bool, mensagem: str, detalhes: dict
        ) -> None:
            """Grava em `erros/erros.log` qualquer módulo que falhou ou teve
            ressalva (ver `CHAVES_RESSALVA`), mesmo quando o resultado
            geral foi `sucesso=True`."""
            parcial = indica_ressalva(detalhes)
            if sucesso and not parcial:
                return
            linhas = [
                f"Módulo: {extrator.nome_exibicao} (id={extrator.id})",
                f"Status: {'FALHOU' if not sucesso else 'SUCESSO COM RESSALVAS'}",
                f"Mensagem: {mensagem}",
            ]
            for chave, valor in (detalhes or {}).items():
                linhas.append(f"  - {chave}: {valor}")
            logger_erros.warning("\n" + "\n".join(linhas) + "\n" + ("-" * 40))

        for aviso in detectar_sobreposicao(self.extratores):
            registrar(f"[ATENÇÃO] {aviso}")
            RegistroProcedimento(self.pasta_caso).registrar_observacao(
                f"Sobreposição de módulos: {aviso}"
            )

        # O alcance declarado dos módulos escolhidos é gravado ANTES da
        # coleta, e não montado depois: a combinação de módulos define o
        # alcance daquele exame, e um laudo emitido meses adiante, com a
        # ferramenta já atualizada, exibiria as limitações da versão nova
        # como se fossem as da coleta antiga.
        try:
            caminho_metodo = gravar_metodo(self.pasta_caso, descrever(self.extratores))
            registrar(f"[*] Método declarado registrado em: {caminho_metodo.name}")
        except OSError as exc:
            registrar(f"[ERRO] Não foi possível registrar o método declarado: {exc}")

        desfechos = {"sucesso": 0, "ressalva": 0, "falha": 0}
        # Registro por modulo, para o laudo nao precisar interpretar prosa.
        # Cada entrada e a MESMA tupla emitida em `extrator_concluido`: uma
        # fonte so para o mesmo fato.
        execucao: list = []

        def contabilizar(sucesso: bool, detalhes: dict) -> None:
            if not sucesso:
                desfechos["falha"] += 1
            elif indica_ressalva(detalhes):
                desfechos["ressalva"] += 1
            else:
                desfechos["sucesso"] += 1

        total = len(self.extratores)
        for indice, extrator in enumerate(self.extratores, 1):
            if self._cancelar:
                registrar(
                    "[*] Execução cancelada pelo usuário antes de concluir todos os módulos."
                )
                break

            extrator._log_callback = registrar
            extrator._progress_callback = self.progresso_emitido.emit
            # A barra é de cada módulo: sem zerar, ficava em 100% (do módulo
            # anterior) enquanto o backup do iPhone esperava o código na tela.
            self.progresso_emitido.emit(0)

            self.extrator_iniciado.emit(extrator.id, extrator.nome_exibicao)
            registrar("")
            registrar("=" * 60)
            registrar(f"[MÓDULO {indice}/{total}] {extrator.nome_exibicao}")
            registrar("=" * 60)

            disponivel, motivo = extrator.disponivel()
            if not disponivel:
                registrar(f"[IGNORADO] {motivo}")
                registrar_erro_se_necessario(extrator, False, motivo, {})
                contabilizar(False, {})
                # Módulo previsto e não executado é fato metodológico: o
                # exame precisa saber que aquele dado não foi buscado, e por
                # quê, sem depender de alguém cruzar dois arquivos de log.
                RegistroProcedimento(self.pasta_caso).registrar_decisao(
                    f"Módulo '{extrator.nome_exibicao}' NÃO foi executado.", motivo
                )
                self._registrar_execucao(execucao, 
                    extrator.id, extrator.nome_exibicao, False, motivo, {}
                )
                continue

            try:
                resultado = extrator.executar(self.pasta_caso)
                registrar_erro_se_necessario(
                    extrator, resultado.sucesso, resultado.mensagem, resultado.detalhes
                )
                contabilizar(resultado.sucesso, resultado.detalhes or {})
                self._registrar_execucao(execucao, 
                    extrator.id,
                    extrator.nome_exibicao,
                    resultado.sucesso,
                    resultado.mensagem,
                    resultado.detalhes or {},
                )
            except Exception as exc:  # pragma: no cover - defesa contra falhas inesperadas de hardware/SO
                registrar(f"[ERRO] Falha inesperada em {extrator.nome_exibicao}: {exc}")
                registrar_erro_se_necessario(extrator, False, str(exc), {})
                contabilizar(False, {})
                self._registrar_execucao(execucao, 
                    extrator.id, extrator.nome_exibicao, False, str(exc), {}
                )

        # Ultima oportunidade de escrever no caso: tudo o que a interface
        # precisa registrar (conferencia do aparelho, por exemplo) passa por
        # aqui, e nao depois que o servico termina.
        if self._ao_finalizar is not None:
            try:
                mensagem_final = self._ao_finalizar()
                if mensagem_final:
                    registrar(f"[*] {mensagem_final}")
            except Exception as exc:  # pragma: no cover - defesa contra falha externa
                registrar(f"[ERRO] Falha na finalização do caso: {exc}")

        # A ORDEM aqui e parte da cadeia de custodia: o manifesto sela o
        # caso e, depois dele, NADA pode ser escrito na pasta -- nem o log,
        # nem o registro do procedimento. Enquanto o manifesto era gerado
        # antes do encerramento, todo caso produzido pela suite falhava na
        # propria conferencia de integridade, acusando 'extracao.log' e
        # 'registro_procedimento.txt' como alterados. Um exame adversarial
        # encontraria isso de imediato.
        # Gravado ANTES do selo, como o metodo declarado: o desfecho pertence
        # a aquisicao e precisa estar coberto pelo manifesto.
        self.desfecho = descrever_execucao(execucao, cancelada=self._cancelar)
        try:
            desfecho = self.desfecho
            caminho_desfecho = gravar_desfecho(self.pasta_caso, desfecho)
            registrar(f"[*] Desfecho da coleta registrado em: {caminho_desfecho.name}")
        except OSError as exc:
            registrar(f"[ERRO] Nao foi possivel registrar o desfecho da coleta: {exc}")

        self._encerrar_registro_procedimento(desfechos, total)
        self._fechar_loggers(logger_arquivo, logger_erros)
        self._gerar_manifesto_final()
        for linha in self.linhas_do_desfecho():
            self.log_emitido.emit(linha)
        self.tudo_concluido.emit()

    def linhas_do_desfecho(self) -> List[str]:
        """
        O desfecho da coleta, como ÚLTIMA coisa que o console mostra.

        A tela terminava no lacre ("[CONCLUÍDO] Manifesto...") e quem lia só o
        fim saía achando que a coleta deu certo, com o backup do iPhone
        recusado poucas linhas acima. Lacrar não é ter coletado. Só console:
        depois do selo nada é escrito na aquisição.
        """
        desfecho = self.desfecho
        if desfecho is None:
            return []
        linhas = ["", "=" * 60]
        if desfecho.integral:
            linhas.append(f"[DESFECHO] {desfecho.resumo}")
        else:
            linhas.append(f"[DESFECHO — ATENÇÃO] {desfecho.resumo}")
            for modulo in desfecho.modulos:
                if modulo.situacao != SUCESSO:
                    linhas.append(f"    {modulo.rotulo.upper()}: {modulo.nome}")
            linhas.append("    'Não obteve dado' NÃO significa ausência de dado no aparelho. "
                          "Detalhes em desfecho/desfecho_da_coleta.txt.")
        linhas.append("=" * 60)
        return linhas

    def texto_da_barra_de_status(self) -> str:
        """Uma linha para a barra de status, no lugar de 'Extração finalizada'."""
        desfecho = self.desfecho
        if desfecho is None:
            return "Extração finalizada."
        if desfecho.integral:
            return f"Extração finalizada — {desfecho.resumo}"
        return f"ATENÇÃO — {desfecho.resumo}"

    def _registrar_execucao(self, execucao: list, identificador, nome, sucesso, mensagem, detalhes) -> None:
        """Emite o sinal para a interface E guarda o mesmo fato para o laudo."""
        execucao.append((identificador, nome, sucesso, mensagem, detalhes))
        self.extrator_concluido.emit(identificador, nome, sucesso, mensagem, detalhes)

    def _encerrar_registro_procedimento(self, desfechos: dict, total: int) -> None:
        """
        Fecha o `registro_procedimento.txt` com o desfecho consolidado.

        É a linha que o examinador lê primeiro ao retomar o caso, e a que o
        relatório cita: quantos módulos completaram, quantos completaram com
        ressalva e quantos falharam. Módulo com ressalva não é módulo bem
        sucedido — misturar os dois é o que produz conclusão negativa falsa.
        """
        resumo = (
            f"{total} módulo(s) executado(s): "
            f"{desfechos['sucesso']} com sucesso pleno, "
            f"{desfechos['ressalva']} com ressalva, "
            f"{desfechos['falha']} com falha. "
            "Módulos com ressalva e com falha estão detalhados em erros/erros.log."
        )
        RegistroProcedimento(self.pasta_caso).encerrar(resumo)

    @staticmethod
    def _fechar_loggers(*loggers) -> None:
        """
        Fecha os arquivos de log antes de o manifesto ser calculado.

        Duas razoes: garante que todo o conteudo esteja em disco no momento
        em que o hash e computado, e libera os descritores -- sem isso, o
        Windows impede mover ou arquivar a pasta do caso enquanto a
        aplicacao estiver aberta.
        """
        for logger in loggers:
            for manipulador in list(logger.handlers):
                manipulador.flush()
                manipulador.close()
                logger.removeHandler(manipulador)

    def _gerar_manifesto_final(self) -> None:
        """
        Gera o manifesto SHA-256 do caso como ÚLTIMO ato da execução.

        A geração era um passo manual e opcional — existia uma janela entre a
        aquisição e o cálculo dos hashes em que o material ficava sem
        qualquer selo. Fechá-la automaticamente vincula o manifesto ao
        momento da aquisição.

        Note que aqui se escreve **apenas no console**, e não no
        `extracao.log`: qualquer linha gravada em arquivo depois de o
        manifesto ser calculado tornaria o próprio caso divergente do seu
        selo. O que a suíte faz depois de selar não pertence ao caso.
        """
        try:
            self.log_emitido.emit("")
            self.log_emitido.emit("[*] Gerando manifesto de integridade (SHA-256) do caso...")
            gerar_manifesto(self.pasta_caso, log_callback=self.log_emitido.emit)
        except OSError as exc:
            self.log_emitido.emit(
                f"[ERRO] Não foi possível gerar o manifesto de integridade: {exc}"
            )
