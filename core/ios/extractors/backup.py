"""
Backup local do iPhone — o mesmo que o iTunes faria.

É a via padrão de aquisição lógica de um iPhone sem jailbreak: o aparelho,
depois de CONFIAR na estação, entrega um backup com mensagens (iMessage e
SMS), agenda, fotos, notas e os dados dos aplicativos que se deixam copiar
(entre eles o WhatsApp). Os bancos conhecidos são interpretados depois, no
Relatório de Conteúdo; aqui o material é adquirido e conferido.

Este módulo NÃO mexe na configuração do aparelho: o backup sai cifrado ou
não conforme o dono deixou. Sem cifra, o iOS deixa de fora o registro de
chamadas e outros dados sensíveis — e o módulo diz isso. Cifrado com senha
que o examinador não tem, o backup é adquirido inteiro, mas só se lê com a
senha (botão "Decifrar backup").
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import EXCLUIDO_DO_BACKUP_SEM_CIFRA, IOSExtractor


@registrar_extrator
class BackupCompletoExtractorIOS(IOSExtractor):
    id = "ios_backup_completo"
    nome_exibicao = "Backup local do iPhone (mensagens, agenda, WhatsApp, fotos)"
    ordem = 10
    caminhos_de_origem = ("backup_local_do_ios",)
    descricao = (
        "Faz o backup local do iPhone pelo mesmo protocolo do iTunes, sem alterar a "
        "configuração do aparelho. Traz iMessage/SMS, agenda, fotos e dados de aplicativos "
        "(WhatsApp incluso), interpretados depois no Relatório de Conteúdo."
    )

    limitacoes_conhecidas = (
        "Obtém o que o iOS inclui no backup local. Mensagens e arquivos apagados não são "
        "recuperados, e aplicativos que se excluem do backup não aparecem.",
        "Backup SEM criptografia não traz " + EXCLUIDO_DO_BACKUP_SEM_CIFRA + ": é decisão "
        "do iOS. Para obtê-los é preciso o backup cifrado (módulo de senha temporária).",
        "Se o dono definiu uma senha de backup, o backup sai cifrado e só pode ser lido com "
        "essa senha. Ela não é o código de desbloqueio e não pode ser contornada.",
        "Mensagens guardadas só no iCloud (Mensagens no iCloud com armazenamento otimizado) "
        "podem não estar no aparelho e, portanto, no backup.",
    )

    alteracoes_no_dispositivo = (
        (
            "O iPhone registra a estação como computador confiável (pareamento) e anota a "
            "data do último backup local.",
            "Sem o pareamento, autorizado na tela do aparelho, o iOS não entrega dado algum "
            "a um computador. Nenhum dado do usuário é alterado ou apagado.",
        ),
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        self.registrar_alteracao(
            pasta_caso,
            self._t("lg_ic_alt"),
            self._t("lg_ic_alt_motivo"),
        )
        desfecho = self.fazer_backup(pasta_caso)
        if desfecho.erro:
            return ResultadoExtracao(
                False,
                self._t("lg_ic_sem_backup", erro=desfecho.erro),
                desfecho.pasta or pasta_caso,
            )
        if not desfecho.arquivos:
            return ResultadoExtracao(
                False, self._t("lg_ic_sem_arquivos"),
                desfecho.pasta,
            )

        self.progresso(100)
        detalhes = {"arquivos_copiados": desfecho.arquivos,
                    "bytes_copiados": desfecho.bytes_copiados,
                    "backup_cifrado": bool(desfecho.cifrado)}
        mensagem = self._t("lg_ic_msg_ok", arquivos=desfecho.arquivos,
                           bytes=desfecho.bytes_copiados)
        if desfecho.cifrado:
            detalhes["itens_fora_do_alcance"] = True
            mensagem += self._t("lg_ic_cifrado_msg")
            self.log(self._t("lg_ressalva", valor=self._t("lg_ic_cifrado_log")))
        else:
            detalhes["itens_fora_do_alcance"] = True
            excluido = self._t("lg_ib_excluido")
            mensagem += self._t("lg_ic_sem_cifra_msg", excluido=excluido)
            self.log(self._t("lg_ressalva", valor=self._t("lg_ic_sem_cifra_log", excluido=excluido)))
        self.log(self._t("lg_concluido", valor=mensagem))
        return ResultadoExtracao(True, mensagem, desfecho.pasta, detalhes)
