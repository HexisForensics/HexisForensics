"""
Base comum a todos os extratores Android: fornece acesso compartilhado a
um `ADBClient`/`AndroidDevice` e implementa a checagem padrão de
disponibilidade (binário presente + dispositivo conectado e autorizado),
para que cada extrator concreto só precise se preocupar com sua lógica de
coleta específica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from core.armazenamento import formatar_bytes, verificar_espaco
from core import backup_android
from core.base_extractor import BaseExtractor, Plataforma
from core.hashing import calcular_sha256
# Os marcadores de recusa do provider moram em `core.normalizacao`: a mesma
# regra vale na coleta (distinguir "sem dados" de "acesso negado") e meses
# depois, quando o bruto é normalizado para o relatório de conteúdo. Duas
# definições divergiriam na primeira vez que uma delas fosse ajustada.
from core.normalizacao import MARCADORES_ACESSO_NEGADO, indica_acesso_negado  # noqa: F401

from ..adb_client import ADBClient, ResultadoPull, SituacaoPull
from ..device import AndroidDevice

# A partir do Android 12 (API 31), a Google removeu o recurso `adb backup`
# do sistema — abaixo disso, em dispositivos mais antigos, ainda vale a
# pena tentar como alternativa ao provider negado.
NIVEL_API_ANDROID_12 = 31

# A partir do Android 11 (API 30) o proprio sistema deixou de expor
# /sdcard/Android/data ao shell do ADB. Uma copia de /sdcard nesses
# aparelhos vem SEM essa subarvore, e o `adb pull` nao avisa: ele apenas
# nao traz os arquivos. Sem declarar isso, o exame concluiria que os dados
# dos aplicativos nao existiam.
NIVEL_API_ANDROID_11 = 30
CAMINHO_DADOS_DE_APP = "/sdcard/Android/data"


def _nome_aceito_no_windows(nome: str) -> str:
    """O nome como o Windows o grava: sem ponto nem espaço no fim."""
    return nome.rstrip(". ") or "_"


def _nome_livre(local: Path) -> Path:
    """Um nome ainda livre na pasta, derivado do original."""
    base = _nome_aceito_no_windows(local.name)
    numero = 1
    while True:
        candidato = local.with_name(f"{base} (nome alterado {numero})")
        if not candidato.exists():
            return candidato
        numero += 1


def saida_indica_acesso_negado(saida: str) -> bool:
    """Detecta se a saída de um `content query` indica falha de permissão.

    Em muitas versões recentes do Android, o shell ADB (uid=2000) não tem
    as permissões READ_SMS / READ_CALL_LOG necessárias para os providers
    nativos sem que o dispositivo esteja rooteado. Nesse caso, `content
    query` não retorna dados: retorna um stack trace de `SecurityException`
    ("Permission Denial ... requires android.permission.READ_SMS", etc.).

    Isso é uma restrição do próprio Android, não um erro do
    HexisForensics — mas o extrator precisa reconhecer esse padrão para
    não reportar sucesso quando, na prática, nenhum dado foi obtido. A
    saída bruta continua sendo salva no arquivo de evidência de qualquer
    forma, documentando a tentativa para fins de laudo.
    """
    return indica_acesso_negado(saida)


PASTA_AQUISICAO = "aquisicao"

# Teto de arquivos inventariados por caminho. Um `find` em /sdcard de um
# aparelho cheio pode devolver centenas de milhares de linhas; acima deste
# limite a reconciliação é feita por CONTAGEM e o fato fica registrado, em
# vez de a ferramenta travar tentando casar nome a nome.
LIMITE_INVENTARIO = 50_000

# Quantos caminhos por chamada de `sha256sum`. Lotes grandes demais estouram
# o limite de tamanho da linha de comando do shell do aparelho.
LOTE_HASH_ORIGEM = 40

# Acima deste volume a verificacao na origem e dispensada e o fato fica
# declarado: hashear dezenas de GB no processador do aparelho levaria horas.
# A escolha e explicita justamente para nao virar omissao silenciosa.
LIMITE_VERIFICACAO_ORIGEM = 2 * 1024 ** 3


@dataclass
class Inventario:
    """
    O que existe na origem, e por qual via isso foi apurado.

    O método importa para o exame: `find` lista arquivos diretamente, ao
    passo que `ls -R` exige inferir quais entradas são diretórios. São
    graus de confiança diferentes, e o relatório de reconciliação informa
    qual foi usado em vez de apresentar os dois como equivalentes.
    """

    arquivos: Optional[List[str]] = None
    motivo_indisponivel: str = ""
    metodo: str = ""

    @property
    def disponivel(self) -> bool:
        """`False` quando a origem não pôde ser inventariada por via alguma."""
        return self.arquivos is not None


@dataclass
class ResultadoAquisicao:
    """
    Uma cópia acompanhada da prova de que ela está completa e íntegra.

    Três coisas que um `adb pull` sozinho não responde e que o exame
    precisa: o que existia na origem (inventário), o que efetivamente
    chegou (reconciliação) e qual o hash de cada arquivo adquirido.
    """

    copia: ResultadoPull
    arquivos_na_origem: Optional[int] = None
    faltantes: List[str] = field(default_factory=list)
    inventario_indisponivel: str = ""
    metodo_inventario: str = ""
    restricao_do_sistema: str = ""
    verificacao_na_origem: str = ""
    divergencias: List[str] = field(default_factory=list)
    hashes: dict = field(default_factory=dict)
    # Arquivos que o `adb pull` não trouxe e foram lidos um a um.
    recuperados_um_a_um: int = 0
    # arquivo -> por que nem a leitura individual o trouxe.
    motivos_dos_faltantes: dict = field(default_factory=dict)
    # nome gravado na estação -> nome no aparelho, quando o Windows não
    # aceitava o original (dois nomes que só diferem em maiúsculas, ponto
    # ou espaço no fim). O conteúdo é o mesmo, conferido pelo hash.
    nomes_trocados: dict = field(default_factory=dict)

    @property
    def sucesso(self) -> bool:
        return self.copia.sucesso

    @property
    def integra(self) -> Optional[bool]:
        """
        `True` quando cada arquivo adquirido tem, no aparelho, o mesmo
        SHA-256 que tem no destino.

        `None` quando a verificacao na origem nao foi possivel -- e nesse
        caso NAO se afirma fidelidade. Hashear apenas o arquivo que chegou
        prova que ele nao mudou desde que chegou; nao prova que a
        transferencia foi fiel.
        """
        if not self.verificacao_na_origem.startswith("realizada"):
            return None
        return not self.divergencias

    @property
    def inconsistente(self) -> bool:
        """
        `True` quando foram adquiridos MAIS arquivos do que o inventário
        encontrou na origem.

        É uma contradição aritmética: não se copia da origem mais do que ela
        contém. Quando acontece, o inventário está errado — e o relatório
        precisa dizer isso, em vez de escolher um dos dois números e
        apresentá-lo como fato. Foi exatamente esse o sintoma de um `ls -R`
        que não recursava: "origem vazia" ao lado de 273 arquivos copiados.
        """
        if self.arquivos_na_origem is None:
            return False
        return self.copia.arquivos_copiados > self.arquivos_na_origem

    @property
    def completa(self) -> Optional[bool]:
        """
        `None` quando não foi possível inventariar a origem, ou quando o
        inventário se contradiz com o que foi adquirido — não se afirma
        completude que não se pode verificar.
        """
        if self.arquivos_na_origem is None or self.inconsistente:
            return None
        return not self.faltantes


class AndroidExtractor(BaseExtractor):
    plataforma = Plataforma.ANDROID

    def __init__(self, adb_client: Optional[ADBClient] = None, **kwargs):
        super().__init__(**kwargs)
        self.adb = adb_client or ADBClient()
        self.device = AndroidDevice(self.adb)

    def consultar_provider(
        self, uri: str, arquivo_bruto: Path
    ) -> Tuple[str, bool]:
        """
        Consulta um Content Provider e devolve `(dados, houve_recusa)`.

        Existe porque `self.adb.executar()` devolve **só o stdout**, e a
        recusa do Android sai no **stderr** -- com codigo de saida ZERO.
        Medido num moto x4 de fabrica (Android 9):

            content://call_log/calls -> codigo 0, stdout vazio,
                                        stderr 1373 bytes com
                                        "Permission Denial ... requires
                                        android.permission.READ_CALL_LOG"

        Com o stderr descartado, `saida_indica_acesso_negado("")` respondia
        False, e o modulo concluia que "o provider respondeu e nao retornou
        nenhum registro" -- transformando RECUSA DE ACESSO em AFIRMACAO DE
        AUSENCIA, que e o pior defeito possivel nesta ferramenta. O codigo
        de saida nao serve de sinal: o Android recusa com zero. E a mesma
        familia do defeito do `dd`, em que erro de leitura e fim de volume
        eram indistinguiveis.

        O arquivo bruto preserva a tentativa (principio 3: stdout e stderr
        sao evidencia e nunca sao descartados):

        - com dados, grava o stdout, e o stderr vai para um arquivo irmao
          `_stderr.txt` -- junta-los contaminaria o ultimo registro `Row:`
          lido pelo normalizador;
        - sem dados, grava o stderr no proprio arquivo bruto: e ele a
          evidencia do que foi tentado. O normalizador ja conta texto fora
          do formato `Row: N` como descarte declarado.

        `dados` continua sendo apenas o stdout: mensagem de erro jamais
        pode ser devolvida como se fosse dado do aparelho.
        """
        resultado = self.adb.executar_detalhado(
            ["shell", "content", "query", "--uri", uri]
        )
        saida = resultado.stdout or ""
        erro = (resultado.stderr or "").strip()

        arquivo_bruto.parent.mkdir(parents=True, exist_ok=True)
        if saida:
            arquivo_bruto.write_text(saida, encoding="utf-8")
            if erro:
                arquivo_bruto.with_name(
                    arquivo_bruto.stem + "_stderr.txt"
                ).write_text(erro, encoding="utf-8")
        else:
            arquivo_bruto.write_text(erro, encoding="utf-8")

        # A recusa e procurada no stderr E no stdout: ha versoes do Android
        # que imprimem o SecurityException na saida padrao.
        houve_recusa = indica_acesso_negado(erro) or indica_acesso_negado(saida)
        return saida, houve_recusa

    def nivel_api(self) -> Optional[int]:
        """
        Nivel de API do aparelho, lido uma unica vez por extrator.

        Varias decisoes metodologicas dependem dele -- e nenhuma delas pode
        ser tomada por presuncao, como ja custou uma justificativa falsa no
        registro de um caso.
        """
        if getattr(self, "_nivel_api", "nao lido") == "nao lido":
            bruto = self.adb.executar(["shell", "getprop", "ro.build.version.sdk"]).strip()
            try:
                self._nivel_api = int(bruto)
            except (TypeError, ValueError):
                self._nivel_api = None
        return self._nivel_api

    def shell_e_root(self) -> bool:
        """
        Se o shell do ADB esta em modo root, lido uma unica vez por extrator.

        Mora aqui porque duas decisoes dependem dele e estavam separadas: o
        dump do sistema de arquivos perguntava por conta propria, e a
        ressalva de scoped storage nao perguntava nada -- presumia pela
        versao do Android.
        """
        if getattr(self, "_shell_e_root", "nao lido") == "nao lido":
            self._shell_e_root = (
                self.adb.executar(["shell", "whoami"]).strip() == "root"
            )
        return self._shell_e_root

    def restricao_de_dados_de_app(self, caminho_remoto: str) -> str:
        """
        Texto da ressalva quando o caminho abrange `/sdcard/Android/data` em
        aparelho com Android 11 ou superior.

        Devolve string vazia quando nao se aplica. O ponto sensivel: o `adb
        pull` de `/sdcard` nesses aparelhos simplesmente NAO traz essa
        subarvore, sem erro e sem aviso. A copia parece integral e nao e.
        """
        api = self.nivel_api()
        if api is None or api < NIVEL_API_ANDROID_11:
            return ""

        # Com o shell em root, adbd LE essa subarvore, e a restricao do
        # sistema nao se aplica. Emiti-la assim mesmo faria o registro
        # afirmar que os dados NAO foram adquiridos quando eles foram --
        # a ferramenta declarando uma limitacao que nao verificou, que e o
        # mesmo defeito de sempre virado do avesso. Custa caro do mesmo
        # jeito: o examinador descarta como inexistente o que esta na
        # pasta, ou procura noutro lugar o que ja tem em maos.
        if self.shell_e_root():
            return ""

        raiz = caminho_remoto.rstrip("/")
        abrange = CAMINHO_DADOS_DE_APP.startswith(raiz + "/") or raiz == CAMINHO_DADOS_DE_APP
        if not abrange:
            return ""

        return (
            f"Aparelho com Android API {api}: a partir do Android 11 (API 30) o sistema "
            f"nao expoe {CAMINHO_DADOS_DE_APP} ao shell do ADB. Os dados privados dos "
            "aplicativos NAO foram adquiridos por este caminho, e a copia obtida NAO "
            "abrange essa subarvore. A ausencia desses dados aqui decorre de restricao "
            "do sistema, e nao autoriza concluir que o aparelho nao os continha."
        )

    def contar_perfis_de_usuario(self) -> Optional[int]:
        """
        Quantos perfis de usuario existem no aparelho.

        Android permite usuario secundario e perfil de trabalho, cada um com
        area de dados propria (`/data/user/<n>/`). Devolve `None` quando nao
        foi possivel determinar.
        """
        resultado = self.adb.executar_detalhado(["shell", "pm", "list", "users"], timeout=60)
        if not resultado.sucesso:
            return None

        perfis = re.findall(r"UserInfo\{(\d+):", resultado.stdout)
        return len(perfis) if perfis else None

    @staticmethod
    def restricao_de_multiplos_usuarios(quantidade: int) -> str:
        """
        Texto da ressalva quando o aparelho tem mais de um perfil.

        Esta limitacao existia desde sempre e NAO estava declarada em lugar
        nenhum: a extracao alcanca apenas o usuario principal, e um perfil de
        trabalho ou um segundo usuario tem area de dados propria, intocada.
        Concluir sobre o conteudo do aparelho sem saber disso e concluir
        sobre uma fracao dele.
        """
        return (
            f"O aparelho possui {quantidade} perfis de usuario. Esta extracao alcanca "
            "apenas o perfil principal (usuario 0). Perfis adicionais -- segundo usuario "
            "ou perfil de trabalho -- mantem area de dados propria em /data/user/<n>/, "
            "inacessivel por esta via e nao adquirida. A ausencia desses dados no material "
            "extraido NAO autoriza concluir que o aparelho nao os continha."
        )

    def definir_serial(self, serial: Optional[str]) -> None:
        """
        Vincula este extrator ao aparelho do caso.

        Chamado pela camada de UI logo apos a abertura do caso, no mesmo
        padrao de `definir_unidade` dos extratores de Computador.
        """
        self.adb.definir_serial(serial)

    def disponivel(self) -> Tuple[bool, str]:
        binario_ok, motivo = self.adb.verificar_binario()
        if not binario_ok:
            return False, motivo

        status = self.device.verificar_conexao()
        serial_do_caso = self.adb.serial

        # Se o aparelho já estava vinculado ao caso, ele foi detectado no
        # início do procedimento. Sumir depois disso NÃO é problema de cabo
        # nem de Depuração USB — essas hipóteses já foram descartadas pelos
        # módulos que rodaram antes. Repetir a mensagem genérica de setup
        # atribui ao exame uma causa falsa; o que houve foi a perda do
        # aparelho no meio da aquisição, e isso é um evento de cadeia de
        # custódia.
        if serial_do_caso:
            seriais = status.seriais_detectados
            if serial_do_caso not in seriais:
                return False, (
                    f"O aparelho '{serial_do_caso}', vinculado a este caso, deixou de "
                    "responder ao ADB DURANTE a aquisição. Ele foi detectado no início do "
                    "procedimento, portanto cabo e Depuração USB não são a causa. "
                    "Hipóteses: desconexão física, desligamento ou reinício do aparelho, "
                    "bloqueio de tela com revogação da autorização, ou suspensão da porta "
                    "USB. Reconecte o aparelho e execute os módulos restantes em uma NOVA "
                    "aquisição, que ficará registrada como tal."
                )
            if not status.autorizado:
                return False, (
                    f"O aparelho '{serial_do_caso}' está conectado, porém deixou de estar "
                    f"autorizado durante a aquisição ({status.mensagem})"
                )
            return True, ""

        if not status.conectado:
            return False, status.mensagem
        if not status.autorizado:
            return False, status.mensagem
        return True, ""

    # ------------------------------------------------------------------
    # Utilitários compartilhados por extratores que copiam caminhos do
    # aparelho com `adb pull`.
    # ------------------------------------------------------------------
    def copiar_caminho(
        self,
        caminho_remoto: str,
        destino_local: Path,
        faixa_progresso: Optional[Tuple[int, int]] = None,
    ) -> ResultadoPull:
        """
        Executa um `adb pull` **registrando o desfecho no log do caso** e
        mantendo a cópia sob controle do examinador.

        Todo extrator deve copiar por aqui, e não chamando `self.adb.pull`
        diretamente: é este método que garante que a recusa do Android
        apareça no `extracao.log` em vez de se perder, que o cancelamento
        surta efeito durante a cópia, e que o progresso reportado seja o da
        transferência, e não o da contagem de pastas.

        `faixa_progresso` mapeia o percentual da cópia na fatia que este
        caminho ocupa no módulo (ex.: `(15, 32)`), para que a barra do
        examinador avance de forma contínua ao longo de vários caminhos.
        """
        ao_progredir = None
        if faixa_progresso is not None:
            inicio, fim = faixa_progresso

            def ao_progredir(percentual: int) -> None:
                self.progresso(inicio + int((fim - inicio) * percentual / 100))

        resultado = self.adb.pull(
            caminho_remoto,
            destino_local,
            cancelado=lambda: self.cancelado,
            ao_progredir=ao_progredir,
        )
        self.log(f" -> {resultado.resumo()}")

        # A mensagem do ADB é evidência da tentativa: fica no log mesmo
        # quando a cópia teve sucesso (pode haver recusa parcial).
        if resultado.stderr:
            for linha in resultado.stderr.splitlines()[:3]:
                self.log(f"    [ADB] {linha.strip()}")

        return resultado

    @staticmethod
    def avaliar_consulta_a_provider(
        rotulo: str, obteve_dado: bool, acesso_negado: bool, arquivos_backup: list
    ) -> Tuple[bool, str]:
        """
        Decide o desfecho de um módulo que consulta Content Providers.

        A distinção que precisa aparecer no relatório:

        - **dado obtido** → sucesso;
        - **nada obtido, com recusa do sistema** → FALHA. O provider negou,
          então não se sabe se havia dado. Declarar sucesso aqui produziria
          a conclusão negativa falsa de que o aparelho não continha
          contatos ou mensagens;
        - **nada obtido, sem recusa** → sucesso. A consulta foi respondida e
          veio vazia: isso é um fato verificado sobre o aparelho.
        """
        if obteve_dado:
            mensagem = f"{rotulo}: dados obtidos."
            if arquivos_backup:
                mensagem += f" {len(arquivos_backup)} backup(s) .ab como alternativa."
            if acesso_negado:
                mensagem += " Ressalva: parte das consultas foi recusada pelo sistema (ver log)."
            return True, mensagem

        if acesso_negado:
            return False, (
                f"{rotulo}: NENHUM dado obtido — o sistema recusou o acesso ao provider. "
                "A recusa foi preservada como evidência da tentativa. NÃO se pode concluir, "
                "a partir deste módulo, que o aparelho não continha esses dados."
            )

        return True, (
            f"{rotulo}: o provider respondeu à consulta e não retornou nenhum registro."
        )

    @staticmethod
    def aspas_para_shell(caminho: str) -> str:
        """
        Protege um caminho para uso dentro do shell do aparelho.

        `adb shell` NÃO recebe uma lista de argumentos: ele junta tudo numa
        linha e entrega ao shell do dispositivo, que separa por espaço. Um
        caminho como `/sdcard/Android/media/com.whatsapp.w4b/WhatsApp
        Business/Media` chegava, portanto, como DOIS argumentos — e o
        `find` inventariava caminhos que não existem, devolvendo zero
        arquivo para uma pasta cheia. O `adb pull` não sofre disso, porque
        recebe o caminho como argumento próprio: o resultado era um
        inventário vazio ao lado de uma cópia bem-sucedida.
        """
        return "'" + caminho.replace("'", "'\\''") + "'"

    def inventariar_origem(self, caminho_remoto: str) -> Inventario:
        """
        Lista os arquivos que existem no aparelho sob `caminho_remoto`.

        É o que torna a completude **verificável**: sem saber o que havia na
        origem, "copiei 4.809 arquivos" não permite afirmar que nada ficou
        para trás.

        Duas vias, nesta ordem:

        1. `find`, que lista arquivos diretamente. Ausente em Android antigo
           (5.x e anteriores usam toolbox, sem `find`).
        2. `ls -R`, presente em qualquer versão, do qual os arquivos são
           inferidos descartando as entradas que reaparecem como diretório.

        Nunca inventa um inventário que não conseguiu obter: quando as duas
        vias falham, devolve `Inventario` indisponível com o motivo.
        """
        inventario = self._inventariar_por_find(caminho_remoto)
        if inventario.disponivel or "não existe" not in inventario.motivo_indisponivel:
            return inventario

        # Aparelho sem `find`: a alternativa recupera a reconciliação, que
        # de outro modo ficaria indisponível em todo Android antigo.
        self.log("    Aparelho sem 'find'; inventariando a origem por 'ls -R'.")
        alternativa = self._inventariar_por_ls(caminho_remoto)
        if alternativa.disponivel:
            return alternativa

        return Inventario(
            motivo_indisponivel=(
                f"{inventario.motivo_indisponivel}; a alternativa 'ls -R' também não "
                f"funcionou ({alternativa.motivo_indisponivel})"
            )
        )

    def _inventariar_por_find(self, caminho_remoto: str) -> Inventario:
        """Inventário por `find`, a via preferida quando o aparelho a possui."""
        # `/sdcard` é link simbólico, e `find /sdcard` (sem barra) não entra
        # nele: o inventário vinha VAZIO. Com o inventário vazio não há lista
        # de faltantes, a recuperação um a um nunca dispara, e a completude
        # da cópia deixa de ser conferível. Não é defeito de aparelho antigo:
        # um Android 13 inventariou 0 arquivo(s) no `/sdcard` (07/11/2026),
        # embora a cópia em bloco os trouxesse. A barra final faz o `find`
        # seguir o link — a mesma salvaguarda que o `ls -R` já tinha. Se o
        # alvo for um arquivo, a barra falha e a segunda forma o lista.
        alvo = caminho_remoto.rstrip("/")
        resultado = self.adb.executar_detalhado(
            ["shell", f"find {self.aspas_para_shell(alvo + '/')} -type f "
                      f"|| find {self.aspas_para_shell(alvo)} -type f"],
            timeout=600,
        )
        saida = resultado.stdout
        # O shell do Android escreve seus próprios erros no stdout tanto
        # quanto no stderr, então os dois precisam ser examinados juntos.
        bruto = f"{saida}\n{resultado.stderr}".lower()

        # Ordem importa. "find: not found" NÃO é "a pasta está vazia" nem
        # "o acesso foi negado": é a ferramenta de inventário não existir.
        # Tratar isso como lista de arquivos foi o que fez a mensagem de
        # erro do shell ser contada como cinco arquivos faltantes.
        if "permission denied" in bruto or saida_indica_acesso_negado(saida):
            return Inventario(motivo_indisponivel="acesso negado ao listar a origem")
        if "not found" in bruto and "no such file" not in bruto:
            return Inventario(
                motivo_indisponivel="o comando 'find' não existe neste aparelho"
            )
        if "no such file" in bruto:
            return Inventario(arquivos=[], metodo="find")
        if not resultado.sucesso and not saida.strip():
            return Inventario(motivo_indisponivel=resultado.motivo_falha)
        if not saida.strip():
            return Inventario(arquivos=[], metodo="find")

        arquivos, descartadas = self._relativizar_linhas(saida.splitlines(), caminho_remoto)

        # Saída inteiramente irreconhecível: o inventário não é confiável, e
        # afirmar completude sobre ele seria pior do que não afirmar nada.
        if descartadas and not arquivos:
            return Inventario(
                motivo_indisponivel="a saída do 'find' não foi reconhecida como lista de arquivos"
            )
        if len(arquivos) > LIMITE_INVENTARIO:
            return Inventario(
                motivo_indisponivel=f"inventário acima do limite de {LIMITE_INVENTARIO} arquivos"
            )
        return Inventario(arquivos=arquivos, metodo="find")

    def _inventariar_por_ls(self, caminho_remoto: str) -> Inventario:
        """
        Inventário por `ls -R`, para aparelhos sem `find`.

        `ls -R` imprime um bloco por diretório::

            /sdcard/DCIM:
            Camera

            /sdcard/DCIM/Camera:
            foto_1.jpg
            foto_2.jpg

        Ele não diz o que é arquivo e o que é diretório — mas todo
        diretório reaparece como cabeçalho de um bloco adiante. Toda
        entrada que **não** reaparece assim é arquivo. É essa inferência
        que substitui o `-type f` do `find`.
        """
        # A barra final e obrigatoria: `/sdcard` e link simbolico, e sem ela o
        # toolbox imprime apenas o nome do link, sem recursar. Foi assim que
        # uma pasta com 273 arquivos foi inventariada como vazia.
        resultado = self.adb.executar_detalhado(
            ["shell", f"ls -R {self.aspas_para_shell(caminho_remoto.rstrip('/') + '/')}"],
            timeout=600,
        )
        saida = resultado.stdout
        bruto = f"{saida}\n{resultado.stderr}".lower()

        if "permission denied" in bruto or saida_indica_acesso_negado(saida):
            return Inventario(motivo_indisponivel="acesso negado ao listar a origem")
        if "no such file" in bruto:
            return Inventario(arquivos=[], metodo="ls -R")
        if "not found" in bruto:
            return Inventario(motivo_indisponivel="o comando 'ls' não respondeu neste aparelho")
        if not saida.strip():
            return Inventario(arquivos=[], metodo="ls -R")

        # Uma listagem valida sempre traz ao menos um cabecalho de bloco
        # ("/caminho:"), inclusive quando a pasta esta vazia. Saida sem
        # cabecalho algum significa que o `ls` NAO recursou -- e reportar
        # zero arquivo nesse caso seria afirmar vazio o que nao se listou.
        if not any(linha.strip().endswith(":") for linha in saida.splitlines()):
            return Inventario(
                motivo_indisponivel=(
                    "o 'ls -R' não recursou neste caminho (nenhuma listagem de diretório "
                    "foi devolvida)"
                )
            )

        blocos = self._separar_blocos_do_ls(saida, caminho_remoto)
        if not blocos:
            return Inventario(motivo_indisponivel="a saída do 'ls -R' não foi reconhecida")

        # A propria raiz e diretorio por definicao. Sem isso, um aparelho que
        # imprime a raiz como entrada solta (observado ao listar /sdcard, que
        # e link simbolico) faria a raiz virar "arquivo" no inventario.
        diretorios = set(blocos) | {caminho_remoto.rstrip("/")}

        caminhos_absolutos = []
        for pasta, entradas in blocos.items():
            for entrada in entradas:
                # Entradas de `ls -R` sao nomes simples; quando vem um caminho
                # absoluto, ele ja e o proprio alvo e nao um filho da pasta.
                absoluto = entrada if entrada.startswith("/") else f"{pasta}/{entrada}"
                if absoluto not in diretorios:
                    caminhos_absolutos.append(absoluto)

        arquivos, _ = self._relativizar_linhas(caminhos_absolutos, caminho_remoto)
        if len(arquivos) > LIMITE_INVENTARIO:
            return Inventario(
                motivo_indisponivel=f"inventário acima do limite de {LIMITE_INVENTARIO} arquivos"
            )
        return Inventario(arquivos=arquivos, metodo="ls -R")

    @staticmethod
    def _separar_blocos_do_ls(saida: str, caminho_remoto: str) -> dict:
        """Agrupa a saída de `ls -R` em {diretório: [entradas]}."""
        blocos: dict = {}
        pasta_atual = None

        for linha_bruta in saida.splitlines():
            linha = linha_bruta.strip()
            if not linha:
                continue
            if linha.endswith(":") and linha.startswith("/"):
                pasta_atual = linha[:-1].rstrip("/")
                blocos.setdefault(pasta_atual, [])
                continue
            if pasta_atual is None:
                # Sem cabeçalho de bloco, a listagem é do próprio caminho
                # pedido (acontece quando ele não tem subpastas).
                pasta_atual = caminho_remoto.rstrip("/")
                blocos.setdefault(pasta_atual, [])
            blocos[pasta_atual].append(linha)

        return blocos

    @staticmethod
    def _relativizar_linhas(linhas, caminho_remoto: str) -> Tuple[List[str], int]:
        """
        Converte caminhos absolutos do aparelho em caminhos relativos à raiz
        pedida, descartando o que não pertence a ela.

        Só é inventário o que de fato parece um caminho sob a raiz. Qualquer
        outra linha é ruído do shell e não pode virar "arquivo".
        """
        prefixo = caminho_remoto.rstrip("/") + "/"
        arquivos: List[str] = []
        descartadas = 0

        for linha in linhas:
            # A barra final no `find` faz o toybox imprimir "/sdcard//DCIM/…":
            # colapsa barras repetidas, senão o prefixo não casa e o relativo
            # nasceria com "/" na frente.
            caminho = re.sub(r"/{2,}", "/", linha.strip())
            if not caminho:
                continue
            if caminho.startswith(prefixo):
                arquivos.append(caminho[len(prefixo):])
            elif caminho == caminho_remoto.rstrip("/"):
                arquivos.append(Path(caminho).name)
            else:
                descartadas += 1

        return arquivos, descartadas

    def estimar_tamanho_origem(self, caminho_remoto: str) -> Optional[int]:
        """
        Tamanho aproximado, em bytes, do que existe sob `caminho_remoto`.

        Usa `du -sk`, presente na maioria dos aparelhos. Devolve `None`
        quando nao e possivel estimar -- e nesse caso a aquisicao segue sem
        checagem de espaco, porque impedir uma coleta por falta de
        estimativa seria pior do que nao checar.
        """
        resultado = self.adb.executar_detalhado(
            ["shell", f"du -sk {self.aspas_para_shell(caminho_remoto)}"], timeout=300
        )
        if not resultado.sucesso or not resultado.stdout.strip():
            return None

        primeiro_campo = resultado.stdout.split()[0] if resultado.stdout.split() else ""
        try:
            return int(primeiro_campo) * 1024
        except ValueError:
            return None

    def hashear_na_origem(
        self, caminho_remoto: str, relativos: List[str]
    ) -> Tuple[Optional[dict], str]:
        """
        Calcula o SHA-256 dos arquivos **dentro do aparelho**, antes de
        qualquer comparacao com o que chegou.

        E o que transforma "o arquivo que tenho tem este hash" em "o arquivo
        que tenho e identico ao que estava no aparelho". Sem isso, uma
        corrupcao durante a transferencia passaria despercebida: o hash
        calculado no destino bateria consigo mesmo.

        Depende de `sha256sum` existir no aparelho -- presente no toybox
        (Android 6+), ausente nos aparelhos antigos com toolbox. Quando nao
        existe, devolve `(None, motivo)`, e a nao verificacao fica declarada
        em vez de presumida.
        """
        if not relativos:
            return {}, ""

        hashes: dict = {}
        prefixo = caminho_remoto.rstrip("/") + "/"

        for inicio in range(0, len(relativos), LOTE_HASH_ORIGEM):
            if self.cancelado:
                return None, "verificacao interrompida pelo examinador"

            lote = relativos[inicio:inicio + LOTE_HASH_ORIGEM]
            alvos = " ".join(self.aspas_para_shell(prefixo + nome) for nome in lote)
            resultado = self.adb.executar_detalhado(["shell", f"sha256sum {alvos}"], timeout=900)

            bruto = f"{resultado.stdout}\n{resultado.stderr}".lower()
            if "not found" in bruto or "inaccessible" in bruto:
                return None, "o aparelho nao possui o comando 'sha256sum'"

            for linha in resultado.stdout.splitlines():
                partes = linha.strip().split(None, 1)
                if len(partes) != 2 or len(partes[0]) != 64:
                    continue
                valor, caminho = partes
                nome = caminho[len(prefixo):] if caminho.startswith(prefixo) else caminho
                hashes[nome] = valor

        if not hashes:
            return None, "o aparelho nao devolveu nenhum hash"
        return hashes, ""

    def verificar_fidelidade(
        self, caminho_remoto: str, destino_local: Path, aquisicao: "ResultadoAquisicao"
    ) -> None:
        """
        Confronta o hash de cada arquivo no aparelho com o do arquivo copiado.

        Preenche `verificacao_na_origem` e `divergencias` na aquisicao. Nao
        levanta excecao: falha na verificacao nunca pode derrubar uma coleta
        ja concluida.
        """
        if not aquisicao.hashes:
            aquisicao.verificacao_na_origem = "dispensada: nenhum arquivo adquirido"
            return

        if aquisicao.copia.bytes_copiados > LIMITE_VERIFICACAO_ORIGEM:
            aquisicao.verificacao_na_origem = (
                f"NAO realizada: volume adquirido "
                f"({formatar_bytes(aquisicao.copia.bytes_copiados)}) acima do limite de "
                f"{formatar_bytes(LIMITE_VERIFICACAO_ORIGEM)} para hashear no aparelho"
            )
            return

        base_remota = caminho_remoto.rstrip("/").rsplit("/", 1)[-1]
        no_destino = {}
        for nome, valor in aquisicao.hashes.items():
            chave = self._chave_relativa(nome, base_remota)
            # Arquivo gravado com nome alternativo é conferido pelo nome que
            # tem no aparelho.
            no_destino[aquisicao.nomes_trocados.get(chave, chave)] = valor

        self.log("    Verificando fidelidade da copia contra o aparelho...")
        na_origem, motivo = self.hashear_na_origem(caminho_remoto, sorted(no_destino))

        if na_origem is None:
            aquisicao.verificacao_na_origem = f"NAO realizada: {motivo}"
            self.log(f"    [RESSALVA] Fidelidade nao verificada na origem: {motivo}.")
            return

        divergentes = [
            nome
            for nome, valor in no_destino.items()
            if nome in na_origem and na_origem[nome] != valor
        ]
        ausentes = [nome for nome in no_destino if nome not in na_origem]

        aquisicao.divergencias = sorted(divergentes)
        aquisicao.verificacao_na_origem = (
            f"realizada: {len(na_origem)} arquivo(s) conferidos no aparelho, "
            f"{len(divergentes)} divergencia(s), {len(ausentes)} sem hash de origem"
        )

        if divergentes:
            self.log(
                f"    [ALERTA] {len(divergentes)} arquivo(s) DIVERGEM do aparelho: "
                f"{', '.join(divergentes[:5])}"
            )
        else:
            self.log(f"    Fidelidade confirmada: {len(na_origem)} arquivo(s) identicos a origem.")

    @staticmethod
    def _chave_relativa(caminho_relativo: str, base_remota: str) -> str:
        """Normaliza o caminho do destino para a raiz remota, sem o nome da pasta copiada."""
        partes = caminho_relativo.split("/")
        if partes and partes[0] == base_remota:
            partes = partes[1:]
        return "/".join(partes)

    def adquirir_caminho(
        self,
        caminho_remoto: str,
        destino_local: Path,
        pasta_caso: Optional[Path] = None,
        rotulo: Optional[str] = None,
        faixa_progresso: Optional[Tuple[int, int]] = None,
    ) -> ResultadoAquisicao:
        """
        Copia um caminho do aparelho **com prova de completude e integridade**:
        inventaria a origem, copia, reconcilia o que chegou contra o que
        existia, e calcula o SHA-256 de cada arquivo adquirido.

        O hash sai aqui, no próprio módulo, e não apenas no manifesto
        consolidado do fim: o valor precisa estar vinculado ao momento em
        que o dado saiu do aparelho.
        """
        rotulo = rotulo or destino_local.name

        # Espaco na estacao e conferido ANTES de comecar: copia truncada por
        # disco cheio chegaria ao exame como aquisicao incompleta, sem dizer
        # que a limitacao era da estacao, e nao do aparelho.
        tamanho_origem = self.estimar_tamanho_origem(caminho_remoto)
        tem_espaco, motivo_espaco = verificar_espaco(destino_local, tamanho_origem)
        if not tem_espaco:
            self.log(f"    [FALHA] {motivo_espaco}")
            return ResultadoAquisicao(
                copia=ResultadoPull(
                    caminho_remoto=caminho_remoto,
                    caminho_local=Path(destino_local),
                    codigo_saida=-1,
                    stdout="",
                    stderr=motivo_espaco,
                    arquivos_copiados=0,
                    bytes_copiados=0,
                    situacao=SituacaoPull.ERRO,
                ),
                inventario_indisponivel="aquisição não iniciada por falta de espaço",
            )

        if tamanho_origem:
            self.log(f"    Origem ocupa aproximadamente {formatar_bytes(tamanho_origem)}.")

        inventario = self.inventariar_origem(caminho_remoto)
        arquivos_origem = inventario.arquivos

        if inventario.disponivel:
            self.log(
                f"    Origem inventariada por '{inventario.metodo}': "
                f"{len(arquivos_origem)} arquivo(s) em {caminho_remoto}"
            )
        elif inventario.motivo_indisponivel:
            self.log(f"    Inventário da origem indisponível ({inventario.motivo_indisponivel}).")

        copia = self.copiar_caminho(caminho_remoto, destino_local, faixa_progresso)

        aquisicao = ResultadoAquisicao(
            copia=copia,
            arquivos_na_origem=len(arquivos_origem) if inventario.disponivel else None,
            inventario_indisponivel=inventario.motivo_indisponivel,
            metodo_inventario=inventario.metodo,
        )

        if arquivos_origem:
            obtidos = self._relativizar_obtidos(caminho_remoto, destino_local)
            aquisicao.faltantes = sorted(set(arquivos_origem) - set(obtidos))
            if aquisicao.faltantes and copia.situacao in (SituacaoPull.OK, SituacaoPull.ERRO):
                self._recuperar_faltantes(caminho_remoto, Path(destino_local), aquisicao)
            if aquisicao.faltantes:
                self.log(
                    f"    [RESSALVA] {len(aquisicao.faltantes)} arquivo(s) existiam na origem e "
                    "NÃO chegaram ao destino."
                )
                for nome in aquisicao.faltantes[:5]:
                    motivo = aquisicao.motivos_dos_faltantes.get(nome)
                    if motivo:
                        self.log(f"        {nome}: {motivo}")

        restricao = self.restricao_de_dados_de_app(caminho_remoto)
        if restricao:
            aquisicao.restricao_do_sistema = restricao
            self.log(f"    [RESSALVA] {restricao}")

        aquisicao.hashes = self._hashear_destino(destino_local)
        self.verificar_fidelidade(caminho_remoto, destino_local, aquisicao)
        if pasta_caso is not None:
            self._gravar_prova_aquisicao(pasta_caso, rotulo, caminho_remoto, aquisicao)
        return aquisicao

    def _recuperar_faltantes(
        self, caminho_remoto: str, destino_local: Path, aquisicao: ResultadoAquisicao
    ) -> None:
        """
        Lê, um a um, os arquivos que o `adb pull` não trouxe.

        O `adb pull` de uma pasta ABORTA INTEIRO no primeiro arquivo que
        não consegue gravar na estação. Medido em 09/10/2026 contra um
        `/data/data` com WhatsApp: um único arquivo de configuração, cujo
        caminho de destino passava do limite do Windows, derrubou a cópia
        dos 693 — e com ela o `msgstore.db`. Um arquivo irrelevante
        custava a evidência inteira.

        Cada faltante é lido por `exec-out cat` (fluxo binário, sem
        tradução de bytes). O que ainda assim não vier continua na lista
        de faltantes, agora com o motivo; a conferência de fidelidade
        contra o aparelho, logo depois, cobre também os recuperados.
        """
        base_remota = caminho_remoto.rstrip("/").rsplit("/", 1)[-1]
        raiz_local = destino_local / base_remota
        total = len(aquisicao.faltantes)
        self.log(
            f"    A cópia em bloco deixou {total} arquivo(s) para trás. "
            "Lendo cada um individualmente..."
        )

        restantes = []
        for relativo in aquisicao.faltantes:
            if self.cancelado:
                restantes.append(relativo)
                aquisicao.motivos_dos_faltantes[relativo] = "leitura cancelada pelo examinador"
                continue
            remoto = caminho_remoto.rstrip("/") + "/" + relativo
            local = raiz_local.joinpath(*relativo.split("/"))
            gravado_como = relativo
            if local.exists() or relativo.rsplit("/", 1)[-1] != _nome_aceito_no_windows(
                    relativo.rsplit("/", 1)[-1]):
                # O Windows não aceita o nome do aparelho: grava com nome
                # alternativo e anota a correspondência, em vez de perder o
                # arquivo (antes) ou sobrescrever o outro (nunca).
                local = _nome_livre(local)
                gravado_como = "/".join(relativo.split("/")[:-1] + [local.name])
            motivo = self._copiar_arquivo_avulso(remoto, local)
            if motivo:
                restantes.append(relativo)
                aquisicao.motivos_dos_faltantes[relativo] = motivo
            else:
                aquisicao.recuperados_um_a_um += 1
                if gravado_como != relativo:
                    aquisicao.nomes_trocados[gravado_como] = relativo
                    self.log(f"    [NOME ALTERADO] '{relativo}' gravado como '{local.name}': "
                             "o Windows não aceita o nome original nesta pasta.")

        aquisicao.faltantes = restantes
        self.log(
            f"    Leitura individual: {aquisicao.recuperados_um_a_um} recuperado(s), "
            f"{len(restantes)} ainda ausente(s)."
        )

        # A contagem em disco é a fonte da verdade, e mudou.
        arquivos = [a for a in destino_local.rglob("*") if a.is_file()]
        aquisicao.copia.arquivos_copiados = len(arquivos)
        aquisicao.copia.bytes_copiados = sum(a.stat().st_size for a in arquivos)
        if aquisicao.copia.situacao is SituacaoPull.ERRO and arquivos and not restantes:
            # O erro do ADB está preservado no stderr da cópia; o caminho,
            # porém, foi adquirido por inteiro pela segunda via.
            aquisicao.copia.situacao = SituacaoPull.OK

    def _copiar_arquivo_avulso(self, remoto: str, local: Path) -> str:  # noqa: C901
        """Copia um arquivo por fluxo binário. Devolve o motivo da falha, ou vazio."""
        if local.exists():
            # Android distingue maiúsculas de minúsculas; o Windows não.
            # Sobrescrever trocaria um arquivo adquirido por outro.
            return (
                "o destino já tem um arquivo de mesmo nome, diferindo só por "
                "maiúsculas/minúsculas — não sobrescrito"
            )
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            arquivo = open(local, "wb")
        except OSError as erro:
            return (
                f"a estação não pôde criar o arquivo de destino ({erro.strerror}); "
                f"o caminho tem {len(str(local))} caracteres"
            )
        with arquivo:
            resultado = self.adb.stream_binario(
                ["exec-out", f"cat {self.aspas_para_shell(remoto)} 2>/dev/null"],
                arquivo.write,
            )
        if resultado.codigo_saida != 0:
            try:
                local.unlink()
            except OSError:
                pass
            return f"a leitura individual falhou no aparelho (código {resultado.codigo_saida})"
        return ""

    @staticmethod
    def _relativizar_obtidos(caminho_remoto: str, destino_local: Path) -> List[str]:
        """
        Converte o que chegou ao destino para caminhos relativos à raiz
        remota, para poder confrontar com o inventário da origem.

        `adb pull /sdcard/DCIM destino` cria `destino/DCIM/...`, então o
        primeiro componente é descartado quando corresponde ao nome da
        pasta de origem.
        """
        base_remota = caminho_remoto.rstrip("/").rsplit("/", 1)[-1]
        obtidos = []
        for caminho in Path(destino_local).rglob("*"):
            if not caminho.is_file():
                continue
            partes = caminho.relative_to(destino_local).as_posix().split("/")
            if partes and partes[0] == base_remota:
                partes = partes[1:]
            obtidos.append("/".join(partes))
        return obtidos

    @staticmethod
    def _hashear_destino(destino_local: Path) -> dict:
        """SHA-256 de cada arquivo adquirido, no momento da aquisição."""
        hashes = {}
        for caminho in sorted(Path(destino_local).rglob("*")):
            if caminho.is_file():
                hashes[caminho.relative_to(destino_local).as_posix()] = calcular_sha256(caminho)
        return hashes

    def _gravar_prova_aquisicao(
        self, pasta_caso: Path, rotulo: str, caminho_remoto: str, aquisicao: ResultadoAquisicao
    ) -> None:
        """
        Grava, em `<caso>/aquisicao/`, o hash de cada arquivo e o relatório
        de reconciliação origem × destino.

        Fica fora das pastas de evidência de propósito: artefato produzido
        pela ferramenta não se mistura com o material extraído do aparelho.
        """
        pasta = Path(pasta_caso) / PASTA_AQUISICAO
        try:
            pasta.mkdir(parents=True, exist_ok=True)

            linhas_hash = [f"{valor} *{nome}" for nome, valor in aquisicao.hashes.items()]
            (pasta / f"{rotulo}.sha256").write_text(
                "\n".join(linhas_hash) + "\n", encoding="utf-8"
            )

            if aquisicao.arquivos_na_origem is None:
                motivo = aquisicao.inventario_indisponivel or "origem não inventariada"
                situacao_origem = f"NÃO VERIFICÁVEL ({motivo})"
            else:
                situacao_origem = f"{aquisicao.arquivos_na_origem} arquivo(s)"

            relatorio = [
                "RECONCILIAÇÃO DE AQUISIÇÃO",
                f"Módulo:              {self.id}",
                f"Origem (aparelho):   {caminho_remoto}",
                f"Destino:             {aquisicao.copia.caminho_local}",
                f"Arquivos na origem:  {situacao_origem}",
                f"Via do inventário:   {aquisicao.metodo_inventario or 'nenhuma (não inventariado)'}",
                f"Arquivos adquiridos: {aquisicao.copia.arquivos_copiados}",
                f"Bytes adquiridos:    {aquisicao.copia.bytes_copiados}",
                f"Desfecho da cópia:   {aquisicao.copia.situacao.value}",
                f"Completude:          {self._descrever_completude(aquisicao)}",
                f"Fidelidade:          {aquisicao.verificacao_na_origem or 'não avaliada'}",
            ]
            if aquisicao.divergencias:
                relatorio += [
                    "",
                    "ARQUIVOS CUJO CONTEUDO DIVERGE DO APARELHO (possivel corrupcao "
                    "na transferencia):",
                ]
                relatorio += [f"  - {nome}" for nome in aquisicao.divergencias]
            if aquisicao.faltantes:
                relatorio += ["", "ARQUIVOS QUE EXISTIAM NA ORIGEM E NÃO FORAM ADQUIRIDOS:"]
                relatorio += [f"  - {nome}" for nome in aquisicao.faltantes]
            if aquisicao.nomes_trocados:
                relatorio += [
                    "",
                    "ARQUIVOS GRAVADOS COM NOME ALTERADO (o Windows não aceita o nome do "
                    "aparelho; o conteúdo é o mesmo e foi conferido pelo hash):",
                ]
                relatorio += [f"  - no aparelho: {original}\n    na aquisição: {gravado}"
                              for gravado, original in sorted(aquisicao.nomes_trocados.items())]
            if aquisicao.restricao_do_sistema:
                relatorio += ["", "RESTRIÇÃO DO SISTEMA OPERACIONAL:", aquisicao.restricao_do_sistema]
            if aquisicao.copia.stderr:
                relatorio += ["", "SAÍDA DE ERRO DO ADB (evidência da tentativa):", aquisicao.copia.stderr]

            (pasta / f"{rotulo}_reconciliacao.txt").write_text(
                "\n".join(relatorio) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            self.log(f"    [AVISO] Não foi possível gravar a prova de aquisição: {exc}")

    @staticmethod
    def _descrever_completude(aquisicao: ResultadoAquisicao) -> str:
        completa = aquisicao.completa
        if aquisicao.inconsistente:
            return (
                "NÃO VERIFICÁVEL — o inventário da origem "
                f"({aquisicao.arquivos_na_origem}) é MENOR que o adquirido "
                f"({aquisicao.copia.arquivos_copiados}); o inventário não é confiável "
                "para este caminho"
            )
        if completa is None:
            return "NÃO VERIFICÁVEL — a origem não pôde ser inventariada"
        if aquisicao.arquivos_na_origem == 0:
            # Dizer "COMPLETA" quando não havia nada a adquirir sugere, a quem
            # lê o relatório, que algo foi obtido. O caminho existia e estava
            # vazio: é isso que precisa estar escrito.
            return "ORIGEM VAZIA — o caminho existe no aparelho e não continha arquivo algum"
        if completa:
            return "COMPLETA — todo arquivo inventariado na origem foi adquirido"
        return f"INCOMPLETA — {len(aquisicao.faltantes)} arquivo(s) faltando"

    @staticmethod
    def consolidar_reconciliacao(aquisicoes: List[ResultadoAquisicao]) -> dict:
        """
        Resume a verificação de completude de várias aquisições.

        `completude_verificavel=False` é uma informação em si: significa que
        a ferramenta não conseguiu inventariar a origem e, portanto, **não
        afirma** que a cópia está completa. Silenciar isso seria deixar o
        exame concluir completude que ninguém verificou.
        """
        divergentes = [nome for aquisicao in aquisicoes for nome in aquisicao.divergencias]
        faltantes = [nome for aquisicao in aquisicoes for nome in aquisicao.faltantes]
        # Aquisicao contraditoria nao conta como verificavel: seu inventario
        # ja se provou errado.
        verificaveis = [
            a for a in aquisicoes if a.arquivos_na_origem is not None and not a.inconsistente
        ]
        return {
            # `if verificaveis` e nao `or None`: uma origem inventariada com
            # ZERO arquivos e um fato verificado, e nao a ausencia de
            # verificacao. Confundir os dois inverte o sentido do relatorio.
            "arquivos_na_origem": (
                sum(a.arquivos_na_origem for a in verificaveis) if verificaveis else None
            ),
            "arquivos_faltantes": len(faltantes),
            "amostra_faltantes": faltantes[:20],
            "completude_verificavel": len(verificaveis) == len(aquisicoes) and bool(aquisicoes),
            "inventarios_inconsistentes": [
                a.copia.caminho_remoto for a in aquisicoes if a.inconsistente
            ],
            "arquivos_divergentes": len(divergentes),
            "amostra_divergentes": divergentes[:20],
            "fidelidade_verificada": bool(aquisicoes)
            and all(a.integra is not None for a in aquisicoes),
        }

    @staticmethod
    def consolidar_copias(resultados: List[ResultadoPull]) -> dict:
        """
        Resume uma lista de `ResultadoPull` nos números que o exame precisa
        para afirmar (ou negar) completude: quanto veio, de onde, e o que
        foi recusado.
        """
        return {
            "arquivos_copiados": sum(r.arquivos_copiados for r in resultados),
            "bytes_copiados": sum(r.bytes_copiados for r in resultados),
            "caminhos_com_dados": [r.caminho_remoto for r in resultados if r.sucesso],
            "caminhos_negados": [r.caminho_remoto for r in resultados if r.acesso_negado],
            "caminhos_com_erro": [
                r.caminho_remoto for r in resultados if r.situacao is SituacaoPull.ERRO
            ],
            "caminhos_inexistentes": [
                r.caminho_remoto for r in resultados if r.situacao is SituacaoPull.INEXISTENTE
            ],
            # Copia interrompida (cancelada ou expirada) e incompleta por
            # construcao: o que veio pode ser legitimo, mas o caminho NAO
            # foi adquirido por inteiro, e o exame precisa saber disso.
            "caminhos_interrompidos": [r.caminho_remoto for r in resultados if r.interrompida],
        }

    @staticmethod
    def consolidar_restricoes(aquisicoes: List[ResultadoAquisicao]) -> List[str]:
        """Restricoes do sistema operacional encontradas durante a aquisicao."""
        return sorted({a.restricao_do_sistema for a in aquisicoes if a.restricao_do_sistema})

    # ------------------------------------------------------------------
    # Utilitários compartilhados por extratores que consultam Content
    # Providers nativos (SMS, Call Log, ...) e precisam se adaptar quando o
    # acesso é negado.
    # ------------------------------------------------------------------
    def log_diagnostico_versao(self) -> Optional[int]:
        """
        Registra no log fabricante/modelo/versão do Android/API do
        aparelho e devolve o nível de API (SDK) como inteiro (ou `None` se
        não foi possível ler). Chamado no início de extrações que podem
        precisar adaptar sua estratégia conforme a versão do sistema (ex.:
        decidir se `adb backup` ainda é uma alternativa viável).
        """
        especs = self.device.obter_especificacoes()
        sdk: Optional[int] = None
        try:
            sdk = int(especs.versao_sdk.strip())
        except (ValueError, AttributeError):
            pass

        self.log(
            f"[*] Dispositivo: {especs.fabricante} {especs.modelo} — "
            f"Android {especs.versao_android or '?'} (API {especs.versao_sdk or '?'})"
        )
        return sdk

    def tentar_fallback_backup(
        self,
        sdk: Optional[int],
        candidatos: List[str],
        pasta_destino: Path,
        pasta_caso: Optional[Path] = None,
    ) -> List[Path]:
        """
        Tentativa best-effort de obter dados via `adb backup` quando o
        Content Provider correspondente negou acesso (ver
        `saida_indica_acesso_negado`). Só é tentado para pacotes
        efetivamente instalados no aparelho, evitando pedir confirmações
        de tela desnecessárias.

        Ver `ADBClient.backup_pacote` para as limitações (Android < 12,
        `allowBackup=true` no app-alvo, confirmação manual na tela).

        O `.ab` obtido é ABERTO antes de contar como dado. Um pacote que
        não permite backup devolve um arquivo de algumas centenas de bytes
        só com o próprio manifesto — maior que zero, e vazio. Contá-lo
        como "backup obtido" faria o módulo declarar sucesso sobre nada.
        """
        arquivos_gerados: List[Path] = []

        if sdk is not None and sdk >= NIVEL_API_ANDROID_12:
            self.log(
                "[*] 'adb backup' não tentado: a partir do Android 12 (API 31) a Google "
                "removeu esse recurso do sistema. Neste aparelho, a via para SMS e chamadas "
                "é o módulo 'Agenda, Chamadas e SMS por aplicativo agente'."
            )
            return arquivos_gerados

        candidatos_instalados = [pacote for pacote in candidatos if self.adb.pacote_instalado(pacote)]
        if not candidatos_instalados:
            self.log("[*] Nenhum app candidato para 'adb backup' foi encontrado instalado no aparelho.")
            return arquivos_gerados

        for pacote in candidatos_instalados:
            if self.cancelado:
                break
            caminho_ab = pasta_destino / f"backup_{pacote}.ab"
            self.log(
                f"[*] Tentando 'adb backup' de '{pacote}' como alternativa ao provider negado. "
                "A suíte confirma o pedido na tela do aparelho por comando; mantenha a tela "
                "DESBLOQUEADA. Se o pedido ficar parado na tela, toque em 'Fazer backup dos "
                "meus dados'."
            )
            if pasta_caso is not None:
                self.registrar_alteracao(
                    pasta_caso,
                    f"Toque no botão de confirmação do 'adb backup' de '{pacote}', na tela do "
                    "aparelho — dado por comando da suíte (input tap) ou, na falta dele, pelo "
                    "examinador.",
                    "O Android exige confirmação na tela do dispositivo para concluir o "
                    "backup. A interação se limita ao toque no botão de confirmação, sem acesso "
                    "a conteúdo, e foi a única via disponível após o Content Provider negar "
                    "acesso aos dados. O arquivo de saída do backup diz quem deu o toque.",
                )
            obtido = self.adb.backup_pacote(
                pacote, caminho_ab, chave_valor=pacote in backup_android.PACOTES_CHAVE_VALOR
            )
            if not obtido:
                self.log(
                    f"    -> Sem sucesso para '{pacote}' (app pode ter allowBackup=false, ou a "
                    "confirmação não foi feita a tempo)."
                )
                continue

            conteudo = backup_android.abrir(caminho_ab)
            if conteudo.cifrado:
                # Não dá para olhar dentro: fica, e fica dito que não foi lido.
                arquivos_gerados.append(caminho_ab)
                self.log(
                    f"    -> Backup de '{pacote}' obtido, porém CIFRADO (foi digitada senha "
                    "na tela). O conteúdo não foi verificado."
                )
            elif not conteudo.legivel:
                arquivos_gerados.append(caminho_ab)
                self.log(
                    f"    -> Backup de '{pacote}' obtido, mas não pôde ser aberto: "
                    f"{conteudo.motivo}. Preservado como veio."
                )
            elif not conteudo.arquivos_de_dados:
                try:
                    caminho_ab.unlink()
                except OSError:
                    pass
                self.log(
                    f"    -> O backup de '{pacote}' veio SEM DADOS (só o manifesto do pacote): "
                    "o aplicativo não entrega conteúdo por esta via. Arquivo descartado; a "
                    "tentativa está registrada."
                )
            else:
                arquivos_gerados.append(caminho_ab)
                self.log(
                    f"    -> Backup obtido: {caminho_ab.name}, com "
                    f"{len(conteudo.arquivos_de_dados)} arquivo(s) de dados."
                )

        return arquivos_gerados
