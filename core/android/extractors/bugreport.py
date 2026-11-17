"""
Relatório de diagnóstico do sistema (`adb bugreport`).

É o artefato mais denso que se obtém de um Android sem root, e reúne num só
pacote coisas que os `dumpsys` avulsos não trazem inteiras: histórico de
energia com marcações de tela ligada, estatísticas de uso por aplicativo,
eventos do sistema, conectividade ao longo do tempo, pacotes com data de
instalação e permissões, além do `logcat` retido.

Em investigação, o valor está na **linha do tempo**: o bugreport frequentemente
permite situar quando o aparelho foi ligado, desligado, quando a tela foi
acesa e qual aplicativo estava em primeiro plano — informação que nenhum
arquivo de mídia carrega.

Duas particularidades tratadas aqui:

- **Formato varia com a versão.** A partir do Android 7 (API 24) o comando
  grava um `.zip`; antes disso, despeja texto na saída padrão. Os dois casos
  são suportados, e o formato obtido fica registrado.
- **Demora.** Leva de um a vários minutos, e por isso roda sob o executor
  controlado: cancelável a qualquer momento e com teto de inatividade, para
  não deixar a aplicação pendurada num aparelho que parou de responder.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.hashing import calcular_sha256
from core.registry import registrar_extrator

from .base import AndroidExtractor

# A partir do Android 7 o `adb bugreport` grava um arquivo .zip em vez de
# despejar texto na saída padrão.
NIVEL_API_BUGREPORT_ZIP = 24

# O bugreport é demorado por natureza; o teto abaixo é de INATIVIDADE, não
# de duração total.
SEGUNDOS_SEM_SINAL = 420


@registrar_extrator
class BugreportExtractor(AndroidExtractor):
    id = "android_bugreport"
    nome_exibicao = "Relatório de Diagnóstico do Sistema (bugreport)"
    ordem = 27
    descricao = (
        "Gera o bugreport do Android: histórico de energia com marcações de tela ligada, "
        "estatísticas de uso por aplicativo, eventos do sistema, conectividade, pacotes com "
        "data de instalação e logcat retido. É o artefato mais denso disponível sem root, e "
        "o que melhor sustenta uma linha do tempo de uso do aparelho. "
        "ATENÇÃO: leva de um a vários minutos e pode ocupar dezenas de MB."
    )

    limitacoes_conhecidas = (
        "O conteúdo varia com a versão do Android e com o fabricante; nem todo "
        "aparelho entrega as mesmas seções.",
        "O log do sistema incluído é circular: cobre apenas o período que ainda "
        "estava retido no aparelho no momento da coleta.",
        "Reúne dados de funcionamento do sistema, não conteúdo de aplicativos — "
        "mensagens, fotos e arquivos do usuário não estão aqui.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = pasta_caso / "bugreport"
        pasta.mkdir(parents=True, exist_ok=True)

        api = self.nivel_api()
        self.log(self._t("lg_br_gerando", api=api or '?'))
        self.progresso(5)

        if api is not None and api < NIVEL_API_BUGREPORT_ZIP:
            resultado, caminho, formato = self._bugreport_em_texto(pasta)
        else:
            resultado, caminho, formato = self._bugreport_em_zip(pasta)

        self.progresso(90)

        if caminho is None or not caminho.exists() or caminho.stat().st_size == 0:
            motivo = resultado.motivo_falha or self._t("lg_br_sem_conteudo")
            self.log(self._t("lg_falha", valor=self._t("lg_br_falha_log", motivo=motivo)))
            # Arquivo vazio não é evidência: é tentativa frustrada, e a
            # tentativa já está no log.
            if caminho is not None and caminho.exists():
                try:
                    caminho.unlink()
                except OSError:
                    pass
            return ResultadoExtracao(
                False,
                self._t("lg_br_falha_msg", motivo=motivo),
                caminho_saida=pasta,
                detalhes={"formato": formato, "api": api},
            )

        tamanho = caminho.stat().st_size
        hash_arquivo = calcular_sha256(caminho)
        (pasta / f"{caminho.name}.sha256").write_text(
            f"{hash_arquivo} *{caminho.name}\n", encoding="utf-8"
        )
        self.progresso(100)

        detalhes = {
            "formato": formato,
            "api": api,
            "arquivo": caminho.name,
            "bytes": tamanho,
            "sha256": hash_arquivo,
        }

        if resultado.expirou:
            # Conteúdo pode estar truncado: o relatório precisa dizer isso.
            detalhes["copia_incompleta"] = True
            self.log(self._t("lg_ressalva", valor=self._t("lg_br_parcial_log")))
            return ResultadoExtracao(
                True,
                self._t("lg_br_parcial_msg", nome=caminho.name, bytes=tamanho),
                caminho_saida=caminho,
                detalhes=detalhes,
            )

        self.log(self._t("lg_concluido",
                         valor=self._t("lg_br_ok_log", nome=caminho.name, bytes=tamanho)))
        return ResultadoExtracao(
            True,
            self._t("lg_br_ok_msg", nome=caminho.name, bytes=tamanho, formato=formato),
            caminho_saida=caminho,
            detalhes=detalhes,
        )

    # ------------------------------------------------------------------
    def _bugreport_em_zip(self, pasta: Path):
        """Android 7 ou superior: o próprio ADB grava o `.zip` no destino."""
        resultado = self.adb.executar_longo(
            ["bugreport", str(pasta)],
            cancelado=lambda: self.cancelado,
            segundos_sem_sinal=SEGUNDOS_SEM_SINAL,
        )
        gerados = sorted(pasta.glob("*.zip"), key=lambda c: c.stat().st_mtime)
        return resultado, (gerados[-1] if gerados else None), "zip"

    def _bugreport_em_texto(self, pasta: Path):
        """Anterior ao Android 7: o relatório sai como texto na saída padrão."""
        resultado = self.adb.executar_longo(
            ["bugreport"],
            cancelado=lambda: self.cancelado,
            segundos_sem_sinal=SEGUNDOS_SEM_SINAL,
        )
        caminho = pasta / "bugreport.txt"
        caminho.write_text(resultado.stdout, encoding="utf-8")
        return resultado, caminho, "texto"
