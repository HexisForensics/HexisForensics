"""
Migrado de `3_contatos_chamadas.py`: agenda de contatos e histórico de chamadas.

Assim como o extrator de SMS, reconhece quando o Android nega acesso ao
provider (`Permission Denial` / `SecurityException`) — comum em
dispositivos sem root, independente da idade do aparelho, já que
READ_CALL_LOG nem sempre é concedido ao shell ADB por padrão. Quando isso
ocorre, o módulo registra a versão exata do Android/API do aparelho e
tenta `adb backup` do app discador como alternativa best-effort (ver
`AndroidExtractor.tentar_fallback_backup`).
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor, saida_indica_acesso_negado

# Pacotes conhecidos de apps discador/telefone, usados apenas como alvo de
# `adb backup` quando o provider de Call Log nega acesso — tentamos só os
# que estiverem de fato instalados no aparelho.
PACOTES_DISCADOR_CANDIDATOS = [
    # O pacote do sistema que serializa o registro de chamadas vem primeiro.
    # Medido num moto x4 de fábrica (Android 9): 17 chamadas obtidas, sem
    # root. Exige backup chave/valor (ver `backup_android.PACOTES_CHAVE_VALOR`).
    "com.android.calllogbackup",
    "com.google.android.dialer",
    "com.android.dialer",
    "com.samsung.android.dialer",
    "com.android.phone",
]


@registrar_extrator
class ContatosChamadasExtractor(AndroidExtractor):
    id = "android_contatos_chamadas"
    nome_exibicao = "Contatos e Histórico de Chamadas"
    ordem = 30
    descricao = (
        "Consulta os Content Providers nativos do Android "
        "(content://call_log/calls e content://com.android.contacts/data/phones). "
        "ATENÇÃO: o shell ADB pode não ter permissão READ_CALL_LOG a menos que o "
        "dispositivo tenha root; nesse caso o provider retorna 'Permission Denial' "
        "(registrado nos arquivos gerados) e o módulo tenta 'adb backup' do app discador "
        "como alternativa best-effort em aparelhos com Android abaixo da versão 12."
    )

    limitacoes_conhecidas = (
        "Sem privilégio elevado, o Android pode negar a leitura dos provedores "
        "de contatos e de chamadas. A recusa é registrada, mas os dados não são "
        "obtidos.",
        "A via alternativa por backup depende de o aplicativo permiti-lo e foi "
        "removida do sistema a partir do Android 12.",
        "Pela via de backup, quem decide o que é incluído é o agente do próprio "
        "Android: a completude NÃO é verificável, e o nome do contato não acompanha "
        "a chamada.",
        "Obtém o que o aparelho mantinha. Registro apagado pelo usuário não é "
        "recuperado por esta via; recuperação de resíduo depende de imagem "
        "física da partição.",
    )
    alteracoes_no_dispositivo = (
        (
            "Quando a leitura direta é negada e a via de backup é tentada, o "
            "aparelho exibe pedido de confirmação que precisa ser aceito na tela.",
            "É a única via alternativa de obter o dado sem privilégio elevado. "
            "Sem a confirmação, o backup não ocorre e nada é adquirido.",
        ),
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta_dump = pasta_caso / "contacts_calls"
        pasta_dump.mkdir(parents=True, exist_ok=True)

        sdk = self.log_diagnostico_versao()

        algum_acesso_negado = False
        alguma_extracao_ok = False

        self.log("[*] Extraindo Registro de Chamadas (Call Logs)...")
        chamadas, recusou_chamadas = self.consultar_provider(
            "content://call_log/calls", pasta_dump / "registro_chamadas_bruto.txt"
        )

        arquivos_backup: list[Path] = []
        if recusou_chamadas:
            algum_acesso_negado = True
            self.log(
                "[ALERTA] Acesso negado ao provider de Call Log (Permission Denial). "
                "A resposta bruta de erro foi preservada como evidência da tentativa."
            )
            arquivos_backup = self.tentar_fallback_backup(
                sdk, PACOTES_DISCADOR_CANDIDATOS, pasta_dump, pasta_caso
            )
            if arquivos_backup:
                alguma_extracao_ok = True
        elif chamadas:
            alguma_extracao_ok = True
        self.progresso(50)

        if self.cancelado:
            return ResultadoExtracao(False, "Extração cancelada pelo usuário.")

        self.log("[*] Extraindo Agenda Telefônica (Contatos)...")
        contatos, recusou_contatos = self.consultar_provider(
            "content://com.android.contacts/data/phones",
            pasta_dump / "agenda_contatos_bruta.txt",
        )
        if recusou_contatos:
            algum_acesso_negado = True
            self.log(
                "[ALERTA] Acesso negado ao provider de Contatos (Permission Denial). "
                "A resposta bruta de erro foi preservada como evidência da tentativa."
            )
        elif contatos:
            alguma_extracao_ok = True
        self.progresso(100)

        sucesso, mensagem = self.avaliar_consulta_a_provider(
            "Contatos e histórico de chamadas",
            alguma_extracao_ok,
            algum_acesso_negado,
            arquivos_backup,
        )
        self.log(f"[{'CONCLUÍDO' if sucesso else 'FALHA'}] {mensagem}")
        return ResultadoExtracao(
            sucesso=sucesso,
            mensagem=mensagem,
            caminho_saida=pasta_dump,
            detalhes={
                "acesso_negado": algum_acesso_negado,
                "algum_dado_obtido": alguma_extracao_ok,
                "sdk_android": sdk,
                "arquivos_backup": [str(caminho) for caminho in arquivos_backup],
            },
        )
