"""
Wrapper de baixo nível para o binário ADB (Android Debug Bridge).

Centraliza em um único lugar o que antes era a função `executar_adb(...)`
duplicada em todos os 7 scripts originais, além de localizar o binário de
forma um pouco mais flexível (Windows: binario/adb.exe; Linux/Mac:
binario/adb ou PATH), já que a GUI pode rodar em outros sistemas durante
o desenvolvimento mesmo que o uso forense final seja tipicamente Windows.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Callable, List, Optional, Tuple

from core.instalacao import raiz_da_instalacao

# Sem isto, aberta pelo ícone (sem console), a suíte faz o Windows abrir
# uma janela preta de console para CADA comando do ADB: elas piscam ao
# fundo e a de um comando demorado (o bugreport) cobre a suíte — e
# fechá-la mata o comando no meio da coleta. Visto na primeira extração
# pelo atalho, em 24/10/2026.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class ResultadoStream:
    """Resultado de uma leitura binária em streaming vinda do dispositivo."""

    codigo_saida: int
    stderr: str
    bytes_lidos: int
    cancelado: bool = False

    @property
    def sucesso(self) -> bool:
        """
        Só é sucesso se o processo terminou bem, não foi cancelado e algo
        foi efetivamente lido. Um `dd` que retorna 0 sem produzir nenhum
        byte **não** é uma aquisição bem-sucedida.
        """
        return self.codigo_saida == 0 and not self.cancelado and self.bytes_lidos > 0


@dataclass
class ResultadoComando:
    """
    Resultado de um comando ADB de texto, com o erro em canal próprio.

    O motivo de existir: `executar()` devolvia a string
    `"Erro: tempo limite de execucao excedido"` pelo **mesmo canal** do
    stdout legítimo. Quem chamava não tinha como distinguir uma resposta do
    aparelho de uma falha da ferramenta — e `obter_propriedade("ro.product.manufacturer")`
    podia gravar "Erro de execucao: ..." no campo Fabricante do laudo.
    """

    codigo_saida: int
    stdout: str
    stderr: str
    expirou: bool = False

    @property
    def sucesso(self) -> bool:
        return self.codigo_saida == 0 and not self.expirou

    @property
    def motivo_falha(self) -> str:
        """Descrição da falha para log e para o registro do procedimento."""
        if self.sucesso:
            return ""
        if self.expirou:
            return "tempo limite de execução excedido"
        return self.stderr or f"o ADB retornou código {self.codigo_saida}"


class SituacaoPull(Enum):
    """
    Desfecho de uma copia `adb pull`, classificado a partir do codigo de
    saida e do stderr do ADB.

    Distinguir esses casos e o que separa "nao havia dado" de "o sistema
    negou o acesso" — duas conclusoes periciais completamente diferentes
    que, antes, terminavam ambas como um generico "sucesso".
    """

    OK = "ok"                          # copiou pelo menos um arquivo
    VAZIO = "vazio"                    # caminho existe no aparelho, mas sem arquivos
    INEXISTENTE = "inexistente"        # caminho nao existe no aparelho
    ACESSO_NEGADO = "acesso_negado"    # o Android recusou o acesso
    CANCELADO = "cancelado"            # o examinador interrompeu a copia
    EXPIRADO = "expirado"              # o ADB parou de responder
    ERRO = "erro"                      # qualquer outra falha do ADB


# Trechos que o `adb pull` escreve em stderr para cada tipo de recusa.
_MARCADORES_INEXISTENTE = ("no such file or directory", "does not exist")
_MARCADORES_NEGADO = ("permission denied", "operation not permitted", "securityexception")

# Falhas do `adb pull` ao GRAVAR NA ESTACAO. Trazem no texto "No such file
# or directory" ou "Permission denied" -- sobre o caminho LOCAL. Lidas
# pelos marcadores acima, viravam "caminho nao existe no aparelho": uma
# afirmacao sobre o dispositivo feita a partir de um erro do Windows.
# Medido em 09/10/2026, com um arquivo cujo caminho de destino passava do
# limite do sistema.
_MARCADORES_FALHA_LOCAL = ("cannot create", "failed to create directory")


@dataclass
class ResultadoPull:
    """
    Resultado auditavel de um `adb pull`.

    Guarda o que o ADB efetivamente disse (stdout e stderr) e o que
    efetivamente chegou no destino (arquivos e bytes contados em disco).
    A contagem local e a fonte da verdade: o texto do ADB e preservado
    como evidencia da tentativa, nao como prova do resultado.
    """

    caminho_remoto: str
    caminho_local: Path
    codigo_saida: int
    stdout: str
    stderr: str
    arquivos_copiados: int
    bytes_copiados: int
    situacao: SituacaoPull
    arquivos: list = field(default_factory=list)

    @property
    def sucesso(self) -> bool:
        """Só é sucesso se algum arquivo foi efetivamente copiado."""
        return self.situacao is SituacaoPull.OK

    @property
    def acesso_negado(self) -> bool:
        return self.situacao is SituacaoPull.ACESSO_NEGADO

    @property
    def interrompida(self) -> bool:
        """
        Copia que nao chegou ao fim por decisao do examinador ou por o ADB
        ter parado de responder.

        Precisa ser distinguida de uma copia que terminou: o material
        adquirido ate ali pode ser legitimo, mas a aquisicao daquele caminho
        esta INCOMPLETA por construcao, e o relatorio nao pode trata-la como
        concluida.
        """
        return self.situacao in (SituacaoPull.CANCELADO, SituacaoPull.EXPIRADO)

    def resumo(self) -> str:
        """Linha unica para log e para o relatorio do caso."""
        descricao = {
            SituacaoPull.OK: f"{self.arquivos_copiados} arquivo(s), {self.bytes_copiados} byte(s)",
            SituacaoPull.VAZIO: "caminho existe, porem sem arquivos",
            SituacaoPull.INEXISTENTE: "caminho nao existe no aparelho",
            SituacaoPull.ACESSO_NEGADO: "ACESSO NEGADO pelo Android",
            SituacaoPull.CANCELADO: (
                f"CANCELADA pelo examinador apos {self.arquivos_copiados} arquivo(s)"
            ),
            SituacaoPull.EXPIRADO: (
                f"INTERROMPIDA: o ADB parou de responder apos {self.arquivos_copiados} arquivo(s)"
            ),
            SituacaoPull.ERRO: f"ERRO do ADB (codigo {self.codigo_saida})",
        }[self.situacao]
        return f"{self.caminho_remoto} -> {descricao}"


class ADBClient:
    """
    Wrapper do binario ADB, opcionalmente **vinculado a um serial**.

    A vinculacao nao e um detalhe de conveniencia: sem `-s <serial>`, o ADB
    escolhe sozinho o unico dispositivo conectado — e, se houver mais de um,
    recusa o comando ou (pior, em alguns fluxos) opera sobre o aparelho
    errado. Numa pericia, isso significaria misturar dados de dois
    aparelhos no mesmo caso sem nenhum registro disso. Fixado o serial na
    abertura do caso, todo comando subsequente fala com aquele aparelho e
    com nenhum outro.
    """

    def __init__(self, caminho_binario: Optional[Path] = None, serial: Optional[str] = None):
        self.caminho_binario = caminho_binario or self._localizar_adb()
        self.serial = serial

    def definir_serial(self, serial: Optional[str]) -> None:
        """Fixa o aparelho do caso; todo comando passa a usar `-s <serial>`."""
        self.serial = serial

    @staticmethod
    def _localizar_adb() -> Path:
        # `binario/` fica ao lado do programa — do código-fonte ou do
        # executável. A raiz vem de `core.instalacao`, a única fonte.
        pasta_binario = raiz_da_instalacao() / "binario"
        nome_executavel = "adb.exe" if platform.system() == "Windows" else "adb"

        caminho_local = pasta_binario / nome_executavel
        if caminho_local.exists():
            return caminho_local

        caminho_no_path = shutil.which("adb")
        if caminho_no_path:
            return Path(caminho_no_path)

        # Mesmo sem existir ainda, devolve o caminho esperado: a checagem
        # explícita de disponibilidade é feita por `verificar_binario()`,
        # que gera a mensagem de erro amigável para o usuário.
        return caminho_local

    def verificar_binario(self) -> Tuple[bool, str]:
        if not self.caminho_binario.exists():
            return False, (
                f"O binário do ADB não foi encontrado em '{self.caminho_binario}'. "
                "Copie adb.exe (e AdbWinApi.dll / AdbWinUsbApi.dll no Windows) para a "
                "pasta 'binario/', ou instale o Android Platform Tools e garanta que "
                "'adb' esteja disponível no PATH do sistema."
            )
        return True, ""

    def executar_detalhado(
        self,
        argumentos: List[str],
        timeout: Optional[int] = None,
        vincular_serial: bool = True,
    ) -> ResultadoComando:
        """
        Executa um comando ADB devolvendo stdout, stderr e código de saída
        **separados**. É a forma correta para qualquer chamador que precise
        distinguir "o aparelho respondeu isto" de "o comando falhou".
        """
        try:
            resultado = subprocess.run(
                self._montar_comando(argumentos, vincular_serial),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=SEM_JANELA,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,
            )
            return ResultadoComando(
                codigo_saida=resultado.returncode,
                stdout=(resultado.stdout or "").strip(),
                stderr=(resultado.stderr or "").strip(),
            )
        except subprocess.TimeoutExpired:
            return ResultadoComando(-1, "", "tempo limite de execucao excedido", expirou=True)
        except OSError as exc:
            return ResultadoComando(-1, "", f"falha ao executar o ADB: {exc}")

    def executar(
        self,
        argumentos: List[str],
        timeout: Optional[int] = None,
        vincular_serial: bool = True,
    ) -> str:
        """
        Conveniência para comandos cujo chamador só quer o texto de saída.

        Em caso de falha devolve string **vazia**, nunca uma mensagem de
        erro travestida de dado do aparelho. Quem precisa saber o motivo da
        falha usa `executar_detalhado`.
        """
        return self.executar_detalhado(argumentos, timeout, vincular_serial).stdout

    def executar_stream_binario(self, argumentos: List[str], arquivo_saida: BinaryIO) -> str:
        """
        Executa um comando ADB despejando o stdout bruto (bytes) diretamente
        em `arquivo_saida` (já aberto em modo binário).

        Mantido por compatibilidade. Código novo deve preferir
        `stream_binario()`, que informa também o código de saída e a
        quantidade de bytes efetivamente lidos — informações sem as quais
        não é possível distinguir uma aquisição bem-sucedida de uma que
        gravou zero byte.
        """
        resultado = self.stream_binario(argumentos, arquivo_saida.write)
        return resultado.stderr

    def stream_binario(
        self,
        argumentos: List[str],
        ao_receber_bloco: Callable[[bytes], None],
        tamanho_bloco: int = 1024 * 1024,
        cancelado: Optional[Callable[[], bool]] = None,
    ) -> "ResultadoStream":
        """
        Executa um comando ADB lendo o stdout bruto em blocos e entregando
        cada bloco a `ao_receber_bloco` — que pode gravar em arquivo,
        alimentar um hash, contar bytes ou tudo isso ao mesmo tempo.

        Diferente da versão anterior (que redirecionava o stdout direto para
        o arquivo e devolvia só o stderr), aqui o código de saída do
        processo e o total de bytes lidos ficam disponíveis para quem chamou.
        Em aquisição forense isso não é detalhe: `dd` pode falhar, ser
        interrompido ou não produzir nada, e o comando ainda assim terminar
        sem escrever nada em stderr.

        Se `cancelado()` retornar True entre blocos, o processo é encerrado
        e o resultado vem marcado como cancelado — a leitura para onde está,
        sem esperar o fim de uma cópia que pode durar horas.
        """
        processo = subprocess.Popen(
            self._montar_comando(argumentos),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=SEM_JANELA,
        )

        bytes_lidos = 0
        foi_cancelado = False

        try:
            while True:
                if cancelado is not None and cancelado():
                    foi_cancelado = True
                    processo.kill()
                    break

                bloco = processo.stdout.read(tamanho_bloco)
                if not bloco:
                    break

                ao_receber_bloco(bloco)
                bytes_lidos += len(bloco)
        finally:
            if processo.stdout:
                processo.stdout.close()
            stderr_bruto = processo.stderr.read() if processo.stderr else b""
            if processo.stderr:
                processo.stderr.close()
            processo.wait()

        return ResultadoStream(
            codigo_saida=processo.returncode,
            stderr=stderr_bruto.decode("utf-8", errors="ignore").strip(),
            bytes_lidos=bytes_lidos,
            cancelado=foi_cancelado,
        )

    def versao(self) -> str:
        """
        Versao do binario ADB em uso, para o registro do procedimento.

        Faz parte do requisito de repetibilidade da ISO/IEC 27037: o
        comportamento do `adb pull`, do `exec-out` e do `backup` variou
        entre versoes, e um exame so e reproduzivel se essa versao constar
        do caso.
        """
        saida = self.executar(["version"], timeout=15, vincular_serial=False)
        primeira_linha = saida.splitlines()[0].strip() if saida.strip() else ""
        return primeira_linha or "(versao do ADB nao identificada)"

    def suporta_exec_out(self) -> bool:
        """
        Informa se o ADB local aceita `exec-out`.

        `adb shell` foi projetado para texto: em várias combinações de
        versão de ADB e sistema operacional ele traduz quebras de linha
        (0x0A vira 0x0D 0x0A) no fluxo de saída. Para texto isso é
        inofensivo; para uma imagem bit-a-bit é **corrupção silenciosa** —
        a extração termina "com sucesso", o arquivo tem tamanho plausível e
        os bytes estão adulterados. `exec-out` não faz essa tradução e é o
        canal correto para conteúdo binário.
        """
        saida = self.executar(["version"], timeout=15, vincular_serial=False)
        correspondencia = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)", saida, re.IGNORECASE)
        if not correspondencia:
            # Sem conseguir identificar a versão, assume-se o caminho seguro:
            # `exec-out` existe desde o ADB 1.0.32 (2015) e qualquer
            # Platform Tools em uso hoje é muito mais recente.
            return True

        versao = tuple(int(parte) for parte in correspondencia.groups())
        return versao >= (1, 0, 32)

    # Sem sinal nenhum do ADB por este tempo, a copia e considerada travada.
    # E um teto de INATIVIDADE, nao de duracao: uma copia legitima de 40
    # minutos segue emitindo progresso e nunca e interrompida por ele.
    SEGUNDOS_SEM_SINAL = 300

    def pull(
        self,
        caminho_remoto: str,
        caminho_local: Path,
        preservar_timestamps: bool = True,
        cancelado: Optional[Callable[[], bool]] = None,
        ao_progredir: Optional[Callable[[int], None]] = None,
        segundos_sem_sinal: Optional[int] = None,
    ) -> "ResultadoPull":
        """
        Copia recursivamente um caminho do dispositivo, de forma auditavel e
        **controlavel**.

        Tres garantias que a versao anterior nao dava, e que sao o que separa
        uma ferramenta de laboratorio de uma utilizavel em campo:

        1. **Cancelamento efetivo.** O processo e encerrado assim que
           `cancelado()` passa a devolver True. Antes, o `subprocess.run`
           bloqueava ate o fim: num aparelho de 128 GB, o botao "Cancelar"
           nao surtia efeito por dezenas de minutos.
        2. **Teto de inatividade.** Cabo ruim ou porta USB suspensa deixavam
           a aplicacao pendurada indefinidamente, sem diagnostico.
        3. **Progresso real.** O `adb pull` informa o percentual no stdout;
           ele e repassado ao chamador em vez de a barra andar so quando uma
           pasta inteira termina.

        Alem disso: `-a` preserva a data de modificacao original, sem a qual
        todo arquivo chegaria carimbado com a hora da pericia; e a contagem
        de arquivos e bytes e apurada EM DISCO, no destino, unico jeito de
        afirmar com seguranca que algo foi de fato adquirido.
        """
        destino = Path(caminho_local)
        destino.mkdir(parents=True, exist_ok=True)

        argumentos = ["pull"]
        if preservar_timestamps:
            argumentos.append("-a")
        argumentos += [caminho_remoto, str(destino)]

        limite_sem_sinal = segundos_sem_sinal or self.SEGUNDOS_SEM_SINAL
        try:
            codigo_saida, saida, erro, foi_cancelado, expirou = self._executar_copia(
                argumentos, cancelado, ao_progredir, limite_sem_sinal
            )
        except OSError as exc:
            codigo_saida, saida, erro = -1, "", f"Falha ao executar o ADB: {exc}"
            foi_cancelado = expirou = False

        arquivos = [caminho for caminho in destino.rglob("*") if caminho.is_file()]
        bytes_copiados = sum(caminho.stat().st_size for caminho in arquivos)

        if foi_cancelado:
            situacao = SituacaoPull.CANCELADO
        elif expirou:
            situacao = SituacaoPull.EXPIRADO
        else:
            situacao = self._classificar_pull(codigo_saida, erro, len(arquivos))

        return ResultadoPull(
            caminho_remoto=caminho_remoto,
            caminho_local=destino,
            codigo_saida=codigo_saida,
            stdout=saida.strip(),
            stderr=erro.strip(),
            arquivos_copiados=len(arquivos),
            bytes_copiados=bytes_copiados,
            situacao=situacao,
            arquivos=[caminho.relative_to(destino).as_posix() for caminho in arquivos],
        )

    def executar_longo(
        self,
        argumentos: List[str],
        cancelado: Optional[Callable[[], bool]] = None,
        ao_progredir: Optional[Callable[[int], None]] = None,
        segundos_sem_sinal: Optional[int] = None,
    ) -> "ResultadoComando":
        """
        Executa um comando ADB demorado sob controle do examinador.

        Mesmo mecanismo do `pull`: cancelavel a qualquer momento e com teto
        de inatividade. Serve a comandos que levam minutos e nao podem
        deixar a aplicacao pendurada -- `bugreport` e o caso tipico.
        """
        codigo, saida, erro, foi_cancelado, expirou = self._executar_copia(
            argumentos, cancelado, ao_progredir, segundos_sem_sinal or self.SEGUNDOS_SEM_SINAL
        )
        if foi_cancelado:
            erro = (erro + "\ncomando cancelado pelo examinador").strip()
        return ResultadoComando(
            codigo_saida=codigo, stdout=saida, stderr=erro, expirou=expirou
        )

    def _executar_copia(self, argumentos, cancelado, ao_progredir, limite_sem_sinal):
        """
        Roda o processo drenando stdout e stderr em paralelo, para poder
        vigia-lo enquanto ele trabalha.

        Os dois fluxos sao lidos por threads proprias: se ficassem na mesma
        linha de execucao, o buffer de um encheria enquanto o outro fosse
        lido, e o ADB travaria esperando espaco -- o classico impasse de
        pipe. O laco principal fica livre para checar cancelamento e
        inatividade a cada fracao de segundo.
        """
        processo = subprocess.Popen(
            self._montar_comando(argumentos),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=SEM_JANELA,
        )

        coletado = {"stdout": [], "stderr": []}
        ultimo_sinal = [time.monotonic()]

        def drenar(fluxo, chave):
            descritor = fluxo.fileno()
            while True:
                try:
                    bloco = os.read(descritor, 4096)
                except OSError:
                    break
                if not bloco:
                    break
                coletado[chave].append(bloco)
                ultimo_sinal[0] = time.monotonic()
                if chave == "stdout" and ao_progredir is not None:
                    percentual = self._percentual_do_adb(bloco)
                    if percentual is not None:
                        ao_progredir(percentual)

        leitores = [
            threading.Thread(target=drenar, args=(processo.stdout, "stdout"), daemon=True),
            threading.Thread(target=drenar, args=(processo.stderr, "stderr"), daemon=True),
        ]
        for leitor in leitores:
            leitor.start()

        foi_cancelado = expirou = False
        while processo.poll() is None:
            if cancelado is not None and cancelado():
                foi_cancelado = True
                processo.kill()
                break
            if time.monotonic() - ultimo_sinal[0] > limite_sem_sinal:
                expirou = True
                processo.kill()
                break
            time.sleep(0.2)

        processo.wait()
        for leitor in leitores:
            leitor.join(timeout=5)
        for fluxo in (processo.stdout, processo.stderr):
            if fluxo:
                fluxo.close()

        decodificar = lambda blocos: b"".join(blocos).decode("utf-8", errors="ignore")
        return (
            processo.returncode,
            decodificar(coletado["stdout"]),
            decodificar(coletado["stderr"]),
            foi_cancelado,
            expirou,
        )

    @staticmethod
    def _percentual_do_adb(bloco: bytes) -> Optional[int]:
        """Le o percentual das linhas de progresso do `adb pull` (ex.: `[ 34%]`)."""
        texto = bloco.decode("utf-8", errors="ignore")
        encontrados = re.findall(r"\[\s*(\d{1,3})%\]", texto)
        return int(encontrados[-1]) if encontrados else None

    @staticmethod
    def _classificar_pull(codigo_saida: int, stderr: str, arquivos_copiados: int) -> "SituacaoPull":
        """
        Traduz codigo de saida + stderr do ADB em uma situacao periciamente
        util.

        A ordem importa: mesmo com codigo de saida 0, se nada chegou ao
        destino a copia **nao** foi bem-sucedida. E um `Permission denied`
        e classificado como tal ainda que algum arquivo tenha vindo junto —
        o exame precisa saber que parte do conteudo foi recusada.
        """
        stderr_normalizado = (stderr or "").lower()

        if any(marcador in stderr_normalizado for marcador in _MARCADORES_FALHA_LOCAL):
            # Vem antes de tudo: o problema e da estacao, e nada se pode
            # afirmar sobre o aparelho a partir dele.
            return SituacaoPull.OK if arquivos_copiados and codigo_saida == 0 else SituacaoPull.ERRO
        if any(marcador in stderr_normalizado for marcador in _MARCADORES_NEGADO):
            return SituacaoPull.ACESSO_NEGADO
        if any(marcador in stderr_normalizado for marcador in _MARCADORES_INEXISTENTE):
            return SituacaoPull.INEXISTENTE
        if codigo_saida != 0:
            return SituacaoPull.ERRO
        if arquivos_copiados == 0:
            return SituacaoPull.VAZIO
        return SituacaoPull.OK

    def _montar_comando(self, argumentos: List[str], vincular_serial: bool = True) -> List[str]:
        """
        Monta a linha de comando completa do ADB — ponto unico por onde
        todo comando passa.

        `vincular_serial=False` e usado apenas por comandos que sao, por
        natureza, globais (ex.: `adb devices`, `adb version`), e nao se
        dirigem a um aparelho especifico.
        """
        comando = [str(self.caminho_binario)]
        if vincular_serial and self.serial:
            comando += ["-s", self.serial]
        return comando + argumentos

    def listar_dispositivos(self) -> List[Tuple[str, str]]:
        """Retorna uma lista de tuplas (serial, status) dos dispositivos detectados."""
        saida = self.executar(["devices"], vincular_serial=False)
        dispositivos: List[Tuple[str, str]] = []
        for linha in saida.splitlines()[1:]:
            partes = linha.split()
            if len(partes) >= 2:
                dispositivos.append((partes[0], partes[1]))
        return dispositivos

    def obter_propriedade(self, propriedade: str) -> str:
        return self.executar(["shell", "getprop", propriedade])

    def pacote_instalado(self, nome_pacote: str) -> bool:
        """
        Verifica se um pacote esta instalado no aparelho (nao exige root).

        A comparacao e EXATA, linha a linha. `pm list packages <nome>` filtra
        por substring, entao a checagem ingenua `"package:<nome>" in saida`
        casava com qualquer pacote de nome mais longo: pedir "com.whatsapp"
        num aparelho que so tem "com.whatsapp.w4b" (WhatsApp Business)
        retornava True. O relatorio afirmaria que a pessoa usava WhatsApp
        quando ela usava outro aplicativo -- conclusao falsa sobre o que o
        aparelho continha.
        """
        saida = self.executar(["shell", "pm", "list", "packages", nome_pacote])

        for linha in saida.splitlines():
            linha = linha.strip()
            if not linha.startswith("package:"):
                continue

            instalado = linha[len("package:"):].strip()
            # Variantes do comando (-f, -U) acrescentam caminho ou uid:
            # "package:/data/app/base.apk=com.exemplo  uid:10123"
            instalado = instalado.split()[0] if instalado.split() else ""
            if "=" in instalado:
                instalado = instalado.rsplit("=", 1)[-1]

            if instalado == nome_pacote:
                return True

        return False

    # Botão "Fazer backup de meus dados" da tela de confirmação do Android.
    _BOTAO_CONFIRMAR_BACKUP = re.compile(
        r'resource-id="com\.android\.backupconfirm:id/button_allow"[^>]*'
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    )

    def _confirmar_backup_na_tela(self, parar: threading.Event, toques: list) -> None:
        """
        Enquanto um `adb backup` aguarda, confirma por comando a tela que o
        Android abre no aparelho.

        O backup só anda com o toque em "Fazer backup de meus dados", e o
        pedido aparece minutos depois do início da extração, quando o
        examinador já não está olhando para o aparelho: o tempo esgotava e
        as chamadas simplesmente não vinham. A suíte passa a dar o toque.

        O botão é localizado LENDO A TELA (pelo identificador dele), e não
        por coordenada fixa: a posição muda com o modelo e a resolução. Se
        a tela não for a de confirmação, ou o botão não for achado, nada é
        tocado — e o examinador ainda pode confirmar à mão.

        Cada toque dado é anotado em `toques`, para o registro da saída.
        """
        while not parar.wait(1.0):
            try:
                foco = self.executar(["shell", "dumpsys window | grep mCurrentFocus"], timeout=10)
                if "backupconfirm" not in foco:
                    continue
                tela = self.executar(["exec-out", "uiautomator", "dump", "/dev/tty"], timeout=20)
                botao = self._BOTAO_CONFIRMAR_BACKUP.search(tela)
                if not botao:
                    continue
                x1, y1, x2, y2 = (int(valor) for valor in botao.groups())
                x, y = (x1 + x2) // 2, (y1 + y2) // 2
                self.executar(["shell", "input", "tap", str(x), str(y)], timeout=10)
                toques.append((x, y))
                parar.wait(3.0)
            except Exception:
                # A confirmação automática é ajuda, não requisito: qualquer
                # tropeço aqui não pode derrubar o backup em andamento.
                continue

    def backup_pacote(
        self,
        pacote: str,
        caminho_saida: Path,
        timeout: int = 90,
        chave_valor: bool = False,
        confirmar_na_tela: bool = True,
    ) -> bool:
        """
        Tenta um backup local (`adb backup`) de um único pacote, sem exigir
        root — usado como alternativa quando um Content Provider nega
        acesso (ex.: SMS/Call Log em dispositivos sem root).

        Duas limitações importantes, ambas fora do controle deste código:
          1. Só funciona em Android < 12 (API 31): a Google removeu esse
             recurso do sistema a partir do Android 12.
          2. Exige o app de destino ter `android:allowBackup="true"` no
             manifesto — muitos apps de mensagens/discador mais recentes
             desativam isso por padrão, e o comando falha silenciosamente
             gerando um arquivo vazio.
          3. `adb backup` pede confirmação na tela do aparelho ("Fazer
             backup dos meus dados"). Com `confirmar_na_tela`, a suíte dá
             esse toque por comando (ver `_confirmar_backup_na_tela`); se
             não conseguir, o comando espera o toque manual até o timeout.

        `chave_valor` acrescenta `-keyvalue`: há pacotes do sistema — o
        do registro de chamadas é um — cujo agente só responde ao backup
        chave/valor, e sem a opção o arquivo sai sem dado nenhum.

        O `.ab` é preservado como veio; quem o lê é `core.backup_android`,
        em memória. A saída do comando (stdout e stderr) é gravada ao lado,
        em `<arquivo>_saida.txt`: era descartada, e é evidência do que o
        ADB respondeu.
        """
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        argumentos = ["backup", "-f", str(caminho_saida), "-noapk"]
        if chave_valor:
            argumentos.append("-keyvalue")
        argumentos.append(pacote)
        caminho_log = caminho_saida.with_name(caminho_saida.stem + "_saida.txt")
        parar_confirmacao = threading.Event()
        toques: list = []
        if confirmar_na_tela:
            threading.Thread(
                target=self._confirmar_backup_na_tela,
                args=(parar_confirmacao, toques),
                daemon=True,
            ).start()
        try:
            processo = subprocess.run(
                self._montar_comando(argumentos),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=SEM_JANELA,
                timeout=timeout,
            )
            saida = (getattr(processo, "stdout", b"") or b"") + (
                getattr(processo, "stderr", b"") or b""
            )
            texto = (
                f"comando: adb {' '.join(argumentos)}\n"
                f"codigo de saida: {processo.returncode}\n"
                + saida.decode("utf-8", errors="replace")
            )
        except subprocess.TimeoutExpired:
            texto = (
                f"comando: adb {' '.join(argumentos)}\n"
                f"tempo limite de {timeout}s excedido — a confirmação na tela do aparelho "
                "não foi feita a tempo.\n"
            )
            processo = None
        except OSError as erro:
            texto = f"comando: adb {' '.join(argumentos)}\nfalha ao executar o ADB: {erro}\n"
            processo = None
        parar_confirmacao.set()
        self.toques_de_confirmacao = list(toques)
        if toques:
            texto += (
                "confirmacao na tela do aparelho: feita POR COMANDO pela suite "
                "(input tap), no botao 'button_allow' lido da propria tela, em "
                + ", ".join(f"({x},{y})" for x, y in toques) + "\n"
            )
        elif confirmar_na_tela:
            texto += (
                "confirmacao na tela do aparelho: a suite NAO tocou em nada (a tela de "
                "confirmacao nao foi vista ou o botao nao foi localizado)\n"
            )
        try:
            caminho_log.write_text(texto, encoding="utf-8")
        except OSError:
            pass
        if processo is None:
            # Arquivo parcial de uma tentativa que expirou não é backup.
            try:
                caminho_saida.unlink()
            except OSError:
                pass
            return False

        if not caminho_saida.exists():
            return False

        # Backup vazio nao e evidencia: e uma tentativa frustrada, e a
        # tentativa ja esta registrada no log. Deixar um .ab de 0 byte na
        # pasta do caso (e no manifesto de hashes) sugere, a quem examina,
        # que existe um backup — quando nao existe conteudo algum.
        if caminho_saida.stat().st_size == 0:
            try:
                caminho_saida.unlink()
            except OSError:
                pass
            return False

        return True
