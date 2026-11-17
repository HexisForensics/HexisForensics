"""
Artefatos de atividade do sistema — a linha do tempo de uso do aparelho.

Estes dados respondem a perguntas que o conteúdo dos aplicativos não
responde, e são obtidos sem root, em segundos:

- **`usagestats`** — quando cada aplicativo foi usado, e por quanto tempo.
  É o que permite dizer se o aparelho estava sendo operado às 23h40, e por
  qual app. Costuma ser o artefato mais útil de todo este módulo.
- **`wifi`** — redes conhecidas e histórico de associação, que ajudam a
  situar o aparelho geograficamente.
- **`notification`** — notificações ativas e recentes, que às vezes
  preservam o texto de mensagens já apagadas no aplicativo de origem.
- **`batterystats`** — histórico de energia com marcações de tela ligada,
  o que corrobora (ou contradiz) a linha do tempo de uso.

Nenhum deles exige privilégio elevado, e todos são voláteis: reiniciar o
aparelho descarta parte relevante do conteúdo. Por isso este módulo deve
ser executado no início do exame, antes de qualquer operação que possa
provocar reinicialização.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

# nome do arquivo -> (argumentos ADB, chave de idioma da descrição no índice)
COLETAS = {
    "uso_de_aplicativos.txt": (["shell", "dumpsys", "usagestats"], "lg_as_desc_uso"),
    "redes_wifi.txt": (["shell", "dumpsys", "wifi"], "lg_as_desc_wifi"),
    "conectividade.txt": (["shell", "dumpsys", "connectivity"], "lg_as_desc_conectividade"),
    "notificacoes.txt": (["shell", "dumpsys", "notification"], "lg_as_desc_notificacoes"),
    "historico_bateria.txt": (["shell", "dumpsys", "batterystats"], "lg_as_desc_bateria"),
    "aplicativos_em_execucao.txt": (
        ["shell", "dumpsys", "activity", "activities"], "lg_as_desc_execucao"),
    # Diz QUAIS contas estao configuradas no aparelho, e de que tipo.
    "contas_configuradas.txt": (["shell", "dumpsys", "account"], "lg_as_desc_contas"),
    "processos.txt": (["shell", "ps", "-A"], "lg_as_desc_processos"),
    "pacotes_detalhado.txt": (["shell", "dumpsys", "package"], "lg_as_desc_pacotes"),
}

# Abaixo deste tamanho a saída é tratada como recusa ou vazio, não como dado.
TAMANHO_MINIMO_UTIL = 40


@registrar_extrator
class ArtefatosSistemaExtractor(AndroidExtractor):
    id = "android_artefatos_sistema"
    nome_exibicao = "Artefatos de Atividade do Sistema"
    ordem = 25
    descricao = (
        "Coleta a linha do tempo de uso de aplicativos (usagestats), redes Wi-Fi conhecidas, "
        "notificações, histórico de bateria, processos, contas configuradas e permissões "
        "concedidas por pacote. "
        "Responde quando o aparelho foi usado e por qual aplicativo. "
        "ATENÇÃO: são dados voláteis — execute este módulo no início do exame, pois "
        "reiniciar o aparelho descarta parte do conteúdo."
    )

    limitacoes_conhecidas = (
        "Os artefatos são voláteis: reiniciar o aparelho descarta parte "
        "relevante do conteúdo. O que se obtém é o que o sistema ainda retinha "
        "no momento da coleta.",
        "A janela de retenção é do próprio Android e varia com a versão e o "
        "fabricante. Ausência de registro em determinado período não demonstra "
        "que o aparelho não foi usado nele.",
        "A lista de contas configuradas diz quais serviços o aparelho conhece — "
        "endereços de e-mail, mensageiros, nuvem. Não traz mensagem nem arquivo "
        "algum desses serviços: é inventário de contas, não de conteúdo.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = pasta_caso / "artefatos_sistema"
        pasta.mkdir(parents=True, exist_ok=True)

        obtidos, vazios, recusados = [], [], []
        total = len(COLETAS)

        for indice, (nome_arquivo, (argumentos, chave_desc)) in enumerate(COLETAS.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, self._t("lg_cancelada_modulo"), pasta)

            self.log(self._t("lg_as_coletando", descricao=self._t(chave_desc)))
            resultado = self.adb.executar_detalhado(argumentos, timeout=180)

            if not resultado.sucesso:
                conteudo = self._t("lg_as_falhou_conteudo", motivo=resultado.motivo_falha)
                recusados.append(nome_arquivo)
                self.log(self._t("lg_as_falhou", motivo=resultado.motivo_falha))
            elif len(resultado.stdout.strip()) < TAMANHO_MINIMO_UTIL:
                conteudo = resultado.stdout or self._t("lg_as_saida_vazia")
                vazios.append(nome_arquivo)
                self.log(self._t("lg_as_vazia"))
            else:
                conteudo = resultado.stdout
                obtidos.append(nome_arquivo)
                self.log(self._t("lg_as_coletados", n=len(conteudo)))

            (pasta / nome_arquivo).write_text(conteudo, encoding="utf-8")
            self.progresso(int(indice / total * 100))

        self._gravar_indice(pasta, obtidos, vazios, recusados)

        detalhes = {
            "artefatos_obtidos": obtidos,
            "artefatos_vazios": vazios,
            "artefatos_recusados": recusados,
        }

        if not obtidos:
            self.log(self._t("lg_falha", valor=self._t("lg_as_falha_log")))
            return ResultadoExtracao(
                False,
                self._t("lg_as_falha_msg"),
                caminho_saida=pasta,
                detalhes=detalhes,
            )

        mensagem = self._t("lg_as_msg_ok", n=len(obtidos))
        if recusados or vazios:
            # Coleta parcial não pode passar por completa: o exame precisa
            # saber qual artefato não veio antes de concluir sobre ausência de uso.
            detalhes["copia_incompleta"] = True
            mensagem += self._t("lg_as_ress_msg", n=len(recusados + vazios))
            self.log(self._t("lg_ressalva", valor=self._t(
                "lg_as_sem_conteudo", lista=', '.join(recusados + vazios))))

        self.log(self._t("lg_concluido", valor=mensagem))
        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    def _gravar_indice(self, pasta: Path, obtidos, vazios, recusados) -> None:
        """
        Índice do que cada arquivo contém e do que não foi obtido.

        Sem ele, uma pasta com oito arquivos de `dumpsys` é ilegível para
        quem não conhece o Android — e o que **não** veio fica invisível.
        """
        linhas = [self._t("lg_as_idx_titulo"), "=" * 66, ""]
        for nome_arquivo, (_, chave_desc) in COLETAS.items():
            if nome_arquivo in obtidos:
                situacao = self._t("lg_as_idx_coletado")
            elif nome_arquivo in vazios:
                situacao = self._t("lg_as_idx_sem_conteudo")
            else:
                situacao = self._t("lg_as_idx_nao_obtido")
            linhas += [f"{nome_arquivo}",
                       self._t("lg_as_idx_conteudo", descricao=self._t(chave_desc)),
                       self._t("lg_as_idx_situacao", situacao=situacao), ""]

        linhas += ["=" * 66] + self._t("lg_as_idx_nota").split("\n")
        (pasta / "INDICE.txt").write_text("\n".join(linhas), encoding="utf-8")
