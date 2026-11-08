"""
Migrado de `6_filesystem_dump.py`: dump de /data/data e /sdcard.

Nota pericial importante sobre este módulo: sem root, `/data/data` é
inacessível ao shell do ADB (uid 2000) em qualquer Android moderno. A
versão anterior deste extrator ignorava o resultado da cópia e retornava
`sucesso=True` incondicionalmente — ou seja, um exame em que **nada** foi
copiado aparecia na interface como "✔ Sucesso". Isso induz a conclusão
negativa falsa mais perigosa possível ("os bancos dos aplicativos foram
examinados e não havia nada"). Agora cada cópia é conferida e o desfecho
reflete o que efetivamente foi adquirido.
"""

from __future__ import annotations

from pathlib import Path

from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

ALVOS_FILESYSTEM = {
    "data_apps": "/data/data",
    "armazenamento_interno": "/sdcard",
}


@registrar_extrator
class FilesystemDumpExtractor(AndroidExtractor):
    id = "android_filesystem_dump"
    nome_exibicao = "Dump do Sistema de Arquivos"
    ordem = 60
    caminhos_de_origem = tuple(ALVOS_FILESYSTEM.values())
    descricao = (
        "Copia recursivamente /data/data (bancos SQLite dos apps) e /sdcard. "
        "Arquivos protegidos serão bloqueados caso o ADB opere em modo comum (User Shell)."
    )

    limitacoes_conhecidas = (
        "Sem privilégio elevado, a área privada dos aplicativos é inacessível: "
        "os bancos de dados dos aplicativos NÃO são obtidos por este módulo.",
        "O que se alcança é o armazenamento compartilhado. Ausência de dado de "
        "aplicativo aqui não é ausência desse dado no aparelho.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta_filesystem = pasta_caso / "filesystem"
        pasta_filesystem.mkdir(parents=True, exist_ok=True)

        self.log(
            "[*] Shell do ADB em modo root: "
            + ("sim" if self.shell_e_root() else "não")
        )
        if not self.shell_e_root():
            self.log(
                "[*] O shell NÃO está em modo root — /data/data provavelmente será recusado "
                "pelo Android. A tentativa será registrada como evidência."
            )

        aquisicoes = []
        total = len(ALVOS_FILESYSTEM)
        self.log("\n[*] Iniciando extração do Filesystem (pode demorar bastante)...")

        for indice, (nome_pasta, caminho_android) in enumerate(ALVOS_FILESYSTEM.items(), 1):
            if self.cancelado:
                return ResultadoExtracao(False, "Extração cancelada pelo usuário.")

            self.log(f"[*] Extraindo diretório: {caminho_android} -> aguarde...")
            faixa = (int((indice - 1) / total * 100), int(indice / total * 100))
            aquisicoes.append(
                self.adquirir_caminho(
                    caminho_android,
                    pasta_filesystem / nome_pasta,
                    pasta_caso,
                    rotulo=f"filesystem_{nome_pasta}",
                    faixa_progresso=faixa,
                )
            )
            self.progresso(faixa[1])

        consolidado = self.consolidar_copias([a.copia for a in aquisicoes])
        detalhes = dict(consolidado)
        detalhes.update(self.consolidar_reconciliacao(aquisicoes))

        perfis = self.contar_perfis_de_usuario()
        if perfis and perfis > 1:
            aviso_perfis = self.restricao_de_multiplos_usuarios(perfis)
            detalhes["perfis_de_usuario"] = perfis
            detalhes["copia_incompleta"] = True
            self.log(f"[RESSALVA] {aviso_perfis}")
            self.registrar_decisao(
                pasta_caso,
                f"Aquisição restrita ao perfil principal, dentre {perfis} perfis existentes.",
                aviso_perfis,
            )

        restricoes = self.consolidar_restricoes(aquisicoes)
        if restricoes:
            detalhes["restricoes_do_sistema"] = restricoes
            detalhes["copia_incompleta"] = True
            self.registrar_decisao(
                pasta_caso,
                "Dados privados de aplicativos não adquiridos por via lógica.",
                restricoes[0],
            )
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

        # Nada copiado é FALHA, não sucesso silencioso.
        if consolidado["arquivos_copiados"] == 0:
            motivo = (
                "acesso negado pelo Android (exige root)"
                if consolidado["caminhos_negados"]
                else "os caminhos não existem ou estão vazios"
            )
            self.log(f"[FALHA] Nenhum arquivo foi copiado do sistema de arquivos — {motivo}.")
            return ResultadoExtracao(
                sucesso=False,
                mensagem=f"Nenhum arquivo copiado do sistema de arquivos: {motivo}.",
                caminho_saida=pasta_filesystem,
                detalhes=detalhes,
            )

        mensagem = (
            f"Filesystem extraído: {consolidado['arquivos_copiados']} arquivo(s), "
            f"{consolidado['bytes_copiados']} byte(s)."
        )
        # A mensagem é o que o examinador lê primeiro. Contra o emulador, em
        # 09/10/2026, `/data/data` inteiro falhou e ela dizia apenas
        # "Filesystem extraído: 7 arquivo(s)" — a ressalva existia em
        # `detalhes`, e a frase que resume o módulo não a carregava.
        if consolidado["caminhos_com_erro"]:
            mensagem += (
                " Ressalva: a cópia de "
                + ", ".join(consolidado["caminhos_com_erro"])
                + " terminou com ERRO do ADB (ver log)."
            )
        if detalhes.get("arquivos_faltantes"):
            mensagem += (
                f" Ressalva: {detalhes['arquivos_faltantes']} arquivo(s) existiam no "
                "aparelho e NÃO foram adquiridos — a cópia é parcial."
            )
        if consolidado["caminhos_negados"]:
            negados = ", ".join(consolidado["caminhos_negados"])
            mensagem += f" Ressalva: acesso negado a {negados} (exige root)."
            self.log(
                f"[RESSALVA] O Android negou acesso a: {negados}. Os bancos privados dos "
                "aplicativos NÃO foram adquiridos — a ausência de dados desses caminhos não "
                "autoriza concluir que o aparelho não os continha."
            )
            self.registrar_decisao(
                pasta_caso,
                f"Aquisição de {negados} não realizada; prosseguiu-se com os caminhos acessíveis.",
                "O Android recusou o acesso ao shell ADB sem privilégio elevado (root). "
                "A recusa foi preservada como evidência da tentativa. Aquisição desses "
                "caminhos exigiria root, cuja obtenção altera o dispositivo e demanda "
                "decisão expressa do examinador.",
            )

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            sucesso=True,
            mensagem=mensagem,
            caminho_saida=pasta_filesystem,
            detalhes=detalhes,
        )
