"""
Imagem bit-a-bit do volume selecionado: lê o dispositivo bruto pela API do
Windows (`CreateFileW`/`ReadFile`, via `ctypes` — sem dependência externa,
no mesmo espírito de `disk_client.py`) e grava o conteúdo, byte a byte, em
um arquivo `.img`.

É a contraparte da Extração Física do Android, e foi revisada contra os
mesmos três pontos que lá comprometiam a validade pericial do resultado —
todos presentes aqui, e dois deles capazes de apresentar como boa uma
evidência que não existe:

1. **Falha de abertura passava por sucesso.** `CreateFileW` devolve
   `INVALID_HANDLE_VALUE` quando não consegue abrir o volume (unidade
   retirada depois da checagem, volume em uso exclusivo, disco
   criptografado bloqueado). A comparação era feita contra
   `ctypes.c_void_p(-1).value` — `18446744073709551615` —, mas sem
   `restype` declarado o `ctypes` devolve o handle num `c_long`, isto é,
   `-1`. Os dois valores nunca são iguais, então o erro jamais era
   detectado: o código seguia, o `ReadFile` falhava no primeiro bloco, o
   laço quebrava com zero byte gravado e o módulo retornava **sucesso**
   com "Imagem física gerada (0.00 MB)". Agora os tipos de retorno e de
   argumento são declarados, e a checagem passa a ser capaz de detectar
   o erro que ela sempre disse checar.

2. **Erro de leitura era indistinguível de fim do volume.** O laço saía
   com `if not sucesso or bytes_lidos.value == 0`, misturando as duas
   coisas. Um setor defeituoso, uma falha de I/O ou um pendrive retirado
   no meio da cópia encerravam a leitura, e a imagem truncada era
   entregue como completa. `ReadFile` retornando falso é **erro**, e
   agora encerra a aquisição com falha explícita; só `sucesso` com zero
   byte lido é fim de volume.

3. **Nenhuma conferência de completude, e nenhum hash na aquisição.** O
   total lido não era comparado com nada, e o arquivo era gravado com
   `open(..., "wb")` puro, deixando o hash para uma releitura posterior.
   Agora o SHA-256 é calculado sobre os bytes no momento em que chegam
   (`EscritorComHash`), gravado em `<imagem>.sha256` antes de qualquer
   conclusão, e o total é conferido contra o tamanho real do volume.

O tamanho de referência vem de `IOCTL_DISK_GET_LENGTH_INFO`, e não do
`bytes_total` que a listagem de unidades já traz. A distinção importa: o
`bytes_total` vem de `GetDiskFreeSpaceExW` e é o espaço do **sistema de
arquivos**, sempre menor que o volume bruto. Usá-lo como referência faria
toda imagem correta parecer maior que o esperado — e, pela regra herdada
do Android, excesso é falha. A conferência acusaria justamente as
aquisições íntegras.

Ler o volume bruto exige acesso de baixo nível ao dispositivo, e por isso
este é o único dos quatro módulos de Computador que pede Administrador —
checado em `disponivel()`, para não descobrir depois de horas de cópia.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Optional, Tuple

from core.base_extractor import Perfil, ResultadoExtracao
from core.hashing import EscritorComHash, gravar_hash_avulso
from core.registry import registrar_extrator

from .. import disk_client
from .base import ComputadorExtractor

# As constantes de abertura de volume e o `kernel32_tipado()` vivem em
# `disk_client` — a camada de API do Windows desta plataforma. Ficavam
# aqui, e a deteccao de volume bloqueado precisou dos mesmos tipos: duas
# implementacoes do mesmo `argtypes` seria exatamente o modo de o defeito
# do handle truncado voltar por uma delas.
from ..disk_client import (
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    kernel32_tipado,
)

TAMANHO_BLOCO = 1024 * 1024  # 1 MiB por leitura

# Devolve o comprimento total do volume, em bytes. É o equivalente ao
# tamanho declarado da partição no Android — a referência de completude.
IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C

MARGEM_TOLERANCIA = 0.99  # imagem aceitável a partir de 99% do comprimento do volume

BLOCOS_ENTRE_AVISOS = 200


@registrar_extrator
class ImagemFisicaExtractor(ComputadorExtractor):
    id = "computador_imagem_fisica"
    nome_exibicao = "Imagem do Volume (Bit-a-Bit)"
    ordem = 90
    descricao = (
        "Gera uma imagem bit-a-bit (.img) do volume selecionado, lendo o dispositivo "
        "bruto pela API do Windows, com SHA-256 calculado durante a aquisição e "
        "conferência do tamanho ao final. Requer privilégios de Administrador."
    )
    requer_privilegio_root = True
    rotulo_privilegio = "requer administrador"

    # A primeira limitação corrige o nome que este módulo exibia — "Imagem
    # Física Completa" — que afirmava mais do que a operação entrega: o que
    # é lido é o volume da letra selecionada, não o disco.
    limitacoes_conhecidas = (
        "A imagem é do volume correspondente à letra selecionada, não do disco "
        "físico inteiro: não contém a tabela de partição, as demais partições, "
        "nem o espaço não alocado fora do volume.",
        "Áreas do disco que o sistema operacional não expõe pela letra de unidade "
        "não são alcançadas por esta leitura.",
        "A leitura é feita na unidade já montada pelo Windows. A ferramenta abre o "
        "volume somente para leitura e nada grava nele, mas não interpõe bloqueador "
        "de escrita e nada pode afirmar sobre o que o sistema operacional tenha "
        "escrito na unidade ao montá-la, antes desta execução.",
        "A imagem preserva o que o volume continha no momento da coleta. Cópia "
        "bit-a-bit não é sinônimo de recuperação integral: dado já sobrescrito "
        "pelo sistema de arquivos não é recuperado por ela.",
    )
    perfil_minimo = Perfil.DES

    def disponivel(self) -> Tuple[bool, str]:
        disponivel_base, motivo = super().disponivel()
        if not disponivel_base:
            return disponivel_base, motivo

        if not disk_client.usuario_e_administrador():
            return False, (
                "A imagem do volume exige privilégios de Administrador — execute o "
                "HexisForensics como Administrador para usar este módulo."
            )
        return True, ""

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        caminho_unidade = self.unidade_obrigatoria()
        pasta_fisica = pasta_caso / "physical"
        pasta_fisica.mkdir(parents=True, exist_ok=True)
        letra = caminho_unidade.rstrip("\\").rstrip(":")
        caminho_bruto = "\\\\.\\" + letra + ":"
        caminho_imagem = pasta_fisica / f"imagem_volume_{letra}.img"

        kernel32 = kernel32_tipado()

        self.log(f"[*] Abrindo dispositivo bruto '{caminho_bruto}' para leitura...")
        handle = kernel32.CreateFileW(
            caminho_bruto,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        if not handle or handle == INVALID_HANDLE_VALUE:
            erro = kernel32.GetLastError()
            mensagem = (
                f"Não foi possível abrir o volume '{caminho_bruto}' para leitura bruta "
                f"(erro do Windows {erro}). Nenhuma imagem foi gerada. Confirme que o "
                "processo está rodando como Administrador, que a unidade continua "
                "conectada e que não está bloqueada por criptografia ou por outro programa."
            )
            self.log(f"[FALHA] {mensagem}")
            return ResultadoExtracao(False, mensagem, detalhes={"acesso_negado": True})

        tamanho_volume = self._obter_tamanho_volume(kernel32, handle)
        if tamanho_volume:
            self.log(f"[*] Comprimento do volume: {self._formatar(tamanho_volume)}")
        else:
            self.log(
                "[RESSALVA] Não foi possível obter o comprimento do volume. A aquisição "
                "prossegue, mas sem conferência de completude do tamanho final."
            )

        erro_leitura: Optional[int] = None
        try:
            with open(caminho_imagem, "wb") as arquivo_saida:
                escritor = EscritorComHash(arquivo_saida)
                buffer = ctypes.create_string_buffer(TAMANHO_BLOCO)
                bytes_lidos = ctypes.c_uint32(0)
                blocos = 0

                self.log("\n[*] Iniciando a clonagem bit-a-bit do volume...")
                self.log("[*] Transmitindo blocos. AGUARDE (pode levar muito tempo)...")

                while not self.cancelado:
                    sucesso = kernel32.ReadFile(
                        handle, buffer, TAMANHO_BLOCO, ctypes.byref(bytes_lidos), None
                    )
                    # Erro e fim de volume deixam de ser a mesma condição.
                    # `ReadFile` falso é erro do dispositivo, e imagem
                    # truncada por erro nunca pode sair como completa.
                    if not sucesso:
                        erro_leitura = kernel32.GetLastError()
                        break
                    if bytes_lidos.value == 0:
                        break

                    escritor.escrever(buffer.raw[: bytes_lidos.value])
                    blocos += 1

                    if tamanho_volume:
                        self.progresso(
                            min(99, int(escritor.bytes_gravados / tamanho_volume * 100))
                        )
                    # Contagem por blocos, e não pelo resto da divisão do
                    # total: uma leitura curta desalinha o total e o aviso
                    # de progresso some sem que nada indique isso.
                    if blocos % BLOCOS_ENTRE_AVISOS == 0:
                        self.log(
                            f"  -> {self._formatar(escritor.bytes_gravados)} transmitidos..."
                        )

                bytes_gravados = escritor.bytes_gravados
                hash_imagem = escritor.hash_hex
        finally:
            kernel32.CloseHandle(handle)

        # --- Hash gravado antes de qualquer conclusão ---------------------
        caminho_hash = gravar_hash_avulso(caminho_imagem, hash_imagem)
        self.log(f"[*] SHA-256 do que foi gravado: {hash_imagem}")
        self.log(f"[*] Hash gravado em: {caminho_hash.name}")

        if erro_leitura is not None:
            mensagem = (
                f"Erro de leitura do volume após {self._formatar(bytes_gravados)} "
                f"(erro do Windows {erro_leitura}). A imagem está INCOMPLETA e não "
                "deve ser usada como cópia fiel do volume."
            )
            self.log(f"[FALHA] {mensagem}")
            return ResultadoExtracao(
                False,
                mensagem,
                caminho_saida=caminho_imagem,
                detalhes={
                    "incompleta": True,
                    "erro_windows": erro_leitura,
                    "bytes": bytes_gravados,
                    "esperado": tamanho_volume,
                    "sha256": hash_imagem,
                },
            )

        if self.cancelado:
            mensagem = (
                f"Extração cancelada pelo usuário após {self._formatar(bytes_gravados)}. "
                "A imagem está INCOMPLETA."
            )
            self.log(f"[!] {mensagem}")
            return ResultadoExtracao(
                False,
                mensagem,
                caminho_saida=caminho_imagem,
                detalhes={
                    "incompleta": True,
                    "cancelada": True,
                    "bytes": bytes_gravados,
                    "esperado": tamanho_volume,
                    "sha256": hash_imagem,
                },
            )

        completa, ressalva = self._conferir_tamanho(bytes_gravados, tamanho_volume)
        self.progresso(100)

        if not completa:
            self.log(f"[FALHA] {ressalva}")
            return ResultadoExtracao(
                False,
                ressalva,
                caminho_saida=caminho_imagem,
                detalhes={
                    "incompleta": True,
                    "bytes": bytes_gravados,
                    "esperado": tamanho_volume,
                    "sha256": hash_imagem,
                },
            )

        mensagem = (
            f"Imagem do volume gerada ({self._formatar(bytes_gravados)}). "
            f"SHA-256: {hash_imagem}"
        )
        detalhes = {
            "bytes": bytes_gravados,
            "esperado": tamanho_volume,
            "sha256": hash_imagem,
            "volume": caminho_bruto,
        }
        if ressalva:
            mensagem += f" | Ressalva: {ressalva}"
            self.log(f"[RESSALVA] {ressalva}")
            detalhes["copia_incompleta"] = ressalva

        self.log("[CONCLUÍDO] Imagem do volume finalizada e integridade registrada.")
        return ResultadoExtracao(
            True, mensagem, caminho_saida=caminho_imagem, detalhes=detalhes
        )

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------
    def _obter_tamanho_volume(self, kernel32, handle) -> Optional[int]:
        """
        Comprimento total do volume, em bytes, perguntado ao próprio
        dispositivo. Best effort: se o `IOCTL` não for atendido, a
        aquisição prossegue sem conferência de tamanho, e a ausência da
        verificação é declarada no resultado — nunca suprimida.
        """
        tamanho = ctypes.c_ulonglong(0)
        retornado = ctypes.c_uint32(0)
        try:
            sucesso = kernel32.DeviceIoControl(
                handle,
                IOCTL_DISK_GET_LENGTH_INFO,
                None,
                0,
                ctypes.byref(tamanho),
                ctypes.sizeof(tamanho),
                ctypes.byref(retornado),
                None,
            )
        except OSError:
            return None
        if not sucesso or retornado.value < ctypes.sizeof(tamanho) or tamanho.value <= 0:
            return None
        return tamanho.value

    @staticmethod
    def _conferir_tamanho(gravados: int, esperado: Optional[int]) -> Tuple[bool, str]:
        """
        Compara o gravado com o comprimento do volume. Devolve
        `(completa, ressalva)`.

        A regra é a mesma da extração física do Android, pela mesma razão.
        Falta pode vir de arredondamento do dispositivo; **excesso só pode
        vir de bytes que não são do volume**, e por isso é sempre fatal.
        Lá isso apareceu na primeira execução real, com a mensagem de
        diagnóstico do `dd` colada dentro da imagem.
        """
        if gravados == 0:
            return False, (
                "Nenhum byte foi lido do volume. Não há imagem: o arquivo gerado está "
                "vazio e não constitui cópia de coisa alguma."
            )

        if not esperado:
            return True, (
                "Comprimento do volume não pôde ser obtido do dispositivo; a completude "
                "da imagem não foi verificada."
            )

        if gravados == esperado:
            return True, ""

        if gravados > esperado:
            excedente = gravados - esperado
            return False, (
                f"Imagem MAIOR que o volume: {ImagemFisicaExtractor._formatar(gravados)} "
                f"contra {ImagemFisicaExtractor._formatar(esperado)} — {excedente} byte(s) "
                "a mais. Bytes que não pertencem ao volume entraram no fluxo. A imagem "
                "NÃO é cópia fiel e não deve ser usada como evidência."
            )

        proporcao = gravados / esperado
        if proporcao >= MARGEM_TOLERANCIA:
            return True, (
                f"Imagem com {proporcao:.2%} do comprimento do volume — diferença dentro "
                "da margem, mas convém conferir antes do uso pericial."
            )

        return False, (
            f"Imagem incompleta: {proporcao:.2%} do comprimento do volume "
            f"({ImagemFisicaExtractor._formatar(gravados)} de "
            f"{ImagemFisicaExtractor._formatar(esperado)})."
        )

    @staticmethod
    def _formatar(quantidade_bytes: int) -> str:
        """Bytes em unidade legível, para o log e para o texto do resultado."""
        valor = float(quantidade_bytes)
        if valor < 1024:
            return f"{int(valor)} B"
        for unidade in ("KiB", "MiB", "GiB", "TiB"):
            valor /= 1024
            if valor < 1024 or unidade == "TiB":
                return f"{valor:.2f} {unidade}"
        return f"{valor:.2f} TiB"
