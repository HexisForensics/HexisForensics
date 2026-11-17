"""
Mensageiros além do WhatsApp — mídia e arquivos em armazenamento externo.

Mesma estratégia, mesmas limitações e mesmo padrão do módulo de WhatsApp,
estendidos aos aplicativos que aparecem com mais frequência em exames:
Telegram, Signal, Instagram, Messenger, Snapchat e Threema.

O que se obtém sem root é o que o aplicativo grava **fora** de sua área
privada: fotos, vídeos, áudios e documentos trocados em conversa. O banco
de mensagens de cada um fica em `/data/data/<pacote>/` e exige privilégio
elevado — ausência de mensagens aqui não é ausência de mensagens no
aparelho, e o relatório precisa dizer isso com todas as letras.

Cada aplicativo só é consultado se estiver instalado, e a distinção entre
"não instalado", "instalado sem mídia externa" e "acesso recusado" é
preservada: as três levam a conclusões diferentes.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

# rótulo -> (pacote, caminhos candidatos em armazenamento externo)
MENSAGEIROS = {
    "Telegram": (
        "org.telegram.messenger",
        [
            "/sdcard/Telegram",
            "/sdcard/Android/media/org.telegram.messenger/Telegram",
        ],
    ),
    "TelegramX": (
        "org.thunderdog.challegram",
        ["/sdcard/Android/media/org.thunderdog.challegram"],
    ),
    "Signal": (
        "org.thoughtcrime.securesms",
        [
            "/sdcard/Signal",
            "/sdcard/Android/media/org.thoughtcrime.securesms",
        ],
    ),
    "Instagram": (
        "com.instagram.android",
        [
            "/sdcard/Pictures/Instagram",
            "/sdcard/DCIM/Instagram",
            "/sdcard/Android/media/com.instagram.android",
        ],
    ),
    "Messenger": (
        "com.facebook.orca",
        [
            "/sdcard/DCIM/Messenger",
            "/sdcard/Android/media/com.facebook.orca",
        ],
    ),
    "Facebook": (
        "com.facebook.katana",
        [
            "/sdcard/DCIM/Facebook",
            "/sdcard/Android/media/com.facebook.katana",
        ],
    ),
    "Snapchat": (
        "com.snapchat.android",
        [
            "/sdcard/Snapchat",
            "/sdcard/Android/media/com.snapchat.android",
        ],
    ),
    "Threema": ("ch.threema.app", ["/sdcard/Threema"]),
}


@registrar_extrator
class MensageirosExtractor(AndroidExtractor):
    id = "android_mensageiros"
    nome_exibicao = "Outros Mensageiros (best effort, sem root)"
    ordem = 55
    descricao = (
        "Extrai mídia e arquivos em armazenamento externo de Telegram, Signal, Instagram, "
        "Messenger, Facebook, Snapchat e Threema, para os que estiverem instalados. "
        "LIMITAÇÃO: o banco de mensagens de cada aplicativo fica em área privada "
        "(/data/data) e exige root — a ausência de mensagens neste módulo NÃO significa "
        "ausência de mensagens no aparelho."
    )

    limitacoes_conhecidas = (
        "Obtém o que cada aplicativo grava FORA de sua área privada: fotos, "
        "vídeos, áudios e documentos trocados em conversa. O banco de mensagens "
        "fica em área privada e exige privilégio elevado.",
        "AUSÊNCIA DE MENSAGENS AQUI NÃO É AUSÊNCIA DE MENSAGENS NO APARELHO.",
        "Somente os aplicativos previstos neste módulo são consultados. Outro "
        "mensageiro instalado no aparelho não é examinado por ele.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = pasta_caso / "mensageiros"
        pasta.mkdir(parents=True, exist_ok=True)

        instalados, nao_instalados, com_dados, sem_dados, negados = [], [], [], [], []
        aquisicoes = []
        total = len(MENSAGEIROS)

        for indice, (rotulo, (pacote, caminhos)) in enumerate(MENSAGEIROS.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, self._t("lg_cancelada_modulo"), pasta)

            self.progresso(int(indice / total * 100))

            if not self.adb.pacote_instalado(pacote):
                nao_instalados.append(rotulo)
                continue

            instalados.append(rotulo)
            self.log(self._t("lg_ms_instalado", rotulo=rotulo, pacote=pacote))

            teve_dado = False
            for posicao, caminho_remoto in enumerate(caminhos, 1):
                destino = pasta / rotulo / f"local_{posicao}"
                aquisicao = self.adquirir_caminho(
                    caminho_remoto, destino, pasta_caso, rotulo=f"mensageiro_{rotulo}_{posicao}"
                )
                aquisicoes.append(aquisicao)

                if aquisicao.copia.sucesso:
                    teve_dado = True
                if aquisicao.copia.acesso_negado:
                    negados.append(f"{rotulo}: {caminho_remoto}")

            (com_dados if teve_dado else sem_dados).append(rotulo)

        self._gravar_relatorio(pasta, instalados, nao_instalados, com_dados, sem_dados, negados)

        consolidado = self.consolidar_copias([a.copia for a in aquisicoes])
        detalhes = dict(consolidado)
        detalhes.update(self.consolidar_reconciliacao(aquisicoes))
        detalhes.update(
            {
                "aplicativos_instalados": instalados,
                "aplicativos_com_dados": com_dados,
                "aplicativos_sem_midia_externa": sem_dados,
            }
        )
        if negados:
            detalhes["acesso_negado"] = True
        if detalhes.get("arquivos_faltantes"):
            detalhes["copia_incompleta"] = True

        if not instalados:
            self.log(self._t("lg_ms_nenhum_log"))
            return ResultadoExtracao(
                True,
                self._t("lg_ms_nenhum_msg"),
                caminho_saida=pasta,
                detalhes=detalhes,
            )

        self.log(self._t("lg_aviso", valor=self._t("lg_ms_aviso_bancos")))

        mensagem = self._t("lg_ms_msg_ok", instalados=len(instalados), com_dados=len(com_dados),
                           arquivos=consolidado['arquivos_copiados'])
        if sem_dados:
            mensagem += self._t("lg_ms_sem_midia", lista=', '.join(sem_dados))
        self.log(self._t("lg_concluido", valor=mensagem))

        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    def _gravar_relatorio(
        self, pasta: Path, instalados, nao_instalados, com_dados, sem_dados, negados
    ) -> None:
        """
        Relatório que separa as três situações que não podem ser confundidas:
        aplicativo ausente, aplicativo presente sem mídia externa, e acesso
        recusado pelo sistema.
        """
        nenhum = self._t("lg_ms_rel_nenhum")
        linhas = [
            "=" * 70,
            self._t("lg_ms_rel_titulo").center(70),
            "=" * 70,
            "",
            self._t("lg_ms_rel_instalados"),
        ]
        linhas += [f"  - {app}" for app in instalados] or [nenhum]

        linhas += ["", self._t("lg_ms_rel_com_midia")]
        linhas += [f"  - {app}" for app in com_dados] or [nenhum]

        linhas += ["", self._t("lg_ms_rel_sem_midia")]
        linhas += [f"  - {app}" for app in sem_dados] or [nenhum]

        linhas += ["", self._t("lg_ms_rel_nao_instalados")]
        linhas += [f"  - {app}" for app in nao_instalados] or [nenhum]

        if negados:
            linhas += ["", self._t("lg_ms_rel_negados")]
            linhas += [f"  - {item}" for item in negados]

        linhas += ["", "=" * 70, self._t("lg_ms_rel_ressalva_titulo"), ""]
        linhas += self._t("lg_ms_rel_ressalva").split("\n")
        linhas += ["=" * 70]
        (pasta / "RELATORIO_MENSAGEIROS.txt").write_text("\n".join(linhas), encoding="utf-8")
