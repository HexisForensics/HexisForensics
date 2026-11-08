"""
Coleta de artefatos forenses clássicos do Windows: hives de registro,
Logs de Eventos, Lixeira, histórico de navegadores e Prefetch.

Pressupõe que a unidade selecionada é (ou contém) uma partição de sistema
Windows — ou seja, tem a estrutura padrão `Windows\\`, `Users\\` e
`$Recycle.Bin` na raiz. Cada categoria é coletada de forma independente:
um artefato ausente ou sem permissão de leitura (hive em uso, Lixeira de
outro usuário) não interrompe a coleta das demais, e por isso o módulo
funciona sem privilégios especiais — ainda que, sem eles, uma parte
previsível do material fique de fora.

Três correções de fundo, todas da mesma família: o módulo afirmava mais
do que tinha verificado.

1. **Ausência e recusa eram a mesma coisa.** A cópia devolvia apenas
   "deu certo" ou "não deu", e `Path.exists()` responde `False` tanto
   para o arquivo que não existe quanto para aquele que existe e não pode
   ser lido. Um hive de registro bloqueado por estar em uso saía do
   exame indistinguível de um hive que nunca esteve ali — e ausência de
   artefato, num laudo, lê-se como ausência do fato. Agora cada tentativa
   devolve `COPIADO`, `AUSENTE` ou `NEGADO`, e a distinção vem de
   `stat()`: `FileNotFoundError` é ausência, qualquer outro `OSError` é
   recusa.

2. **Coleta parcial saía como sucesso limpo.** Falha em qualquer
   categoria era só uma linha de log; o resultado dizia "47 itens" sem
   nada indicar que o registro inteiro ficara de fora. Agora toda recusa
   entra em `detalhes["acesso_negado"]`, que é chave de ressalva
   reconhecida pelo serviço de extração, e chega ao laudo.

3. **A contagem misturava coisas de tamanhos diferentes.** A Lixeira
   inteira era copiada com `copytree` e contava **1**, enquanto cada
   `.evtx` contava 1 também. "47 itens" não significava nada. Agora
   conta-se arquivo, sempre, e a árvore é percorrida arquivo a arquivo —
   o que de quebra permite registrar recusa dentro dela, que o
   `copytree` engolia inteira.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from core.base_extractor import ResultadoExtracao
from core.companheiros import companheiros_de
from core.registry import registrar_extrator

from .base import ComputadorExtractor

HIVES_REGISTRO = ("SAM", "SECURITY", "SOFTWARE", "SYSTEM", "DEFAULT")

# Resultado de uma tentativa de cópia. Três estados, e não dois: a
# diferença entre não existir e não poder ser lido é a diferença entre
# "não havia" e "não se sabe".
COPIADO = "copiado"
AUSENTE = "ausente"
NEGADO = "negado"

# Pastas de dados dos navegadores baseados em Chromium, relativas ao
# perfil do usuário. Dentro delas, cada subpasta `Default`/`Profile N` é
# um perfil de navegação distinto.
NAVEGADORES_CHROMIUM = {
    "Chrome": Path("AppData/Local/Google/Chrome/User Data"),
    "Edge": Path("AppData/Local/Microsoft/Edge/User Data"),
    "Brave": Path("AppData/Local/BraveSoftware/Brave-Browser/User Data"),
}

# Arquivo de histórico dentro de cada perfil Chromium.
ARQUIVO_HISTORICO_CHROMIUM = "History"

# Acervos de correio eletrônico, relativos à pasta de cada perfil do
# Windows. São pastas inteiras, e não arquivos avulsos: um perfil do
# Thunderbird tem dezenas de arquivos interdependentes, e um `.pst` costuma
# vir acompanhado de `.ost` e de índices que só fazem sentido juntos.
#
# `Documents/Outlook Files` aparece nas duas grafias porque é a pasta
# padrão do Outlook e muda com o idioma de instalação — a mesma armadilha
# que fez a cópia lógica perder uma pasta inteira.
CORREIO = (
    ("Outlook", Path("AppData/Local/Microsoft/Outlook")),
    ("Outlook_Arquivos", Path("Documents/Outlook Files")),
    ("Outlook_Arquivos_pt", Path("Documentos/Arquivos do Outlook")),
    ("Outlook_Anexos", Path("AppData/Local/Microsoft/Windows/INetCache/Content.Outlook")),
    ("Thunderbird", Path("AppData/Roaming/Thunderbird/Profiles")),
    ("Correio_do_Windows", Path("AppData/Local/Comms/UnistoreDB")),
)


@registrar_extrator
class ArtefatosWindowsExtractor(ComputadorExtractor):
    id = "computador_artefatos_windows"
    nome_exibicao = "Artefatos Forenses do Windows"
    ordem = 30
    descricao = (
        "Coleta hives de registro, Logs de Eventos, Lixeira, histórico de "
        "navegadores (Chrome/Edge/Brave/Firefox), acervos de correio eletrônico "
        "(Outlook, Thunderbird, Correio do Windows) e Prefetch da unidade selecionada. "
        "Pressupõe que a unidade contém uma instalação do Windows."
    )

    limitacoes_conhecidas = (
        "Coleta um conjunto fixo de artefatos conhecidos, não a totalidade do "
        "material forense do sistema: o que não está na lista deste módulo não é "
        "procurado, e sua ausência no material extraído nada diz sobre o disco.",
        "Dos navegadores é copiado o arquivo de histórico de cada perfil. Cookies, "
        "credenciais salvas, cache e downloads não são alcançados por este módulo.",
        "Executado sem privilégios de Administrador, ou sobre o disco de sistema em "
        "uso, arquivos bloqueados pelo sistema operacional não podem ser lidos. Toda "
        "recusa é contada e declarada no resultado, e nunca é reportada como ausência.",
        "Os arquivos são copiados como estão, sem interpretação: o exame do conteúdo "
        "de hives, logs e bancos de histórico depende de ferramenta própria.",
        "Os acervos de correio (.pst, .ost, caixas do Thunderbird) são preservados "
        "como estão, e NÃO são abertos por esta ferramenta. A relação de mensagens e "
        "anexos que eles contêm exige leitor próprio, em exame posterior — o que "
        "está aqui é o acervo, não o seu conteúdo relacionado.",
        "Correio armazenado apenas no servidor, sem cópia local, não está no disco e "
        "não é alcançado por cópia alguma. Ausência de acervo local não significa "
        "ausência de correspondência.",
        "Hives e bancos de histórico são copiados junto com os arquivos que os "
        "completam — os logs de transação do registro e o write-ahead log do "
        "SQLite. Sem eles, o que ainda não foi consolidado no arquivo principal se "
        "perderia sem que nada indicasse a falta.",
        "A leitura é feita na unidade já montada pelo Windows. A ferramenta nada "
        "grava nela, mas não interpõe bloqueador de escrita e nada pode afirmar "
        "sobre o que o sistema operacional tenha escrito ao montá-la.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        raiz_unidade = Path(self.unidade_obrigatoria())
        pasta_destino = pasta_caso / "artefatos_windows"
        pasta_destino.mkdir(parents=True, exist_ok=True)

        etapas = (
            ("Registro", self._coletar_registro),
            ("Logs de Eventos", self._coletar_logs_evento),
            ("Lixeira", self._coletar_lixeira),
            ("Navegadores", self._coletar_navegadores),
            ("Correio eletrônico", self._coletar_correio),
            ("Prefetch", self._coletar_prefetch),
        )

        copiados_por_etapa: Dict[str, int] = {}
        negados_por_etapa: Dict[str, int] = {}
        total_copiado = 0
        total_negado = 0

        for indice, (nome_etapa, funcao) in enumerate(etapas, 1):
            if self.cancelado:
                return ResultadoExtracao(
                    False,
                    "Extração cancelada pelo usuário.",
                    caminho_saida=pasta_destino,
                    detalhes={"incompleta": True, "cancelada": True},
                )
            self.log(f"[*] Coletando: {nome_etapa}...")
            try:
                copiados, negados = funcao(raiz_unidade, pasta_destino)
            except OSError as exc:
                # A etapa inteira caiu. Isso não é ausência de artefato:
                # é impossibilidade de verificar, e conta como recusa.
                self.log(f"    [!] Falha ao coletar '{nome_etapa}': {exc}")
                copiados, negados = 0, 1

            copiados_por_etapa[nome_etapa] = copiados
            negados_por_etapa[nome_etapa] = negados
            total_copiado += copiados
            total_negado += negados
            self.log(
                f"    -> {nome_etapa}: {copiados} arquivo(s) copiado(s)"
                + (f", {negados} sem acesso" if negados else "")
            )
            self.progresso(int(indice / len(etapas) * 100))

        detalhes: Dict[str, object] = {
            "copiados_por_categoria": copiados_por_etapa,
            "negados_por_categoria": negados_por_etapa,
            "arquivos_copiados": total_copiado,
        }

        # Nada copiado E nada negado: a unidade realmente não tem a
        # estrutura procurada. É a única leitura em que a ausência do
        # material autoriza uma conclusão, porque nada foi impedido.
        if total_copiado == 0 and total_negado == 0:
            mensagem = (
                "Nenhum artefato do Windows foi encontrado na unidade selecionada, e "
                "nenhum acesso foi negado — a unidade provavelmente não contém uma "
                "instalação do Windows."
            )
            self.log(f"[!] {mensagem}")
            return ResultadoExtracao(
                False, mensagem, caminho_saida=pasta_destino, detalhes=detalhes
            )

        if total_copiado == 0:
            detalhes["acesso_negado"] = total_negado
            mensagem = (
                f"Nenhum artefato pôde ser copiado: {total_negado} acesso(s) negado(s) "
                "pelo sistema. Nada se pode afirmar sobre a presença ou ausência desses "
                "artefatos no disco — execute como Administrador, ou sobre a unidade "
                "desmontada em outra máquina."
            )
            self.log(f"[FALHA] {mensagem}")
            return ResultadoExtracao(
                False, mensagem, caminho_saida=pasta_destino, detalhes=detalhes
            )

        vazias = [nome for nome, quantos in copiados_por_etapa.items() if quantos == 0]
        mensagem = f"Artefatos coletados: {total_copiado} arquivo(s)."
        if total_negado:
            detalhes["acesso_negado"] = total_negado
            mensagem += (
                f" RESSALVA: {total_negado} arquivo(s) não puderam ser lidos por recusa "
                "do sistema; sua ausência no material extraído não significa ausência no "
                "disco."
            )
        if vazias:
            mensagem += " Categorias sem nenhum arquivo: " + ", ".join(vazias) + "."

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            True, mensagem, caminho_saida=pasta_destino, detalhes=detalhes
        )

    # ------------------------------------------------------------------
    # Cópia com os três estados
    # ------------------------------------------------------------------
    def _copiar_arquivo(self, origem: Path, destino: Path) -> str:
        """
        Copia um arquivo e devolve `COPIADO`, `AUSENTE` ou `NEGADO`.

        A distinção sai de `stat()`, e não de `exists()`: `exists()`
        devolve `False` tanto para o que não existe quanto para o que
        existe e não pode ser consultado, que são fatos opostos para
        quem lê o laudo.
        """
        try:
            origem.stat()
        except FileNotFoundError:
            return AUSENTE
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{origem}': {exc}")
            return NEGADO

        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
            return COPIADO
        except OSError as exc:
            self.log(f"    [!] Não foi possível copiar '{origem}': {exc}")
            return NEGADO

    def _copiar_com_companheiros(self, origem: Path, destino: Path) -> Tuple[str, int, int]:
        """
        Copia um arquivo e os companheiros que o completam.

        Devolve `(estado_do_principal, companheiros_copiados,
        companheiros_negados)`.

        Um hive do registro tem `.LOG1`/`.LOG2`, e um banco SQLite tem
        `-wal`/`-shm`. Copiar só o arquivo principal perde o que ainda não
        foi consolidado nele — as últimas transações do registro, as
        mensagens mais recentes do histórico — e o arquivo abre normalmente
        depois, sem nada indicar a falta. É perda silenciosa de evidência,
        que é a pior espécie.

        Companheiro ausente é normal: o `-wal` some quando o banco fecha
        limpo. O que não pode é ele existir e ficar para trás.
        """
        estado = self._copiar_arquivo(origem, destino)
        if estado != COPIADO:
            return estado, 0, 0

        copiados = 0
        negados = 0
        for companheiro in companheiros_de(origem):
            resultado = self._copiar_arquivo(
                companheiro, destino.with_name(companheiro.name)
            )
            if resultado == COPIADO:
                copiados += 1
            elif resultado == NEGADO:
                negados += 1

        if copiados:
            self.log(
                f"    -> {origem.name}: {copiados} arquivo(s) companheiro(s) copiado(s)"
            )
        return estado, copiados, negados

    def _copiar_arvore(self, origem: Path, destino: Path) -> Tuple[int, int]:
        """
        Copia uma árvore inteira arquivo a arquivo, devolvendo
        `(copiados, negados)`.

        Não usa `shutil.copytree` de propósito: ele aborta ou engole o
        conjunto quando um único arquivo recusa leitura, e o que se perde
        é justamente a contagem de quanto ficou de fora. Aqui cada
        arquivo é uma tentativa contada, e a árvore inacessível aparece
        como recusa, não como vazio.
        """
        try:
            origem.stat()
        except FileNotFoundError:
            return 0, 0
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{origem}': {exc}")
            return 0, 1

        copiados = 0
        negados = 0
        houve_erro_de_walk = False

        def _ao_erro(erro: OSError) -> None:
            nonlocal houve_erro_de_walk
            houve_erro_de_walk = True
            self.log(f"    [!] Pasta sem acesso: {erro.filename} — {erro}")

        for pasta_atual, _subpastas, nomes in os.walk(
            origem, onerror=_ao_erro, followlinks=False
        ):
            if self.cancelado:
                break
            pasta_atual_path = Path(pasta_atual)
            relativo = pasta_atual_path.relative_to(origem)
            for nome in nomes:
                estado = self._copiar_arquivo(
                    pasta_atual_path / nome, destino / relativo / nome
                )
                if estado == COPIADO:
                    copiados += 1
                elif estado == NEGADO:
                    negados += 1

        if houve_erro_de_walk and negados == 0:
            # Diretório que nem pôde ser listado não gera tentativa de
            # cópia nenhuma, e sem isto sairia como árvore vazia.
            negados = 1

        return copiados, negados

    def _contar(self, estados: List[str]) -> Tuple[int, int]:
        """Resume uma lista de estados em `(copiados, negados)`."""
        return (
            sum(1 for e in estados if e == COPIADO),
            sum(1 for e in estados if e == NEGADO),
        )

    # ------------------------------------------------------------------
    # Categorias
    # ------------------------------------------------------------------
    def _coletar_registro(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        pasta_config = raiz_unidade / "Windows" / "System32" / "config"
        pasta_saida = pasta_destino / "registro"
        copiados = 0
        negados = 0
        for hive in HIVES_REGISTRO:
            estado, extras, recusas = self._copiar_com_companheiros(
                pasta_config / hive, pasta_saida / hive
            )
            copiados += (1 if estado == COPIADO else 0) + extras
            negados += (1 if estado == NEGADO else 0) + recusas
        return copiados, negados

    def _coletar_logs_evento(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        pasta_logs = raiz_unidade / "Windows" / "System32" / "winevt" / "Logs"
        pasta_saida = pasta_destino / "event_logs"
        try:
            arquivos = sorted(pasta_logs.glob("*.evtx"))
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{pasta_logs}': {exc}")
            return 0, 1
        if not pasta_logs.is_dir():
            return 0, 0
        estados = [
            self._copiar_arquivo(arquivo, pasta_saida / arquivo.name)
            for arquivo in arquivos
        ]
        return self._contar(estados)

    def _coletar_lixeira(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        return self._copiar_arvore(
            raiz_unidade / "$Recycle.Bin", pasta_destino / "recycle_bin"
        )

    def _coletar_navegadores(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        pasta_usuarios = raiz_unidade / "Users"
        if not pasta_usuarios.is_dir():
            return 0, 0

        copiados = 0
        negados = 0
        pasta_saida = pasta_destino / "navegadores"

        try:
            perfis_windows = [p for p in pasta_usuarios.iterdir() if p.is_dir()]
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{pasta_usuarios}': {exc}")
            return 0, 1

        for perfil in perfis_windows:
            for nome_navegador, caminho_dados in NAVEGADORES_CHROMIUM.items():
                pasta_dados = perfil / caminho_dados
                # Todos os perfis de navegação, e não só `Default`: um
                # segundo perfil no mesmo navegador é onde costuma estar
                # o que interessa, e ignorá-lo perdia evidência sem que
                # nada no resultado indicasse a perda.
                for pasta_perfil in self._perfis_chromium(pasta_dados):
                    estado, extras, recusas = self._copiar_com_companheiros(
                        pasta_perfil / ARQUIVO_HISTORICO_CHROMIUM,
                        pasta_saida
                        / perfil.name
                        / nome_navegador
                        / pasta_perfil.name
                        / ARQUIVO_HISTORICO_CHROMIUM,
                    )
                    copiados += (1 if estado == COPIADO else 0) + extras
                    negados += (1 if estado == NEGADO else 0) + recusas

            pasta_firefox = (
                perfil / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
            )
            try:
                perfis_firefox = (
                    [p for p in pasta_firefox.iterdir() if p.is_dir()]
                    if pasta_firefox.is_dir()
                    else []
                )
            except OSError as exc:
                self.log(f"    [!] Sem acesso a '{pasta_firefox}': {exc}")
                negados += 1
                perfis_firefox = []

            for perfil_firefox in perfis_firefox:
                estado, extras, recusas = self._copiar_com_companheiros(
                    perfil_firefox / "places.sqlite",
                    pasta_saida
                    / perfil.name
                    / "Firefox"
                    / perfil_firefox.name
                    / "places.sqlite",
                )
                copiados += (1 if estado == COPIADO else 0) + extras
                negados += (1 if estado == NEGADO else 0) + recusas

        return copiados, negados

    def _coletar_correio(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        """
        Acervos de correio eletrônico de cada perfil do Windows.

        Um `.pst` é a caixa de correio inteira num arquivo só — mensagens,
        pastas e **anexos**. É, de longe, o artefato de e-mail mais denso
        que um disco periciado costuma ter, e o módulo não o procurava.

        Copia, não interpreta. Ler um `.pst` de verdade é trabalho próprio,
        e prometer isso aqui seria afirmar o que a ferramenta não sustenta
        — mesma linha do backup `.crypt` do WhatsApp, preservado sem ser
        decifrado.

        O tamanho é registrado no log porque muda a decisão do examinador:
        uma caixa de vários gigabytes pode inviabilizar a cópia no prazo do
        exame, e ele precisa saber disso enquanto ainda pode decidir.
        """
        pasta_usuarios = raiz_unidade / "Users"
        if not pasta_usuarios.is_dir():
            return 0, 0

        try:
            perfis = [p for p in pasta_usuarios.iterdir() if p.is_dir()]
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{pasta_usuarios}': {exc}")
            return 0, 1

        copiados = 0
        negados = 0
        pasta_saida = pasta_destino / "correio"

        for perfil in perfis:
            for rotulo, relativo in CORREIO:
                origem = perfil / relativo
                if not origem.is_dir():
                    continue
                self.log(f"    -> Acervo de correio: {origem}")
                obtidos, recusados = self._copiar_arvore(
                    origem, pasta_saida / perfil.name / rotulo
                )
                copiados += obtidos
                negados += recusados
                if obtidos:
                    self._registrar_volume(pasta_saida / perfil.name / rotulo)

        return copiados, negados

    def _registrar_volume(self, pasta: Path) -> None:
        """Anota no log quanto o acervo copiado ocupa, em unidade legível."""
        total = 0
        for pasta_atual, _subpastas, nomes in os.walk(pasta, onerror=lambda _e: None):
            for nome in nomes:
                try:
                    total += (Path(pasta_atual) / nome).stat().st_size
                except OSError:
                    continue
        valor = float(total)
        for unidade in ("B", "KiB", "MiB", "GiB"):
            if valor < 1024 or unidade == "GiB":
                self.log(f"       {valor:.1f} {unidade} copiados")
                return
            valor /= 1024

    def _perfis_chromium(self, pasta_dados: Path) -> List[Path]:
        """
        Subpastas de perfil de um navegador Chromium: `Default` e cada
        `Profile N`. Devolve lista vazia se a pasta de dados não existir.
        """
        try:
            if not pasta_dados.is_dir():
                return []
            return sorted(
                p
                for p in pasta_dados.iterdir()
                if p.is_dir()
                and (p.name == "Default" or p.name.startswith("Profile "))
            )
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{pasta_dados}': {exc}")
            return []

    def _coletar_prefetch(
        self, raiz_unidade: Path, pasta_destino: Path
    ) -> Tuple[int, int]:
        pasta_prefetch = raiz_unidade / "Windows" / "Prefetch"
        pasta_saida = pasta_destino / "prefetch"
        try:
            arquivos = sorted(pasta_prefetch.glob("*.pf"))
        except OSError as exc:
            self.log(f"    [!] Sem acesso a '{pasta_prefetch}': {exc}")
            return 0, 1
        if not pasta_prefetch.is_dir():
            return 0, 0
        estados = [
            self._copiar_arquivo(arquivo, pasta_saida / arquivo.name)
            for arquivo in arquivos
        ]
        return self._contar(estados)
