"""
Extração lógica: copia pastas-chave do usuário (Documentos, Área de
Trabalho, Downloads, Imagens) da unidade selecionada, sem exigir
privilégios especiais — funciona com o que o usuário Windows atual já
consegue ler.

Como um disco pericial não segue necessariamente a estrutura padrão de um
perfil do Windows (pode ser um HD externo com uma cópia solta das pastas,
ou um disco que é a própria unidade de sistema com vários perfis em
`Users\\<usuário>\\...`), a busca por pastas-alvo é feita em dois níveis:
na raiz da unidade e dentro de cada subpasta de `Users\\`/`Usuários\\`,
cobrindo tanto discos "soltos" quanto discos de sistema.

Três armadilhas comuns de pasta de usuário real, tratadas explicitamente:
    - A própria instalação da suíte (código-fonte e/ou pasta de saída
      `extracoes/`) pode estar dentro da árvore sendo copiada — ao testar
      periciando a própria unidade onde a suíte roda (sem um disco/
      pendrive externo à mão), por exemplo, "Desktop" pode conter a pasta
      do projeto inteira. Sem excluir essa pasta da varredura, o extrator
      copiaria seu próprio código e/ou resultado de volta para dentro de
      si mesmo, num loop que cresce indefinidamente até parecer travado
      (ou encher o disco). A localização da suíte é descoberta
      *dinamicamente* a cada execução — nunca um caminho fixo — via
      `ComputadorExtractor.pastas_a_ignorar`/`raiz_instalacao_suite()`.
    - Links simbólicos/junções do Windows podem formar ciclos (uma pasta
      apontando de volta para um ancestral) — a cópia usa
      `os.walk(..., followlinks=False)`, que nunca desce dentro de um
      link/junção, evitando recursão infinita.
    - "Arquivos sob demanda" do OneDrive/Google Drive (Files On-Demand) —
      muito comuns justamente em Documentos/Imagens, que o Windows
      moderno costuma redirecionar para a nuvem por padrão — aparentam
      ter conteúdo, mas os bytes reais só existem no servidor. Tentar
      copiar um desses trava esperando o Windows baixá-lo (minutos, ou
      para sempre sem internet). São detectados pelo atributo
      `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` e pulados (registrado no
      log e no resultado), em vez de travar a extração inteira.

O progresso também é reportado por arquivo copiado (não mais uma vez por
pasta) — com poucas pastas-alvo e uma delas muito grande, uma extração
saudável podia passar minutos parada num mesmo percentual, indistinguível
de uma trava real.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Tuple

from core.base_extractor import ResultadoExtracao
from core.hashing import gerar_manifesto
from core.registry import registrar_extrator

from .base import ComputadorExtractor, podar_subpastas_ignoradas

# Nomes de pasta procurados (cobre Windows em inglês e em português — o
# exame pode envolver qualquer um dos dois idiomas de instalação).
NOMES_PASTAS_ALVO = {
    "Documents": ("Documents", "Documentos"),
    "Desktop": ("Desktop", "Área de Trabalho"),
    "Downloads": ("Downloads", "Download"),
    "Pictures": ("Pictures", "Imagens"),
}

# Pastas onde procurar perfis de usuário, um nível abaixo da raiz da unidade.
NOMES_PASTA_USUARIOS = ("Users", "Usuários", "Usuarios")

# Atributo de arquivo do Windows que marca um "placeholder" de sincronização
# na nuvem (OneDrive/Google Drive Files On-Demand): o arquivo aparenta ter
# conteúdo, mas os bytes reais só existem no servidor — acessá-lo dispara um
# download bloqueante do Windows. Valor documentado pela Microsoft
# (winnt.h); replicado aqui porque nem toda versão do Python expõe
# `stat.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` (mesmo padrão já usado para
# constantes do Windows em `disk_client.py`).
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

# Quantidade de arquivos copiados entre cada linha de progresso no log —
# sem isso, uma pasta grande fica minutos sem nenhuma linha nova no
# console, o que parece uma trava mesmo quando está tudo funcionando.
INTERVALO_LOG_PROGRESSO = 25


def _eh_arquivo_sob_demanda(caminho: Path) -> bool:
    """Detecta um placeholder de nuvem (OneDrive/Google Drive) ainda não baixado para o disco."""
    try:
        atributos = caminho.stat().st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    return bool(atributos & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)


@registrar_extrator
class CopiaLogicaExtractor(ComputadorExtractor):
    id = "computador_copia_logica"
    nome_exibicao = "Cópia Lógica (Pastas do Usuário)"
    ordem = 10
    descricao = (
        "Copia as pastas-chave do usuário (Documentos, Área de Trabalho, Downloads, "
        "Imagens) encontradas na unidade selecionada, com hash SHA-256 por arquivo "
        "para a cadeia de custódia. Não requer privilégios especiais."
    )

    limitacoes_conhecidas = (
        "Copia apenas as pastas de usuário reconhecidas por nome — Documentos, Área "
        "de Trabalho, Downloads e Imagens — na raiz da unidade e em cada perfil de "
        "'Users'. Nada fora dessas pastas é copiado, e o material do usuário guardado "
        "em outro lugar do disco não é alcançado.",
        "Dados de aplicativos ('AppData'), onde ficam mensageiros, navegadores e "
        "arquivos temporários, não entram nesta cópia.",
        "Arquivo que exista somente na nuvem e não tenha sido baixado para o disco é "
        "pulado, e contado como tal: o conteúdo não está no computador para ser "
        "copiado, e a ferramenta não o busca no serviço remoto.",
        "Recusa de leitura de arquivo ou de pasta é contada e declarada. O que faltar "
        "na cópia por esse motivo nunca é reportado como ausência no disco.",
        "A cópia preserva os arquivos existentes no sistema de arquivos. Arquivos "
        "apagados e espaço não alocado exigem a imagem do volume.",
        "A leitura é feita na unidade já montada pelo Windows. A ferramenta nada "
        "grava nela, mas não interpõe bloqueador de escrita e nada pode afirmar "
        "sobre o que o sistema operacional tenha escrito ao montá-la.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        raiz_unidade = Path(self.unidade_obrigatoria())
        pasta_destino = pasta_caso / "copia_logica"
        pasta_destino.mkdir(parents=True, exist_ok=True)
        pastas_ignoradas = self.pastas_a_ignorar(pasta_caso)

        self.log(f"[*] Procurando pastas de usuário em '{raiz_unidade}'...")
        candidatos = self._localizar_pastas_alvo(raiz_unidade)

        if not candidatos:
            mensagem = (
                "Nenhuma pasta de usuário reconhecida (Documentos/Desktop/Downloads/"
                "Imagens) foi encontrada na unidade selecionada."
            )
            self.log(f"[!] {mensagem}")
            return ResultadoExtracao(False, mensagem, caminho_saida=pasta_destino)

        # O que a copia NAO vai levar, levantado antes de comecar. Um
        # pendrive guarda o material na raiz, nao em pasta de usuario: sem
        # esta contagem o modulo devolve "concluida (6 arquivos)" tendo
        # ignorado o arquivo que o examinador mais esperava encontrar.
        fora_do_alcance = self._itens_da_raiz_fora_da_copia(
            raiz_unidade, candidatos, pastas_ignoradas
        )
        if fora_do_alcance:
            self.log(
                f"[!] {len(fora_do_alcance)} item(ns) na raiz da unidade estao FORA "
                "do alcance deste modulo (ele so copia pastas de usuario)."
            )

        self.log(
            "[*] Contando arquivos a copiar (pode demorar um pouco em pastas grandes)..."
        )
        self._total_arquivos = sum(
            self._contar_arquivos(origem, pastas_ignoradas) for _, origem in candidatos
        )
        self._arquivos_processados = 0
        self.log(f"[*] {self._total_arquivos} arquivo(s) a copiar.")

        arquivos_copiados = 0
        arquivos_pulados_nuvem = 0
        arquivos_negados = 0
        pastas_com_falha = []
        # Origem e destino de cada pasta, para o laudo. O log guarda esse
        # par, mas o log nao e o resultado: quem le a aquisicao meses
        # depois precisa saber de onde veio cada pasta copiada sem ter de
        # reconstituir isso a partir das linhas de execucao.
        pastas_copiadas = []
        for rotulo, origem in candidatos:
            if self.cancelado:
                return ResultadoExtracao(
                    False,
                    f"Extração cancelada pelo usuário ({arquivos_copiados} arquivo(s) "
                    "copiado(s)). A cópia está INCOMPLETA.",
                    caminho_saida=pasta_destino,
                    detalhes={"incompleta": True, "cancelada": True},
                )

            destino = pasta_destino / rotulo
            self.log(
                f" -> Copiando '{origem}' -> '{destino.relative_to(pasta_caso)}'..."
            )
            try:
                copiados, pulados, negados = self._copiar_pasta(
                    origem, destino, pastas_ignoradas
                )
                arquivos_copiados += copiados
                arquivos_pulados_nuvem += pulados
                arquivos_negados += negados
                pastas_copiadas.append(
                    {
                        "origem": str(origem),
                        "destino": str(destino.relative_to(pasta_caso)),
                        "arquivos": copiados,
                    }
                )
            except OSError as exc:
                # Uma pasta-alvo inteira caiu. Antes isto era só uma linha
                # de log: se Documentos falhasse e Downloads copiasse, o
                # resultado saía como sucesso limpo, sem nada indicar que
                # uma das pastas do usuário ficara integralmente de fora.
                # O caminho de origem, sempre: e o que identifica a pasta
                # no disco periciado.
                pastas_com_falha.append(str(origem))
                self.log(f"    [!] Falha ao copiar '{origem}': {exc}")

        self.log("\n[*] Gerando manifesto de hashes SHA-256 da cópia...")
        gerar_manifesto(
            pasta_destino,
            log_callback=self.log,
            progress_callback=lambda p: self.progresso(80 + int(p * 0.2)),
        )

        detalhes: dict = {
            "arquivos_copiados": arquivos_copiados,
            "arquivos_sem_acesso": arquivos_negados,
            "pastas_copiadas": pastas_copiadas,
        }
        if arquivos_pulados_nuvem:
            detalhes["arquivos_pulados_nuvem"] = arquivos_pulados_nuvem
        if arquivos_negados:
            detalhes["acesso_negado"] = arquivos_negados
        if fora_do_alcance:
            detalhes["itens_fora_do_alcance"] = (
                f"{len(fora_do_alcance)} item(ns) na raiz da unidade não entram "
                "nesta cópia, que só alcança pastas de usuário reconhecidas: "
                + ", ".join(fora_do_alcance)
            )
        if pastas_com_falha:
            detalhes["copia_incompleta"] = (
                "Pasta(s) que não puderam ser copiadas: " + ", ".join(pastas_com_falha)
            )

        if arquivos_copiados == 0:
            return ResultadoExtracao(
                False,
                f"Pastas encontradas, porém nenhum arquivo pôde ser copiado "
                f"({arquivos_negados} recusa(s) de acesso; ver log de erros).",
                caminho_saida=pasta_destino,
                detalhes=detalhes,
            )

        mensagem = f"Cópia lógica concluída ({arquivos_copiados} arquivo(s))."
        if arquivos_pulados_nuvem:
            mensagem += (
                f" {arquivos_pulados_nuvem} arquivo(s) sob demanda na nuvem pulado(s): "
                "o conteúdo não estava fisicamente no disco."
            )
        if arquivos_negados:
            mensagem += (
                f" RESSALVA: {arquivos_negados} item(ns) não puderam ser lidos por "
                "recusa do sistema; o que faltar na cópia por esse motivo não é "
                "ausência no disco."
            )
        if fora_do_alcance:
            mensagem += (
                f" RESSALVA: {len(fora_do_alcance)} item(ns) na raiz da unidade "
                "ficaram fora — este módulo só copia pastas de usuário reconhecidas. "
                "Numa mídia removível o material costuma estar justamente na raiz; "
                "para alcançá-lo, use o Índice de Arquivos ou a Imagem do Volume."
            )
        if pastas_com_falha:
            mensagem += (
                " RESSALVA: pasta(s) integralmente fora da cópia — "
                + ", ".join(pastas_com_falha)
                + "."
            )

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            True, mensagem, caminho_saida=pasta_destino, detalhes=detalhes
        )

    def _itens_da_raiz_fora_da_copia(
        self,
        raiz_unidade: Path,
        candidatos: List[Tuple[str, Path]],
        pastas_ignoradas: List[Path],
    ) -> List[str]:
        """
        Nomes dos itens na raiz da unidade que esta cópia não vai levar.

        Não desce nas subpastas: o custo tem de ser o de listar uma pasta,
        não o de varrer o disco — quem varre é o Índice de Arquivos. O
        objetivo é dar a ORDEM DE GRANDEZA do que ficou fora, não o
        inventário: dizer "6 arquivos copiados" sem dizer "e 2 itens na
        raiz não" deixa a conclusão parecendo completa.

        A pasta de perfis ('Users') não entra na conta: ela é percorrida
        por `_localizar_pastas_alvo`.
        """
        cobertos = {origem.resolve() for _, origem in candidatos}
        ignoradas = {p.resolve() for p in pastas_ignoradas}
        nomes = []
        try:
            entradas = sorted(raiz_unidade.iterdir(), key=lambda e: e.name.lower())
        except OSError:
            # Nem a raiz pôde ser listada. Não é este o módulo que
            # diagnostica isso, e inventar uma contagem seria pior que
            # não ter nenhuma.
            return []

        for entrada in entradas:
            if entrada.name in NOMES_PASTA_USUARIOS:
                continue
            try:
                resolvido = entrada.resolve()
            except OSError:
                resolvido = entrada
            if resolvido in cobertos or resolvido in ignoradas:
                continue
            nomes.append(entrada.name + ("\\" if entrada.is_dir() else ""))

        return nomes

    def _localizar_pastas_alvo(self, raiz_unidade: Path) -> List[Tuple[str, Path]]:
        """
        Procura, na raiz da unidade e dentro de cada perfil em `Users\\`,
        as pastas cujo nome bata com alguma variante de `NOMES_PASTAS_ALVO`.
        Devolve `(nome_destino, caminho_origem)`.

        Dois defeitos que a primeira execução contra pendrive real revelou,
        e que a leitura do código não tinha pegado:

        1. **Só a primeira variante era copiada.** O laço parava no
           primeiro nome que existisse, e um disco com `Documents` E
           `Documentos` — os dois existem, é comum em máquina que trocou de
           idioma ou teve dois donos — perdia a segunda pasta inteira, sem
           uma linha no resultado. Agora toda variante existente entra.

        2. **O destino renomeava a evidência.** A pasta ia para o rótulo
           interno, em inglês: `D:\\Documentos` era gravada como
           `copia_logica/Documents`, um caminho que não existe no disco
           periciado. Na mesma aquisição, o índice listava `Documentos\\` e
           a cópia dizia `Documents\\` — dois artefatos discordando sobre o
           nome da mesma pasta. O destino passa a ser o nome real, lido do
           disco com `resolve()`, que no Windows devolve a grafia
           verdadeira (`Path("d:/documentos").resolve().name` é
           `Documentos`).

        A deduplicação por caminho resolvido existe porque o Windows não
        diferencia maiúsculas: duas variantes da lista podem apontar para a
        mesma pasta, e copiar duas vezes duplicaria evidência.
        """
        encontradas: List[Tuple[str, Path]] = []
        ja_vistas = set()

        raizes_candidatas: List[Tuple[str, Path]] = [("", raiz_unidade)]
        for nome_pasta_usuarios in NOMES_PASTA_USUARIOS:
            pasta_usuarios = raiz_unidade / nome_pasta_usuarios
            if pasta_usuarios.is_dir():
                try:
                    for perfil in pasta_usuarios.iterdir():
                        if perfil.is_dir():
                            raizes_candidatas.append((f"{perfil.name}_", perfil))
                except OSError:
                    continue

        for prefixo, raiz in raizes_candidatas:
            for variantes in NOMES_PASTAS_ALVO.values():
                for variante in variantes:
                    caminho = raiz / variante
                    if not caminho.is_dir():
                        continue
                    try:
                        resolvido = caminho.resolve()
                    except OSError:
                        resolvido = caminho
                    if resolvido in ja_vistas:
                        continue
                    ja_vistas.add(resolvido)
                    encontradas.append((f"{prefixo}{resolvido.name}", caminho))

        return encontradas

    def _contar_arquivos(self, origem: Path, pastas_ignoradas: List[Path]) -> int:
        """Pré-conta os arquivos de `origem` (exceto `pastas_ignoradas`), para o progresso ser proporcional ao total real."""
        total = 0
        for pasta_atual, subpastas, nomes_arquivos in os.walk(
            origem, onerror=lambda _erro: None, followlinks=False
        ):
            podar_subpastas_ignoradas(pasta_atual, subpastas, pastas_ignoradas)
            total += len(nomes_arquivos)
        return total

    def _copiar_pasta(
        self, origem: Path, destino: Path, pastas_ignoradas: List[Path]
    ) -> Tuple[int, int, int]:
        """
        Copia `origem` recursivamente para `destino`, excluindo
        `pastas_ignoradas` (a instalação/saída da própria suíte — ver
        `ComputadorExtractor.pastas_a_ignorar`). Devolve
        `(copiados, pulados_por_estarem_só_na_nuvem, negados_por_recusa)`.

        Usa `os.walk(..., followlinks=False)` em vez de `Path.rglob()`:
        nunca desce dentro de um link simbólico/junção (evita recursão
        infinita em ciclos), e uma subpasta sem permissão é pulada sem
        abortar a cópia inteira (mesma abordagem de `file_index.py`).
        """
        contador = 0
        pulados_nuvem = 0
        negados = 0

        def _ao_erro(erro: OSError) -> None:
            # Pasta que nao pode ser listada nao gera tentativa de copia
            # nenhuma: sem contar aqui, ela sumiria da cópia sem deixar
            # rastro no resultado, e a cópia pareceria completa.
            nonlocal negados
            negados += 1
            self.log(f"    [!] Pasta sem acesso: {erro.filename} — {erro}")

        for pasta_atual, subpastas, nomes_arquivos in os.walk(
            origem, onerror=_ao_erro, followlinks=False
        ):
            excluidas = podar_subpastas_ignoradas(
                pasta_atual, subpastas, pastas_ignoradas
            )
            for excluida in excluidas:
                self.log(
                    f"    [!] Pasta da própria suíte excluída da cópia: {excluida}"
                )

            pasta_atual_path = Path(pasta_atual)
            destino_pasta = destino / pasta_atual_path.relative_to(origem)
            destino_pasta.mkdir(parents=True, exist_ok=True)

            for nome in nomes_arquivos:
                if self.cancelado:
                    return contador, pulados_nuvem, negados

                caminho_origem = pasta_atual_path / nome
                caminho_destino = destino_pasta / nome

                if _eh_arquivo_sob_demanda(caminho_origem):
                    pulados_nuvem += 1
                    self.log(
                        f"    [!] Pulado (arquivo sob demanda na nuvem, não baixado): {caminho_origem}"
                    )
                    self._registrar_progresso_arquivo()
                    continue

                try:
                    shutil.copy2(caminho_origem, caminho_destino)
                    contador += 1
                except OSError as exc:
                    negados += 1
                    self.log(
                        f"    [!] Não foi possível copiar '{caminho_origem}': {exc}"
                    )
                self._registrar_progresso_arquivo()

        return contador, pulados_nuvem, negados

    def _registrar_progresso_arquivo(self) -> None:
        self._arquivos_processados += 1
        if self._total_arquivos:
            self.progresso(int(self._arquivos_processados / self._total_arquivos * 80))
        if self._arquivos_processados % INTERVALO_LOG_PROGRESSO == 0:
            self.log(
                f"  -> {self._arquivos_processados}/{self._total_arquivos} arquivo(s) processado(s)"
            )
