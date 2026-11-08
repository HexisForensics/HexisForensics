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

# nome do arquivo -> (argumentos ADB, descrição para o índice)
COLETAS = {
    "uso_de_aplicativos.txt": (
        ["shell", "dumpsys", "usagestats"],
        "Linha do tempo de uso de cada aplicativo",
    ),
    "redes_wifi.txt": (
        ["shell", "dumpsys", "wifi"],
        "Redes Wi-Fi conhecidas e histórico de associação",
    ),
    "conectividade.txt": (
        ["shell", "dumpsys", "connectivity"],
        "Estado e histórico de conectividade de rede",
    ),
    "notificacoes.txt": (
        ["shell", "dumpsys", "notification"],
        "Notificações ativas e recentes",
    ),
    "historico_bateria.txt": (
        ["shell", "dumpsys", "batterystats"],
        "Histórico de energia, com marcações de tela ligada",
    ),
    "aplicativos_em_execucao.txt": (
        ["shell", "dumpsys", "activity", "activities"],
        "Atividades e tarefas em execução no momento da coleta",
    ),
    # Diz QUAIS contas estao configuradas no aparelho, e de que tipo:
    # `com.google` para Gmail, `com.microsoft.office.outlook` para Outlook,
    # Exchange, e os mensageiros que se registram como conta. Nao traz
    # mensagem alguma -- traz a pergunta que o examinador sempre faz
    # primeiro, que e de quem e este aparelho e a que servicos ele responde.
    "contas_configuradas.txt": (
        ["shell", "dumpsys", "account"],
        "Contas configuradas no aparelho e seus tipos (e-mail, mensageiros, nuvem)",
    ),
    "processos.txt": (["shell", "ps", "-A"], "Processos em execução"),
    "pacotes_detalhado.txt": (
        ["shell", "dumpsys", "package"],
        "Pacotes instalados, permissões concedidas e datas de instalação",
    ),
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
        pasta = pasta_caso / "artefatos_sistema"
        pasta.mkdir(parents=True, exist_ok=True)

        obtidos, vazios, recusados = [], [], []
        total = len(COLETAS)

        for indice, (nome_arquivo, (argumentos, descricao)) in enumerate(COLETAS.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, "Extração cancelada pelo usuário.", pasta)

            self.log(f"[*] Coletando: {descricao}...")
            resultado = self.adb.executar_detalhado(argumentos, timeout=180)

            if not resultado.sucesso:
                conteudo = f"(coleta falhou) {resultado.motivo_falha}"
                recusados.append(nome_arquivo)
                self.log(f"    [RESSALVA] Falhou: {resultado.motivo_falha}")
            elif len(resultado.stdout.strip()) < TAMANHO_MINIMO_UTIL:
                conteudo = resultado.stdout or "(saída vazia)"
                vazios.append(nome_arquivo)
                self.log("    (saída vazia ou insuficiente — registrada como tal)")
            else:
                conteudo = resultado.stdout
                obtidos.append(nome_arquivo)
                self.log(f"    -> {len(conteudo)} caracteres coletados")

            (pasta / nome_arquivo).write_text(conteudo, encoding="utf-8")
            self.progresso(int(indice / total * 100))

        self._gravar_indice(pasta, obtidos, vazios, recusados)

        detalhes = {
            "artefatos_obtidos": obtidos,
            "artefatos_vazios": vazios,
            "artefatos_recusados": recusados,
        }

        if not obtidos:
            self.log("[FALHA] Nenhum artefato de sistema pôde ser coletado.")
            return ResultadoExtracao(
                False,
                "Nenhum artefato de atividade do sistema foi obtido.",
                caminho_saida=pasta,
                detalhes=detalhes,
            )

        mensagem = f"{len(obtidos)} artefato(s) de atividade coletados."
        if recusados or vazios:
            # Coleta parcial não pode passar por completa: o exame precisa
            # saber qual artefato não veio antes de concluir sobre ausência de uso.
            detalhes["copia_incompleta"] = True
            mensagem += f" Ressalva: {len(recusados + vazios)} sem conteúdo útil."
            self.log(f"[RESSALVA] Sem conteúdo útil: {', '.join(recusados + vazios)}")

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    @staticmethod
    def _gravar_indice(pasta: Path, obtidos, vazios, recusados) -> None:
        """
        Índice do que cada arquivo contém e do que não foi obtido.

        Sem ele, uma pasta com oito arquivos de `dumpsys` é ilegível para
        quem não conhece o Android — e o que **não** veio fica invisível.
        """
        linhas = ["ÍNDICE DOS ARTEFATOS DE ATIVIDADE DO SISTEMA", "=" * 66, ""]
        for nome_arquivo, (_, descricao) in COLETAS.items():
            if nome_arquivo in obtidos:
                situacao = "COLETADO"
            elif nome_arquivo in vazios:
                situacao = "SEM CONTEÚDO (o aparelho respondeu vazio)"
            else:
                situacao = "NÃO OBTIDO (a coleta falhou)"
            linhas += [f"{nome_arquivo}", f"    Conteúdo: {descricao}", f"    Situação: {situacao}", ""]

        linhas += [
            "=" * 66,
            "NOTA: a ausência de registro em qualquer destes artefatos NÃO autoriza",
            "concluir que o evento não ocorreu. O Android limita a retenção desses",
            "dados e os descarta ao reiniciar o aparelho.",
        ]
        (pasta / "INDICE.txt").write_text("\n".join(linhas), encoding="utf-8")
