"""
Migrado de `2_backup_logico.py`: mídias/downloads + metadados do sistema.

Como no dump de filesystem, a versão anterior ignorava o resultado de cada
`adb pull` e declarava sucesso incondicional. Agora cada pasta de mídia
tem seu desfecho conferido e consolidado, e a mensagem final informa
quantos arquivos foram efetivamente adquiridos — número que o relatório
precisa para sustentar completude.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

PASTAS_MIDIA = {
    "Camera": "/sdcard/DCIM",
    "Downloads": "/sdcard/Download",
    "Pictures": "/sdcard/Pictures",
    "Movies": "/sdcard/Movies",
    "Audio": "/sdcard/Music",
    # Area de dados dos aplicativos no armazenamento COMPARTILHADO -- nao
    # confundir com `/data/data`, que e privada e exige privilegio elevado.
    # E onde clientes de e-mail e mensageiros deixam anexo baixado, e ficava
    # inteiramente de fora deste modulo: quem rodasse so o backup logico
    # perdia essa area sem nenhum aviso.
    #
    # A partir do Android 11 o proprio sistema restringe a leitura daqui, e
    # a recusa aparece contada como qualquer outra -- que e o que distingue
    # "o sistema nao deixou" de "nao havia nada".
    "DadosDeAplicativos": "/sdcard/Android/data",
}


@registrar_extrator
class BackupLogicoExtractor(AndroidExtractor):
    id = "android_backup_logico"
    nome_exibicao = "Backup Lógico (Mídias e Metadados)"
    ordem = 20
    caminhos_de_origem = tuple(PASTAS_MIDIA.values())
    descricao = (
        "Extrai as pastas DCIM, Download, Pictures, Movies, Music e a área de dados "
        "de aplicativos em armazenamento compartilhado, via 'adb pull', "
        "além de metadados do sistema (getprop) e da lista de pacotes instalados."
    )

    limitacoes_conhecidas = (
        "Alcança o armazenamento compartilhado — mídias, downloads e metadados "
        "do sistema. A área privada dos aplicativos exige privilégio elevado e "
        "fica fora deste módulo.",
        "Anexo de e-mail só está aqui se tiver sido baixado para o armazenamento "
        "compartilhado, e chega sem procedência: nada no material indica de qual "
        "mensagem ele veio, de quem ou quando. Essa vinculação depende do banco "
        "do aplicativo de e-mail, que está na área privada.",
        "A partir do Android 11, o sistema restringe a leitura de "
        "'/sdcard/Android/data' mesmo em armazenamento compartilhado. A recusa é "
        "contada e declarada — não é o mesmo que a pasta estar vazia.",
        "Copia o que está presente. Arquivo apagado pelo usuário não é "
        "recuperado aqui.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta_metadados = pasta_caso / "system_info"
        pasta_midia = pasta_caso / "media"
        pasta_metadados.mkdir(parents=True, exist_ok=True)
        pasta_midia.mkdir(parents=True, exist_ok=True)

        self.log("[*] Coletando metadados e propriedades do sistema...")
        propriedades = self.adb.executar(["shell", "getprop"])
        (pasta_metadados / "getprop.txt").write_text(propriedades, encoding="utf-8")

        self.log("[*] Coletando informações de pacotes e apps instalados...")
        apps = self.adb.executar(["shell", "pm", "list", "packages", "-f"])
        (pasta_metadados / "apps_instalados.txt").write_text(apps, encoding="utf-8")

        metadados_ok = bool(propriedades.strip()) and bool(apps.strip())
        if not metadados_ok:
            self.log("[RESSALVA] Metadados do sistema vieram vazios — verifique a conexão ADB.")
        self.progresso(15)

        aquisicoes = []
        total = len(PASTAS_MIDIA)
        self.log("\n[*] Iniciando a cópia de mídias e arquivos (isso pode demorar)...")

        for indice, (nome, caminho_android) in enumerate(PASTAS_MIDIA.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, "Extração cancelada pelo usuário.")

            self.log(f"[*] Extraindo {nome} ({caminho_android})...")
            # Faixa que este caminho ocupa na barra: o progresso passa a
            # refletir a transferencia, e nao a contagem de pastas.
            faixa = (15 + int((indice - 1) / total * 85), 15 + int(indice / total * 85))
            aquisicoes.append(
                self.adquirir_caminho(
                    caminho_android,
                    pasta_midia / nome,
                    pasta_caso,
                    rotulo=f"midia_{nome}",
                    faixa_progresso=faixa,
                )
            )
            self.progresso(faixa[1])

        consolidado = self.consolidar_copias([a.copia for a in aquisicoes])
        detalhes = dict(consolidado)
        detalhes.update(self.consolidar_reconciliacao(aquisicoes))
        detalhes["metadados_coletados"] = metadados_ok
        if consolidado["caminhos_negados"]:
            detalhes["acesso_negado"] = True
        if consolidado.get("caminhos_interrompidos"):
            detalhes["copia_incompleta"] = True
            interrompidos = ", ".join(consolidado["caminhos_interrompidos"])
            self.log(
                f"[RESSALVA] Cópia interrompida antes do fim em: {interrompidos}. "
                "O material adquirido é parcial."
            )
        if detalhes.get("arquivos_faltantes"):
            # Arquivo que existia na origem e não chegou ao destino é
            # ressalva obrigatória: sem isso o exame concluiria completude
            # sobre uma cópia comprovadamente parcial.
            detalhes["copia_incompleta"] = True

        # Nenhuma mídia E nenhum metadado = nada foi adquirido.
        if consolidado["arquivos_copiados"] == 0 and not metadados_ok:
            self.log("[FALHA] Nem metadados nem mídias foram adquiridos.")
            return ResultadoExtracao(
                sucesso=False,
                mensagem="Nenhum dado foi adquirido: metadados vazios e nenhuma mídia copiada.",
                caminho_saida=pasta_caso,
                detalhes=detalhes,
            )

        mensagem = (
            f"Backup lógico concluído: {consolidado['arquivos_copiados']} arquivo(s) de mídia, "
            f"{consolidado['bytes_copiados']} byte(s)."
        )

        # Metadados vieram, mas nenhuma mídia: é sucesso parcial, e precisa
        # ficar explícito — não se pode concluir que o aparelho não tinha mídia.
        if consolidado["arquivos_copiados"] == 0:
            detalhes["copia_incompleta"] = True
            if consolidado["caminhos_inexistentes"]:
                motivo = (
                    "as seguintes pastas não existem no aparelho: "
                    + ", ".join(consolidado["caminhos_inexistentes"])
                )
            else:
                motivo = "as pastas existem no aparelho, porém estão vazias"
            mensagem = (
                "Metadados do sistema coletados, porém NENHUM arquivo de mídia foi copiado — "
                f"{motivo}."
            )
            self.log(f"[RESSALVA] {mensagem}")

        if consolidado["caminhos_negados"]:
            negados = ", ".join(consolidado["caminhos_negados"])
            mensagem += f" Ressalva: acesso negado a {negados}."
            self.log(f"[RESSALVA] O Android negou acesso a: {negados}.")

        if consolidado["caminhos_com_erro"]:
            detalhes["copia_incompleta"] = True
            com_erro = ", ".join(consolidado["caminhos_com_erro"])
            mensagem += f" Ressalva: erro do ADB em {com_erro}."
            self.log(f"[RESSALVA] Erro do ADB ao copiar: {com_erro}.")

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            sucesso=True,
            mensagem=mensagem,
            caminho_saida=pasta_caso,
            detalhes=detalhes,
        )
