"""
NOVO módulo: extração best-effort de dados do WhatsApp (e WhatsApp Business)
sem exigir root.

Estratégia: usar `adb pull` nos caminhos de armazenamento externo onde o
WhatsApp guarda mídias e backups locais criptografados (.crypt12/14/15).
Esses caminhos variam conforme a versão do Android (armazenamento
"legado" vs. scoped storage a partir do Android 11), então tentamos todos
os candidatos conhecidos.

LIMITAÇÃO DOCUMENTADA: o banco de dados ativo de mensagens (msgstore.db) e
a chave de criptografia usada para decifrar os backups .crypt* ficam em
`/data/data/com.whatsapp/...`, uma área privada do app só acessível com o
dispositivo rooteado. Este módulo não tenta decodificar os backups — ele
apenas os preserva como estão para eventual perícia posterior com a chave
adequada.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.hashing import calcular_sha256
from core.registry import registrar_extrator

from .base import AndroidExtractor

CAMINHOS_CANDIDATOS = {
    "WhatsApp_Media_legado": "/sdcard/WhatsApp/Media",
    "WhatsApp_Media_scoped": "/sdcard/Android/media/com.whatsapp/WhatsApp/Media",
    "WhatsApp_Databases_legado": "/sdcard/WhatsApp/Databases",
    "WhatsApp_Databases_scoped": "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases",
    "WhatsAppBusiness_Media": "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media",
    "WhatsAppBusiness_Databases": "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases",
}


# Registro, feito NA aquisição, de quando cada backup foi gravado no
# aparelho. Sem ele, o conteúdo decifrado parecia retratar o aparelho no dia
# do exame — e uma conversa posterior ao backup, ausente, parecia não existir.
# Visto no moto x4 em 24/10/2026: o backup copiado era de 12/10.
NOME_DATAS_DOS_BACKUPS = "datas_dos_backups.json"


@registrar_extrator
class WhatsAppExtractor(AndroidExtractor):
    id = "android_whatsapp"
    nome_exibicao = "WhatsApp — Mídia e Backups (best effort, sem root)"
    ordem = 50
    caminhos_de_origem = tuple(CAMINHOS_CANDIDATOS.values())
    descricao = (
        "Extrai, sem necessidade de root, as pastas de mídia e os backups locais "
        "criptografados (.crypt12/.crypt14/.crypt15) do WhatsApp e WhatsApp Business "
        "acessíveis no armazenamento externo. "
        "LIMITAÇÃO: o banco msgstore.db ativo e a chave de criptografia ficam em "
        "/data/data/com.whatsapp e exigem root para acesso."
    )

    limitacoes_conhecidas = (
        "O banco de mensagens ativo e a chave que decifra os backups ficam em "
        "área privada do aplicativo, acessível apenas com privilégio elevado.",
        "Os backups são preservados como estão, criptografados. Este módulo não "
        "os decifra; lê-los exige a chave, em perícia posterior.",
        "Sem privilégio elevado, a via para o banco em claro é o módulo de "
        "substituição temporária do aplicativo, que altera o dispositivo e é de "
        "seleção expressa.",
        "AUSÊNCIA DE MENSAGENS AQUI NÃO É AUSÊNCIA DE MENSAGENS NO APARELHO.",
    )

    def _registrar_datas_dos_backups(self, pasta_caso: Path, pasta_whatsapp: Path) -> None:
        """
        Pergunta ao aparelho (`stat`) a data de gravação de cada backup
        copiado e grava, com o SHA-256 da cópia, dentro da aquisição — antes
        do lacre. A resposta crua do aparelho vai junto.
        """
        registros, bruto = [], []
        for nome, caminho_android in CAMINHOS_CANDIDATOS.items():
            pasta = pasta_whatsapp / nome
            if not pasta.is_dir():
                continue
            for local in sorted(pasta.rglob("*.crypt*")):
                # `adb pull <origem> <destino>` cria `<destino>/<nome da origem>/`.
                partes = local.relative_to(pasta).as_posix().split("/")
                if partes[0] == caminho_android.rstrip("/").rsplit("/", 1)[-1]:
                    partes = partes[1:]
                remoto = f"{caminho_android}/{'/'.join(partes)}"
                resultado = self.adb.executar_detalhado(
                    ["shell", f"stat -c '%Y' {self.aspas_para_shell(remoto)}"], timeout=30)
                bruto.append(f"$ stat -c '%Y' {remoto}\ncodigo {resultado.codigo_saida}\n"
                             f"{resultado.stdout}\n{resultado.stderr}".rstrip())
                epoch = resultado.stdout.strip()
                registros.append({
                    "arquivo": local.relative_to(pasta_caso).as_posix(),
                    "caminho_no_aparelho": remoto,
                    "gravado_no_aparelho_epoch": int(epoch) if epoch.isdigit() else None,
                    "sha256": calcular_sha256(local),
                })
        if not registros:
            return
        (pasta_whatsapp / NOME_DATAS_DOS_BACKUPS).write_text(
            json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
        (pasta_whatsapp / "datas_dos_backups_saida.txt").write_text(
            "\n\n".join(bruto) + "\n", encoding="utf-8")
        for registro in registros:
            if registro["gravado_no_aparelho_epoch"]:
                self.log(f"    backup {registro['arquivo']}: gravado no aparelho em epoch "
                         f"{registro['gravado_no_aparelho_epoch']}")

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta_whatsapp = pasta_caso / "whatsapp"
        pasta_whatsapp.mkdir(parents=True, exist_ok=True)

        total = len(CAMINHOS_CANDIDATOS)
        aquisicoes = []

        for indice, (nome, caminho_android) in enumerate(CAMINHOS_CANDIDATOS.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, "Extração cancelada pelo usuário.")

            self.log(f"[*] Tentando extrair '{caminho_android}'...")
            faixa = (int((indice - 1) / total * 100), int(indice / total * 100))
            aquisicoes.append(
                self.adquirir_caminho(
                    caminho_android,
                    pasta_whatsapp / nome,
                    pasta_caso,
                    rotulo=f"whatsapp_{nome}",
                    faixa_progresso=faixa,
                )
            )
            self.progresso(faixa[1])

        self._registrar_datas_dos_backups(pasta_caso, pasta_whatsapp)
        consolidado = self.consolidar_copias([a.copia for a in aquisicoes])
        consolidado.update(self.consolidar_reconciliacao(aquisicoes))
        localizacoes_com_dados = len(consolidado["caminhos_com_dados"])

        self.log(
            "[AVISO] Banco de mensagens ativo (msgstore.db) e chave de criptografia NÃO foram "
            "extraídos por este módulo — ficam na área privada do aplicativo. Apenas mídia e "
            "backups criptografados acessíveis no armazenamento externo foram coletados."
        )

        if localizacoes_com_dados == 0:
            # Nenhum caminho foi copiado por INTEIRO — mas isso não é o mesmo
            # que não ter vindo dado. No A56 (Android 16, 07/11/2026) o
            # aparelho caiu do USB no meio da mídia do WhatsApp: a cópia errou
            # com 2,9 GB já no disco, e ainda assim o módulo concluía "nenhum
            # dado encontrado". Afirmar ausência do que se obteve é a conclusão
            # negativa falsa que esta ferramenta não admite. Só é "nada"
            # quando nada veio.
            if consolidado["bytes_copiados"] > 0:
                detalhes = dict(consolidado, localizacoes_com_dados=0)
                detalhes["copia_incompleta"] = True
                if consolidado["caminhos_negados"]:
                    detalhes["acesso_negado"] = True
                return ResultadoExtracao(
                    sucesso=True,
                    mensagem=(
                        "Cópia PARCIAL do WhatsApp: "
                        f"{consolidado['arquivos_copiados']} arquivo(s), "
                        f"{consolidado['bytes_copiados']} byte(s) obtidos — porém NENHUM "
                        "caminho foi copiado por inteiro (erro do ADB ou o aparelho deixou "
                        "de responder durante a cópia). O que não veio não foi examinado, e "
                        "sua ausência não autoriza concluir que não exista no aparelho."
                    ),
                    caminho_saida=pasta_whatsapp,
                    detalhes=detalhes,
                )
            return ResultadoExtracao(
                sucesso=False,
                mensagem=(
                    "Nenhum dado do WhatsApp foi encontrado nos caminhos conhecidos "
                    "(app pode não estar instalado, ou o Android restringiu o acesso via "
                    "scoped storage)."
                ),
                caminho_saida=pasta_whatsapp,
            )

        # Pasta encontrada e vazia NAO e aquisicao. Contra o moto x4 real, a
        # arvore /sdcard/WhatsApp existia e rendeu 22 arquivos somando ZERO
        # byte: eram todos `.nomedia`, marcadores que dizem ao Android para
        # nao indexar a pasta. O modulo contava "22 arquivo(s)" como dado
        # obtido e declarava sucesso -- com "0 byte(s)" na propria mensagem.
        # Contar arquivo em vez de conteudo faz a estrutura de pastas do
        # aplicativo passar por acervo coletado.
        if consolidado["bytes_copiados"] == 0:
            return ResultadoExtracao(
                sucesso=False,
                mensagem=(
                    f"As pastas do WhatsApp existem no armazenamento externo "
                    f"({consolidado['arquivos_copiados']} arquivo(s) encontrado(s)), porém "
                    "somam ZERO byte: só há marcadores vazios (.nomedia) e pastas sem "
                    "conteúdo. Nenhuma mídia e nenhum backup local foi adquirido. ISSO NÃO "
                    "SIGNIFICA AUSÊNCIA DE MENSAGENS NO APARELHO — o banco ativo exige root, "
                    "e o backup local pode nunca ter sido gerado."
                ),
                caminho_saida=pasta_whatsapp,
                detalhes=dict(consolidado, localizacoes_com_dados=localizacoes_com_dados),
            )

        self.log(
            f"[CONCLUÍDO] Extração best-effort do WhatsApp finalizada! "
            f"({localizacoes_com_dados} localização(ões) com dados)"
        )
        detalhes = dict(consolidado)
        detalhes["localizacoes_com_dados"] = localizacoes_com_dados
        if consolidado["caminhos_negados"]:
            detalhes["acesso_negado"] = True

        return ResultadoExtracao(
            sucesso=True,
            mensagem=(
                "Dados de mídia/backup do WhatsApp extraídos (best effort, sem root): "
                f"{consolidado['arquivos_copiados']} arquivo(s), "
                f"{consolidado['bytes_copiados']} byte(s)."
            ),
            caminho_saida=pasta_whatsapp,
            detalhes=detalhes,
        )
