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
        self.registrar_alteracao(
            pasta_caso,
            "Pareamento da estação com o iPhone e registro, no aparelho, da data do último "
            "backup local.",
            "Condição imposta pelo iOS para entregar o backup local; nenhum dado do usuário "
            "é alterado.",
        )
        desfecho = self.fazer_backup(pasta_caso)
        if desfecho.erro:
            return ResultadoExtracao(
                False,
                f"Nenhum backup foi obtido: {desfecho.erro} Isto NÃO significa ausência de "
                "dados no aparelho.",
                desfecho.pasta or pasta_caso,
            )
        if not desfecho.arquivos:
            return ResultadoExtracao(
                False, "O backup terminou sem nenhum arquivo. Nada foi adquirido.",
                desfecho.pasta,
            )

        self.progresso(100)
        detalhes = {"arquivos_copiados": desfecho.arquivos,
                    "bytes_copiados": desfecho.bytes_copiados,
                    "backup_cifrado": bool(desfecho.cifrado)}
        mensagem = (
            f"Backup local do iPhone obtido: {desfecho.arquivos} arquivo(s), "
            f"{desfecho.bytes_copiados} byte(s), SHA-256 de cada um calculado na aquisição."
        )
        if desfecho.cifrado:
            detalhes["itens_fora_do_alcance"] = True
            mensagem += (
                " O backup está CIFRADO com a senha de backup definida no aparelho: o conteúdo "
                "só será lido com ela (botão 'Decifrar backup')."
            )
            self.log("[RESSALVA] Backup cifrado pelo aparelho — será preciso a senha de backup.")
        else:
            detalhes["itens_fora_do_alcance"] = True
            mensagem += (
                " Backup SEM criptografia: o iOS não incluiu " + EXCLUIDO_DO_BACKUP_SEM_CIFRA
                + "."
            )
            self.log("[RESSALVA] Backup sem criptografia — o iOS deixou de fora "
                     + EXCLUIDO_DO_BACKUP_SEM_CIFRA + ".")
        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(True, mensagem, desfecho.pasta, detalhes)
