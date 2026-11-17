"""
Estado do aparelho no momento em que foi recebido.

Documenta como o dispositivo chegou às mãos do examinador — antes de
qualquer coleta que altere o que está na tela. É o equivalente digital da
fotografia da cena: registra o que estava aberto, se a tela estava
bloqueada, o nível de bateria e quantos perfis de usuário existem.

Por que é o primeiro módulo (ordem 5): qualquer outra coleta pode acender a
tela, disparar notificação ou trazer um aplicativo para primeiro plano. O
estado registrado depois disso já não é o estado em que o aparelho foi
recebido.

A captura de tela usa `exec-out`, e não `adb shell`: o `shell` traduz quebras
de linha no fluxo de saída, o que corromperia silenciosamente o PNG — o
mesmo cuidado que a extração física exige.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.hashing import EscritorComHash, gravar_hash_avulso
from core.registry import registrar_extrator

from .base import AndroidExtractor

# nome do arquivo -> (argumentos, descrição PT [fonte], chave de idioma do rótulo)
ESTADO_TEXTUAL = {
    "energia_e_tela.txt": (["shell", "dumpsys", "power"], "Estado de energia e da tela",
                           "lg_estado_rot_energia"),
    "bateria.txt": (["shell", "dumpsys", "battery"], "Nível e saúde da bateria",
                    "lg_estado_rot_bateria"),
    "bloqueio_de_tela.txt": (
        ["shell", "dumpsys", "trust"],
        "Estado do bloqueio de tela e agentes de confiança",
        "lg_estado_rot_bloqueio",
    ),
    "perfis_de_usuario.txt": (
        ["shell", "pm", "list", "users"],
        "Perfis de usuário existentes no aparelho",
        "lg_estado_rot_perfis",
    ),
    "aplicativo_em_primeiro_plano.txt": (
        ["shell", "dumpsys", "activity", "activities"],
        "Aplicativo em primeiro plano no momento da coleta",
        "lg_estado_rot_primeiro_plano",
    ),
}


@registrar_extrator
class EstadoDispositivoExtractor(AndroidExtractor):
    id = "android_estado_inicial"
    nome_exibicao = "Estado do Aparelho ao Ser Recebido"
    ordem = 5
    descricao = (
        "Registra o aparelho como foi recebido: captura de tela, estado de energia e de "
        "bloqueio, nível de bateria, aplicativo em primeiro plano e perfis de usuário. "
        "Execute PRIMEIRO: qualquer outra coleta pode acender a tela ou trazer um "
        "aplicativo para frente, e o estado registrado depois disso já não é o estado em "
        "que o dispositivo chegou."
    )

    limitacoes_conhecidas = (
        "Registra o estado no instante em que este módulo roda. Qualquer coleta "
        "executada antes dele pode ter acendido a tela ou trazido um aplicativo "
        "para primeiro plano — por isso ele encabeça a lista.",
        "A captura de tela mostra o que estava visível. Conteúdo protegido pelo "
        "bloqueio não é revelado por ela.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = pasta_caso / "estado_inicial"
        pasta.mkdir(parents=True, exist_ok=True)

        detalhes = {}
        self.log_t("lg_estado_inicio")

        captura_ok, motivo_captura = self._capturar_tela(pasta)
        detalhes["captura_de_tela"] = captura_ok
        self.progresso(50)

        coletados = []
        total = len(ESTADO_TEXTUAL)
        for indice, (nome_arquivo, (argumentos, _rotulo, chave_rotulo)) in enumerate(
            ESTADO_TEXTUAL.items(), 1
        ):
            if self.cancelado:
                return ResultadoExtracao(False, self._t("lg_cancelada_modulo"), pasta)

            resultado = self.adb.executar_detalhado(argumentos, timeout=120)
            conteudo = resultado.stdout or f"(sem saída) {resultado.motivo_falha}"
            (pasta / nome_arquivo).write_text(conteudo, encoding="utf-8")
            if resultado.sucesso and resultado.stdout.strip():
                coletados.append(self._t(chave_rotulo))
            self.progresso(50 + int(indice / total * 45))

        perfis = self.contar_perfis_de_usuario()
        detalhes["perfis_de_usuario"] = perfis
        self._gravar_resumo(pasta, captura_ok, motivo_captura, coletados, perfis)
        self.progresso(100)

        if perfis and perfis > 1:
            # Perfis adicionais (perfil de trabalho, segundo usuário) têm
            # área de dados própria, fora do alcance da extração lógica.
            aviso = self.restricao_de_multiplos_usuarios(perfis)
            detalhes["copia_incompleta"] = True
            detalhes["perfis_nao_extraidos"] = perfis - 1
            self.log(self._t("lg_ressalva", valor=aviso))
            self.registrar_decisao(
                pasta_caso,
                f"Extração restrita ao usuário principal, dentre {perfis} perfis existentes.",
                aviso,
            )

        if not captura_ok and not coletados:
            return ResultadoExtracao(
                False,
                self._t("lg_estado_nada"),
                caminho_saida=pasta,
                detalhes=detalhes,
            )

        mensagem = (
            self._t("lg_estado_msg", n=len(coletados))
            + (self._t("lg_estado_com_captura") if captura_ok
               else self._t("lg_estado_sem_captura"))
        )
        if perfis and perfis > 1:
            mensagem += self._t("lg_estado_ressalva_perfis", perfis=perfis)

        self.log(self._t("lg_concluido", valor=mensagem))
        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    # ------------------------------------------------------------------
    def _capturar_tela(self, pasta: Path):
        """
        Captura a tela via `exec-out`, hasheando durante a gravação.

        `adb shell` traduziria quebras de linha no fluxo e corromperia o PNG
        silenciosamente — o arquivo teria tamanho plausível e conteúdo
        adulterado.
        """
        if not self.adb.suporta_exec_out():
            motivo = self._t("lg_estado_motivo_execout")
            self.log(self._t("lg_estado_captura_nao_realizada", motivo=motivo))
            return False, motivo

        caminho = pasta / "tela_ao_receber.png"
        with open(caminho, "wb") as arquivo:
            escritor = EscritorComHash(arquivo)
            resultado = self.adb.stream_binario(
                ["exec-out", "screencap", "-p"],
                escritor.escrever,
                cancelado=lambda: self.cancelado,
            )

        if not resultado.sucesso or escritor.bytes_gravados == 0:
            motivo = resultado.stderr or self._t("lg_estado_motivo_sem_imagem")
            try:
                caminho.unlink()
            except OSError:
                pass
            self.log(self._t("lg_estado_captura_nao_obtida", motivo=motivo))
            return False, motivo

        gravar_hash_avulso(caminho, escritor.hash_hex)
        self.log(self._t("lg_estado_captura_gravada", n=escritor.bytes_gravados))
        return True, ""

    def _gravar_resumo(self, pasta: Path, captura_ok, motivo_captura, coletados, perfis) -> None:
        captura_txt = (self._t("lg_estado_captura_obtida") if captura_ok
                       else self._t("lg_estado_captura_resumo_nao", motivo=motivo_captura))
        perfis_txt = perfis if perfis else self._t("lg_estado_nao_determinado")
        linhas = [
            "=" * 70,
            self._t("lg_estado_resumo_titulo").center(70),
            "=" * 70,
            "",
            self._t("lg_estado_resumo_captura", valor=captura_txt),
            self._t("lg_estado_resumo_perfis", valor=perfis_txt),
            "",
            self._t("lg_estado_resumo_itens"),
        ]
        linhas += [f"  - {item}" for item in coletados] or [self._t("lg_estado_resumo_nenhum")]

        if perfis and perfis > 1:
            linhas += ["", self._t("lg_estado_resumo_perfis_titulo"),
                       self.restricao_de_multiplos_usuarios(perfis)]

        linhas += [
            "",
            "=" * 70,
            self._t("lg_estado_resumo_nota1"),
            self._t("lg_estado_resumo_nota2"),
            "=" * 70,
        ]
        (pasta / "RESUMO_ESTADO.txt").write_text("\n".join(linhas), encoding="utf-8")
