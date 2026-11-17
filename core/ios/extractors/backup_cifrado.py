"""
Backup CIFRADO do iPhone com senha temporária — para obter o que o backup
comum não traz.

O iOS só põe no backup o registro de chamadas, as senhas salvas, o
histórico de navegação e os dados de saúde quando o backup é cifrado. Se o
dono nunca definiu senha de backup, a única forma de obtê-los sem
jailbreak é DEFINIR uma, fazer o backup e RETIRÁ-LA.

Isso é alteração de configuração do aparelho, por isso o módulo é de
seleção expressa e segue a regra do agente do Android:

- a senha é gerada pela suíte e registrada (sem ela o backup é ilegível, e
  outro examinador precisa poder repetir a decifragem);
- a retirada da senha é tentada SEMPRE, inclusive quando o backup falha;
- o aparelho é conferido no fim, e senha que ficou é FALHA em voz alta.

Se o aparelho JÁ tem senha de backup, o módulo não faz nada: a senha é do
dono, e trocá-la seria alteração que o examinador não teria como desfazer.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from core import backup_ios
from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from ..client import ErroIOS
from .base import IOSExtractor

NOME_SENHA = "senha_do_backup.txt"
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I, para ditar sem erro


def gerar_senha() -> str:
    return "-".join("".join(secrets.choice(ALFABETO) for _ in range(4)) for _ in range(4))


@registrar_extrator
class BackupCifradoExtractorIOS(IOSExtractor):
    id = "ios_backup_cifrado"
    nome_exibicao = "Backup CIFRADO do iPhone com senha temporária (traz chamadas)"
    ordem = 15
    selecao_expressa = True
    caminhos_de_origem = ("backup_local_do_ios",)
    pasta_do_backup = backup_ios.PASTA_CIFRADO
    descricao = (
        "Define no iPhone uma senha de backup gerada pela suíte, faz o backup cifrado — que "
        "inclui o registro de chamadas — e retira a senha ao final. ALTERA A CONFIGURAÇÃO "
        "do aparelho durante a coleta; o iPhone pede o código de desbloqueio na tela."
    )

    limitacoes_conhecidas = (
        "Só funciona em iPhone sem senha de backup definida pelo dono. Com senha do dono, "
        "use o backup comum e a senha dele.",
        "O iPhone pede o código de desbloqueio na tela para aceitar e para retirar a senha "
        "de backup: sem quem o digite, o módulo não prossegue.",
        "Obtém o que o iOS inclui no backup cifrado. Mensagens e arquivos apagados não são "
        "recuperados.",
    )

    alteracoes_no_dispositivo = (
        (
            "Uma senha de backup, gerada pela suíte, é definida no iPhone durante a coleta e "
            "retirada ao final; a retirada é conferida.",
            "Sem backup cifrado o iOS não entrega o registro de chamadas nem outros dados "
            "sensíveis. Nenhum dado do usuário é alterado; a senha consta do registro para "
            "que a decifragem seja repetível.",
        ),
        (
            "O iPhone registra a estação como computador confiável (pareamento) e anota a "
            "data do último backup local.",
            "Condição imposta pelo iOS para entregar qualquer backup.",
        ),
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = Path(pasta_caso) / self.pasta_do_backup
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            ja_cifrava = self.client.cifragem_ativa()
        except ErroIOS as erro:
            return ResultadoExtracao(
                False, self._t("lg_iz_nao_exec_erro", erro=erro), pasta)
        if getattr(self.client, "cifragem_informada", None) is False:
            self.log(self._t("lg_iz_sem_willencrypt"))
        if ja_cifrava:
            return ResultadoExtracao(
                False, self._t("lg_iz_ja_cifra"), pasta,
            )

        senha = gerar_senha()
        (pasta / NOME_SENHA).write_text(
            self._t("lg_iz_senha_arquivo", senha=senha),
            encoding="utf-8",
        )
        self.registrar_alteracao(
            pasta_caso,
            self._t("lg_iz_alt_define", senha=senha),
            self._t("lg_iz_alt_define_motivo"),
        )
        self.log(self._t("lg_iz_definindo"))
        try:
            self.client.alterar_senha_de_backup(nova=senha)
            cifrando = self.client.cifragem_ativa()
        except ErroIOS as erro:
            return self._encerrar(pasta_caso, pasta, senha, None,
                                  self._t("lg_iz_nao_aceitou", erro=erro))
        if not cifrando:
            return self._encerrar(pasta_caso, pasta, senha, None,
                                  self._t("lg_iz_nao_cifrou"))
        self.progresso(10)
        desfecho = self.fazer_backup(pasta_caso)
        return self._encerrar(pasta_caso, pasta, senha, desfecho, desfecho.erro)

    def _encerrar(self, pasta_caso, pasta, senha, desfecho, motivo_da_falha) -> ResultadoExtracao:
        """Retira a senha — SEMPRE — e confere."""
        self.log(self._t("lg_iz_retirando"))
        try:
            if self.client.cifragem_ativa():
                self.client.alterar_senha_de_backup(antiga=senha)
            retirada = not self.client.cifragem_ativa()
        except ErroIOS as erro:
            self.log(self._t("lg_iz_alerta", erro=erro))
            retirada = False
        self.registrar_alteracao(
            pasta_caso,
            self._t("lg_iz_alt_retirada") if retirada else
            self._t("lg_iz_alt_nao_retirada", senha=senha),
            self._t("lg_iz_alt_retirada_motivo"),
        )
        pendente = "" if retirada else self._t("lg_iz_pendente", senha=senha)
        detalhes = {"restauracao_pendente": True} if pendente else {}

        if motivo_da_falha or desfecho is None:
            return ResultadoExtracao(
                False,
                self._t("lg_iz_sem_backup", motivo=motivo_da_falha) + pendente,
                pasta, detalhes,
            )
        # O que vale é o Manifest.plist do backup, não a configuração lida antes.
        detalhes.update(arquivos_copiados=desfecho.arquivos,
                        bytes_copiados=desfecho.bytes_copiados,
                        backup_cifrado=bool(desfecho.cifrado))
        if desfecho.cifrado:
            mensagem = self._t("lg_iz_msg_cifrado", arquivos=desfecho.arquivos,
                               bytes=desfecho.bytes_copiados, senha=senha)
        else:
            detalhes["itens_fora_do_alcance"] = self._t("lg_iz_fora_alcance")
            mensagem = self._t("lg_iz_msg_sem_cifra", arquivos=desfecho.arquivos,
                               bytes=desfecho.bytes_copiados)
        self.progresso(100)
        if pendente:
            return ResultadoExtracao(False, mensagem + pendente, desfecho.pasta, detalhes)
        self.log(self._t("lg_concluido",
                         valor=mensagem + self._t("lg_iz_concluido_sufixo")))
        return ResultadoExtracao(
            True, mensagem + self._t("lg_iz_msg_sufixo"), desfecho.pasta, detalhes,
        )
