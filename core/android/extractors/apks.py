"""
Cópia dos APKs dos aplicativos instalados pelo usuário.

A lista de pacotes instalados diz *que* um aplicativo existe no aparelho;
o APK diz **qual** aplicativo é. A diferença importa em duas situações
frequentes: aplicativo modificado (um mensageiro adulterado, um aplicativo
de fachada com nome de outro) e aplicativo malicioso, que precisa ser
analisado, não apenas nomeado.

Cada APK recebe seu SHA-256 no momento da cópia. Isso permite tanto
comparar o binário com a versão oficial da loja quanto submetê-lo a
análise posterior sem reabrir o aparelho.

Só são copiados os pacotes instalados pelo usuário (`pm list packages -3`);
aplicativos de sistema ficam de fora por serem centenas e virem da imagem
de fábrica.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

from core.base_extractor import ResultadoExtracao
from core.hashing import calcular_sha256
from core.registry import registrar_extrator

from .base import AndroidExtractor

PADRAO_PACOTE = re.compile(r"^package:(?P<caminho>\S+\.apk)=(?P<pacote>[\w.]+)$")


@registrar_extrator
class ApksExtractor(AndroidExtractor):
    id = "android_apks"
    nome_exibicao = "APKs dos Aplicativos Instalados"
    ordem = 65
    descricao = (
        "Copia o arquivo .apk de cada aplicativo instalado pelo usuário e calcula seu "
        "SHA-256, permitindo identificar aplicativo adulterado ou malicioso e submetê-lo "
        "a análise posterior. Aplicativos de sistema não são copiados. "
        "ATENÇÃO: pode levar vários minutos e ocupar espaço considerável, conforme a "
        "quantidade de aplicativos instalados."
    )

    limitacoes_conhecidas = (
        "Só são copiados os aplicativos instalados pelo usuário; os que vieram "
        "na imagem de fábrica do aparelho ficam de fora.",
        "Aplicativo já desinstalado não deixa APK a copiar — sua ausência aqui "
        "não significa que nunca esteve instalado no aparelho.",
        "O módulo preserva o binário, não o analisa. Afirmar que um aplicativo "
        "foi adulterado exige comparação posterior com a versão oficial.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta = pasta_caso / "apks"
        pasta.mkdir(parents=True, exist_ok=True)

        pacotes = self._listar_pacotes_do_usuario()

        if pacotes is None:
            self.log("[FALHA] A consulta de aplicativos instalados não pôde ser realizada.")
            return ResultadoExtracao(
                False,
                "Não foi possível consultar os aplicativos instalados: o comando falhou no "
                "aparelho. Nada se pode afirmar sobre quais aplicativos existiam.",
                caminho_saida=pasta,
            )

        # Consulta respondida, lista vazia: é resposta, não falha. Dizer que
        # "o aparelho não respondeu" seria afirmar o que não ocorreu — e a
        # conclusão que se tira de cada caso é oposta.
        if not pacotes:
            self.log("[*] O aparelho respondeu: nenhum aplicativo instalado pelo usuário.")
            self._gravar_inventario(pasta, {}, {}, [])
            return ResultadoExtracao(
                True,
                "O aparelho respondeu à consulta e não há aplicativo instalado pelo usuário. "
                "Nenhum APK a copiar — o que é diferente de não ter sido possível consultar.",
                caminho_saida=pasta,
                detalhes={"aplicativos_de_usuario": 0, "apks_copiados": 0, "pacotes_sem_apk": []},
            )

        self.log(f"[*] {len(pacotes)} aplicativo(s) instalado(s) pelo usuário. Copiando APKs...")

        copiados: Dict[str, str] = {}
        falhos = []
        total = len(pacotes)

        for indice, (pacote, caminho_remoto) in enumerate(sorted(pacotes.items()), 1):
            if self.cancelado:
                self.log("[*] Cópia de APKs cancelada pelo examinador.")
                break

            destino = pasta / pacote
            resultado = self.copiar_caminho(caminho_remoto, destino)

            arquivos = [c for c in destino.rglob("*.apk") if c.is_file()]
            if resultado.sucesso and arquivos:
                # Vários APKs por pacote são normais (split APKs); todos entram.
                for arquivo in arquivos:
                    copiados[f"{pacote}/{arquivo.name}"] = calcular_sha256(arquivo)
            else:
                falhos.append(pacote)

            self.progresso(int(indice / total * 100))

        self._gravar_inventario(pasta, pacotes, copiados, falhos)

        detalhes = {
            "aplicativos_de_usuario": len(pacotes),
            "apks_copiados": len(copiados),
            "pacotes_sem_apk": falhos,
        }

        if not copiados:
            self.log("[FALHA] Nenhum APK pôde ser copiado.")
            return ResultadoExtracao(
                False,
                f"Nenhum dos {len(pacotes)} aplicativos teve o APK copiado.",
                caminho_saida=pasta,
                detalhes=detalhes,
            )

        mensagem = f"{len(copiados)} APK(s) copiados de {len(pacotes)} aplicativo(s) de usuário."
        if falhos:
            # Aplicativo listado cujo APK não veio é lacuna que o exame
            # precisa enxergar antes de concluir sobre o conjunto instalado.
            detalhes["copia_incompleta"] = True
            mensagem += f" Ressalva: {len(falhos)} sem APK copiado."
            self.log(f"[RESSALVA] Sem APK copiado: {', '.join(falhos[:10])}")

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    # ------------------------------------------------------------------
    def _listar_pacotes_do_usuario(self) -> Optional[Dict[str, str]]:
        """
        Mapeia pacote -> caminho do APK no aparelho, só para apps do usuário.

        Devolve `None` quando a consulta **falhou**, e um dicionário vazio
        quando ela **respondeu que não há aplicativo de usuário**. As duas
        colapsavam em `{}`, e o módulo relatava "o aparelho não respondeu à
        consulta" nos dois casos — afirmação falsa na segunda, e da mesma
        família de defeito que esta suíte persegue. Apareceu na primeira
        execução contra um Android 13 recém-instalado, sem app nenhum.
        """
        resultado = self.adb.executar_detalhado(
            ["shell", "pm", "list", "packages", "-3", "-f"], timeout=120
        )
        if not resultado.sucesso:
            self.log(f"    [ERRO] Falha ao listar pacotes: {resultado.motivo_falha}")
            return None

        pacotes: Dict[str, str] = {}
        for linha in resultado.stdout.splitlines():
            correspondencia = PADRAO_PACOTE.match(linha.strip())
            if correspondencia:
                pacotes[correspondencia.group("pacote")] = correspondencia.group("caminho")
        return pacotes

    @staticmethod
    def _gravar_inventario(pasta: Path, pacotes, copiados, falhos) -> None:
        linhas = [
            "=" * 74,
            "INVENTÁRIO DE APLICATIVOS INSTALADOS PELO USUÁRIO".center(74),
            "=" * 74,
            "",
            f"Aplicativos de usuário localizados: {len(pacotes)}",
            f"APKs efetivamente copiados:         {len(copiados)}",
            f"Pacotes sem APK copiado:            {len(falhos)}",
            "",
            "-" * 74,
            "SHA-256 DE CADA APK COPIADO",
            "-" * 74,
        ]
        linhas += [f"{valor} *{nome}" for nome, valor in sorted(copiados.items())]

        if falhos:
            linhas += ["", "-" * 74, "PACOTES INSTALADOS CUJO APK NÃO PÔDE SER COPIADO", "-" * 74]
            linhas += [f"  - {pacote}  ({pacotes.get(pacote, 'caminho desconhecido')})" for pacote in falhos]

        linhas += [
            "",
            "=" * 74,
            "NOTA: aplicativos de sistema não são copiados por este módulo — vêm da",
            "imagem de fábrica e somam centenas de pacotes. Se a análise exigir algum",
            "deles, o caminho consta em artefatos_sistema/pacotes_detalhado.txt.",
            "=" * 74,
        ]
        (pasta / "INVENTARIO_APKS.txt").write_text("\n".join(linhas), encoding="utf-8")
