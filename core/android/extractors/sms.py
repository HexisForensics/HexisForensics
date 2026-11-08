"""
NOVO módulo: extração de mensagens SMS (e MMS).

Segue o mesmo padrão do extrator de contatos/chamadas, consultando os
Content Providers nativos de SMS via `adb shell content query`.

O MMS mora em OUTRO provider (`content://mms`), espalhado em três
consultas: cabeçalhos, partes (o texto e os anexos) e endereços (os
números, uma consulta por mensagem). O módulo se chamava "SMS/MMS" e
consultava só `content://sms` — anunciava um alcance que não tinha. Hoje
as três consultas são feitas e os anexos são lidos em fluxo binário, com
hash na aquisição.

Observação importante (documentada também na GUI via tooltip): a partir do
Android 4.4 (KitKat) apenas o app padrão de SMS tem garantia de acesso de
leitura ao provider `content://sms`. Em muitos aparelhos sem root — mesmo
antigos, dependendo do fabricante/ROM — o shell ADB pode receber
"Permission Denial"; nesse caso o arquivo bruto de erro ainda é salvo,
documentando a tentativa para fins de laudo, e o módulo registra a versão
exata do Android/API do aparelho e tenta `adb backup` como alternativa
best-effort (ver `AndroidExtractor.tentar_fallback_backup`).
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.hashing import EscritorComHash, gravar_hash_avulso
from core.normalizacao import (
    NOME_PARTES_MMS,
    PASTA_ENDERECOS_MMS,
    TIPO_LEIAUTE_MMS,
    TIPO_TEXTO_MMS,
    nome_do_arquivo_de_enderecos,
    registros_brutos,
)
from core.registry import registrar_extrator

from .base import AndroidExtractor, saida_indica_acesso_negado

URIS_SMS = {
    "sms_todas": "content://sms",
    "sms_recebidas": "content://sms/inbox",
    "sms_enviadas": "content://sms/sent",
    "sms_rascunhos": "content://sms/draft",
    "mms_cabecalhos": "content://mms",
    Path(NOME_PARTES_MMS).stem: "content://mms/part",
}

PASTA_ANEXOS_MMS = "mms_anexos"

# Pacotes conhecidos de apps de mensagens, usados apenas como alvo de
# `adb backup` quando o provider de SMS nega acesso — tentamos só os que
# estiverem de fato instalados no aparelho (ver `pacote_instalado`).
PACOTES_SMS_CANDIDATOS = [
    # O pacote DO SISTEMA que guarda SMS e MMS vem primeiro: é ele, e não o
    # aplicativo de mensagens, que entrega o conteúdo. Medido num moto x4
    # de fábrica (Android 9): 33 SMS obtidos, sem root.
    "com.android.providers.telephony",
    "com.google.android.apps.messaging",  # Google Mensagens
    "com.android.messaging",              # AOSP (mais recente)
    "com.android.mms",                    # AOSP legado (Android antigo)
    "com.samsung.android.messaging",      # Samsung
    "com.sonyericsson.conversations",     # Sony
    "com.htc.sense.mms",                  # HTC
    "com.motorola.messaging",             # Motorola
]


@registrar_extrator
class SMSExtractor(AndroidExtractor):
    id = "android_sms"
    nome_exibicao = "Mensagens SMS/MMS"
    ordem = 40
    descricao = (
        "Consulta os Content Providers nativos de SMS (content://sms, inbox, sent, draft) "
        "e de MMS (content://mms: cabeçalhos, partes, endereços e anexos). "
        "ATENÇÃO: o shell ADB pode não ter permissão READ_SMS a menos que o dispositivo "
        "tenha root; nesse caso o provider retorna 'Permission Denial' (registrado nos "
        "arquivos gerados) e o módulo tenta 'adb backup' como alternativa best-effort em "
        "aparelhos com Android abaixo da versão 12."
    )

    limitacoes_conhecidas = (
        "Desde o Android 4.4, apenas o aplicativo padrão de mensagens tem "
        "acesso garantido ao provedor de SMS. Em aparelho sem privilégio "
        "elevado a leitura pode ser negada; a recusa é registrada, mas os dados "
        "não são obtidos.",
        "A via alternativa por backup depende de o aplicativo permiti-lo e foi "
        "removida do sistema a partir do Android 12.",
        "Pela via de backup, quem decide o que é incluído é o agente do próprio "
        "Android: a completude NÃO é verificável, e anexos de MMS não são entregues.",
        "Anexo de MMS é gravado como parte_<id>.bin, sem extensão presumida: o "
        "tipo declarado pelo aparelho está em mms_partes.txt.",
        "Mensagem apagada pelo usuário não é recuperada por esta via. "
        "Recuperação de resíduo depende de imagem física da partição.",
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
        pasta_sms = pasta_caso / "sms"
        pasta_sms.mkdir(parents=True, exist_ok=True)

        sdk = self.log_diagnostico_versao()

        total = len(URIS_SMS)
        algum_acesso_negado = False
        alguma_extracao_ok = False
        saidas: dict = {}

        for indice, (nome_arquivo, uri) in enumerate(URIS_SMS.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, "Extração cancelada pelo usuário.")

            self.log(f"[*] Consultando {uri} ...")
            saida, recusou = self.consultar_provider(
                uri, pasta_sms / f"{nome_arquivo}.txt"
            )

            if recusou:
                algum_acesso_negado = True
            elif saida:
                alguma_extracao_ok = True
                saidas[nome_arquivo] = saida

            self.progresso(int(indice / total * 90))

        if self.cancelado:
            return ResultadoExtracao(False, "Extração cancelada pelo usuário.")
        recusa_no_mms, anexos_obtidos, anexos_falhos = self._complementar_mms(
            pasta_sms, saidas
        )
        algum_acesso_negado = algum_acesso_negado or recusa_no_mms
        self.progresso(100)

        arquivos_backup: list[Path] = []
        if algum_acesso_negado:
            self.log(
                "[ALERTA] O dispositivo negou acesso ao provider de SMS em pelo menos uma "
                "consulta (Permission Denial). As respostas brutas de erro foram preservadas "
                "como evidência da tentativa."
            )
            arquivos_backup = self.tentar_fallback_backup(
                sdk, PACOTES_SMS_CANDIDATOS, pasta_sms, pasta_caso
            )
            if arquivos_backup:
                alguma_extracao_ok = True

        sucesso, mensagem = self.avaliar_consulta_a_provider(
            "Mensagens SMS/MMS", alguma_extracao_ok, algum_acesso_negado, arquivos_backup
        )
        detalhes = {
            "acesso_negado": algum_acesso_negado,
            "algum_dado_obtido": alguma_extracao_ok,
            "sdk_android": sdk,
            "arquivos_backup": [str(caminho) for caminho in arquivos_backup],
            "anexos_mms_obtidos": anexos_obtidos,
        }
        if anexos_falhos:
            detalhes["copia_incompleta"] = True
            detalhes["anexos_mms_nao_obtidos"] = anexos_falhos
            mensagem += (
                f" Ressalva: {len(anexos_falhos)} anexo(s) de MMS não foi(ram) lido(s) "
                f"(partes {', '.join(anexos_falhos)}); a tentativa está em {PASTA_ANEXOS_MMS}/."
            )
        self.log(f"[{'CONCLUÍDO' if sucesso else 'FALHA'}] {mensagem}")
        return ResultadoExtracao(
            sucesso=sucesso,
            mensagem=mensagem,
            caminho_saida=pasta_sms,
            detalhes=detalhes,
        )

    def _complementar_mms(self, pasta_sms: Path, saidas: dict):
        """
        Busca o que o cabeçalho do MMS não traz: os endereços de cada
        mensagem e o conteúdo binário de cada anexo.

        Devolve `(houve_recusa, anexos_obtidos, partes_que_falharam)`.
        """
        houve_recusa = False
        mensagens = registros_brutos(saidas.get("mms_cabecalhos", ""))
        if mensagens:
            self.log(f"[*] MMS: consultando os endereços de {len(mensagens)} mensagem(ns)...")
        for campos in mensagens:
            identificador = campos.get("_id")
            if not identificador or self.cancelado:
                continue
            _saida, recusou = self.consultar_provider(
                f"content://mms/{identificador}/addr",
                pasta_sms / PASTA_ENDERECOS_MMS / nome_do_arquivo_de_enderecos(identificador),
            )
            houve_recusa = houve_recusa or recusou

        obtidos, falhos = 0, []
        partes = registros_brutos(saidas.get(Path(NOME_PARTES_MMS).stem, ""))
        for campos in partes:
            tipo = (campos.get("ct") or "").lower()
            identificador = campos.get("_id")
            if not identificador or tipo in (TIPO_TEXTO_MMS, TIPO_LEIAUTE_MMS):
                continue
            if self.cancelado:
                break
            if self._ler_anexo_mms(pasta_sms / PASTA_ANEXOS_MMS, identificador):
                obtidos += 1
            else:
                falhos.append(identificador)
        if obtidos or falhos:
            self.log(f"[*] MMS: {obtidos} anexo(s) lido(s), {len(falhos)} não lido(s).")
        return houve_recusa, obtidos, falhos

    def _ler_anexo_mms(self, pasta_anexos: Path, identificador: str) -> bool:
        """
        Lê o conteúdo de uma parte de MMS em fluxo binário (`exec-out`,
        sem tradução de bytes), com o hash calculado na gravação.

        Leitura que falha ou não rende byte algum não deixa arquivo de
        anexo: fica só o registro da tentativa, para que zero byte não
        passe por anexo adquirido.
        """
        pasta_anexos.mkdir(parents=True, exist_ok=True)
        destino = pasta_anexos / f"parte_{identificador}.bin"
        with open(destino, "wb") as arquivo:
            escritor = EscritorComHash(arquivo)
            resultado = self.adb.stream_binario(
                ["exec-out", "content", "read", "--uri", f"content://mms/part/{identificador}"],
                escritor.escrever,
            )
        if resultado.stderr:
            destino.with_name(f"parte_{identificador}_stderr.txt").write_text(
                resultado.stderr, encoding="utf-8"
            )
        if resultado.codigo_saida != 0 or escritor.bytes_gravados == 0:
            destino.unlink(missing_ok=True)
            destino.with_name(f"parte_{identificador}_NAO_OBTIDA.txt").write_text(
                f"Leitura de content://mms/part/{identificador} não rendeu conteúdo "
                f"(código {resultado.codigo_saida}, {escritor.bytes_gravados} byte(s)).\n"
                f"stderr: {resultado.stderr or '(vazio)'}\n",
                encoding="utf-8",
            )
            return False
        gravar_hash_avulso(destino, escritor.hash_hex)
        return True
