"""
Índice de arquivos: varre toda a unidade selecionada e gera um manifesto
(CSV) com caminho, tamanho, datas e hash SHA-256 de cada arquivo — sem
copiar nenhum conteúdo. Útil como uma "planta" completa do disco antes de
decidir o que copiar, ou quando o espaço/tempo não permitem uma cópia ou
imagem física completa.

Não requer privilégios especiais: pastas que o usuário atual não
conseguir acessar (ex.: `System Volume Information`, hives em uso) são
puladas e registradas no log, sem interromper a varredura das demais —
por isso a enumeração usa `os.walk(..., onerror=...)` em vez de
`Path.rglob()`, que abortaria no primeiro diretório sem permissão.

A instalação da própria suíte (código-fonte e pasta de saída
`extracoes/`) é excluída da varredura, descoberta dinamicamente a cada
execução (ver `ComputadorExtractor.pastas_a_ignorar`) — sem isso,
periciar a própria unidade onde a suíte está instalada indexaria seu
código e evidências de casos anteriores como se fossem dados do usuário
no disco atual.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from core.base_extractor import ResultadoExtracao
from core.hashing import calcular_sha256
from core.registry import registrar_extrator

from .base import ComputadorExtractor, podar_subpastas_ignoradas

NOME_INDICE = "indice_arquivos.csv"


@registrar_extrator
class IndiceArquivosExtractor(ComputadorExtractor):
    id = "computador_indice_arquivos"
    nome_exibicao = "Índice de Arquivos (sem copiar conteúdo)"
    ordem = 20
    descricao = (
        "Varre toda a unidade e gera um índice (CSV) com caminho, tamanho, datas "
        "e hash SHA-256 de cada arquivo, sem copiar nenhum conteúdo. Pode demorar "
        "bastante em unidades grandes."
    )

    limitacoes_conhecidas = (
        "O índice lista o que o sistema de arquivos expõe pela unidade montada. "
        "Arquivos apagados, espaço não alocado, fluxos alternativos de dados (ADS) "
        "e a tabela de arquivos ($MFT) não são alcançados por esta varredura.",
        "Pastas que o sistema recusar não são enumeradas. Cada recusa é contada e "
        "declarada no resultado — arquivo ausente do índice por recusa nunca é "
        "reportado como arquivo inexistente no disco.",
        "A pasta de instalação do próprio HexisForensics e a raiz das extrações "
        "são excluídas de propósito, para que o código e as evidências de casos "
        "anteriores não sejam indexados como conteúdo do disco periciado.",
        "O índice registra caminho, tamanho, datas e hash. Nenhum conteúdo é "
        "copiado: ele não substitui a cópia lógica nem a imagem do volume.",
        "A leitura é feita na unidade já montada pelo Windows. A ferramenta nada "
        "grava nela, mas não interpõe bloqueador de escrita e nada pode afirmar "
        "sobre o que o sistema operacional tenha escrito ao montá-la.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        raiz_unidade = Path(self.unidade_obrigatoria())
        pasta_destino = pasta_caso / "indice"
        pasta_destino.mkdir(parents=True, exist_ok=True)
        caminho_csv = pasta_destino / NOME_INDICE
        pastas_ignoradas = self.pastas_a_ignorar(pasta_caso)

        self.log(
            f"[*] Enumerando arquivos em '{raiz_unidade}' (isso pode demorar bastante)..."
        )
        arquivos, pastas_negadas = self._enumerar_arquivos(
            raiz_unidade, pastas_ignoradas
        )
        total = len(arquivos)
        self.log(
            f"[*] {total} arquivo(s) encontrado(s). Calculando hashes e gravando o índice..."
        )

        gravados = 0
        pulados = 0
        with open(caminho_csv, "w", newline="", encoding="utf-8") as arquivo_csv:
            escritor = csv.writer(arquivo_csv)
            escritor.writerow(
                ["caminho", "tamanho_bytes", "modificado_em", "criado_em", "sha256"]
            )

            for indice, caminho in enumerate(arquivos, 1):
                if self.cancelado:
                    return ResultadoExtracao(
                        False,
                        f"Extração cancelada pelo usuário ({gravados} de {total} "
                        "arquivo(s) indexado(s)). O índice está INCOMPLETO.",
                        caminho_saida=pasta_destino,
                        detalhes={"incompleta": True, "cancelada": True},
                    )
                try:
                    stat = caminho.stat()
                    hash_arquivo = calcular_sha256(caminho)
                    escritor.writerow(
                        [
                            str(caminho.relative_to(raiz_unidade)),
                            stat.st_size,
                            datetime.fromtimestamp(stat.st_mtime).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            datetime.fromtimestamp(stat.st_ctime).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            hash_arquivo,
                        ]
                    )
                    gravados += 1
                except OSError as exc:
                    pulados += 1
                    self.log(f"    [!] Pulado (sem acesso): {caminho} — {exc}")

                if indice % 200 == 0 or indice == total:
                    self.log(f"  -> {indice}/{total} processado(s)")
                if total:
                    self.progresso(int(indice / total * 100))

        recusas = pulados + pastas_negadas
        detalhes: dict = {
            "arquivos_indexados": gravados,
            "arquivos_sem_acesso": pulados,
            "pastas_sem_acesso": pastas_negadas,
        }

        # Índice vazio deixa de ser sucesso. A distinção entre as duas
        # causas é o ponto: unidade sem arquivo nenhum é conclusão sobre o
        # disco; unidade inteiramente recusada é ausência de conclusão. A
        # versão anterior devolvia sucesso nos dois casos, com a mesma
        # frase, e um disco cheio e inacessível virava laudo dizendo que
        # não havia arquivos.
        if gravados == 0:
            if recusas:
                detalhes["acesso_negado"] = recusas
                mensagem = (
                    f"Nenhum arquivo pôde ser indexado: {recusas} recusa(s) de acesso "
                    "do sistema. O índice está vazio por impedimento, e nada se pode "
                    "afirmar sobre o conteúdo da unidade."
                )
            else:
                mensagem = (
                    "Nenhum arquivo foi encontrado na unidade selecionada, e nenhum "
                    "acesso foi negado. O índice está vazio porque a unidade não tem "
                    "arquivos ao alcance desta varredura."
                )
            self.log(f"[FALHA] {mensagem}")
            return ResultadoExtracao(
                False, mensagem, caminho_saida=caminho_csv, detalhes=detalhes
            )

        mensagem = f"Índice gerado com {gravados} arquivo(s)."
        if recusas:
            detalhes["acesso_negado"] = recusas
            mensagem += (
                f" RESSALVA: {pulados} arquivo(s) e {pastas_negadas} pasta(s) não "
                "puderam ser lidos por recusa do sistema; o que ficou de fora do "
                "índice por esse motivo não é ausência no disco."
            )

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            True, mensagem, caminho_saida=caminho_csv, detalhes=detalhes
        )

    def _enumerar_arquivos(
        self, raiz_unidade: Path, pastas_ignoradas: List[Path]
    ) -> Tuple[List[Path], int]:
        """
        Enumera os arquivos da unidade e devolve `(arquivos, pastas_negadas)`.

        A contagem de pastas recusadas sai junto porque uma pasta que não
        pôde sequer ser listada não produz nenhuma tentativa de leitura de
        arquivo — ela sumiria do resultado sem deixar rastro, e o índice
        pareceria completo.
        """
        arquivos: List[Path] = []
        pastas_negadas = 0

        def _ao_erro(erro: OSError) -> None:
            nonlocal pastas_negadas
            pastas_negadas += 1
            self.log(f"    [!] Pasta sem acesso: {erro.filename} — {erro}")

        for pasta_atual, subpastas, nomes_arquivos in os.walk(
            raiz_unidade, onerror=_ao_erro, followlinks=False
        ):
            if self.cancelado:
                break
            excluidas = podar_subpastas_ignoradas(
                pasta_atual, subpastas, pastas_ignoradas
            )
            for excluida in excluidas:
                self.log(
                    f"    [!] Pasta da própria suíte excluída do índice: {excluida}"
                )
            for nome in nomes_arquivos:
                arquivos.append(Path(pasta_atual) / nome)

        return arquivos, pastas_negadas
