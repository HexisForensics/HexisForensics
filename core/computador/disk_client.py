"""
Wrapper de baixo nível para detecção de unidades de disco no Windows.

Diferente do Android/iOS (que falam com o dispositivo via um binário/SDK
externo — ADB, pymobiledevice3), aqui o "dispositivo" é uma unidade de
disco já montada pelo próprio Windows (letra de unidade). Não existe
executável externo: usamos só a API do Windows via `ctypes`, que já vem
com o Python — nenhuma dependência nova.

Funciona apenas no Windows (decisão de escopo: discos/computadores
periciados são majoritariamente Windows). Em qualquer outro SO,
`listar_unidades()` devolve uma lista vazia e `disponivel()` explica o
motivo — o módulo nunca derruba a aplicação por rodar fora do Windows
(ex.: durante desenvolvimento/testes em Linux/Mac).
"""

from __future__ import annotations

import ctypes
import platform
import string
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Constantes de GetDriveTypeW (API do Windows) — ver documentação da
# Microsoft (winbase.h). Replicadas aqui porque não fazem parte do
# `ctypes` nem de nenhuma biblioteca padrão do Python.
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

_DESCRICAO_TIPO = {
    DRIVE_UNKNOWN: "Desconhecido",
    DRIVE_NO_ROOT_DIR: "Sem unidade",
    DRIVE_REMOVABLE: "Removível (USB/externo)",
    DRIVE_FIXED: "Fixo (interno)",
    DRIVE_REMOTE: "Rede",
    DRIVE_CDROM: "CD/DVD",
    DRIVE_RAMDISK: "RAM Disk",
}


# --- Acesso bruto ao volume ------------------------------------------
# Usado tanto pela deteccao de volume bloqueado (aqui) quanto pelo extrator
# de Imagem do Volume. Uma implementacao so.
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

ERRO_ACESSO_NEGADO = 5  # ERROR_ACCESS_DENIED

# O primeiro setor de um volume traz, no offset 3, o campo OEM ID: oito
# bytes que num volume NTFS saudavel dizem "NTFS    ". Num volume cifrado
# com BitLocker eles dizem "-FVE-FS-" (Full Volume Encryption File System).
OFFSET_OEM_ID = 3
TAMANHO_OEM_ID = 8
ASSINATURA_BITLOCKER = "-FVE-FS-"

# Estados de leitura de um volume. Existem porque "nao consegui ler" e
# "esta cifrado" sao coisas diferentes, e afirmar a segunda sem a
# assinatura seria a ferramenta concluindo o que nao verificou.
BLOQUEIO_NENHUM = ""
BLOQUEIO_BITLOCKER = "bitlocker"
BLOQUEIO_INDETERMINADO = "indeterminado"
BLOQUEIO_ILEGIVEL = "ilegivel"


@dataclass
class UnidadeDisco:
    """Uma unidade de disco detectada no Windows."""

    letra: str
    caminho: str
    tipo_codigo: int
    tipo_descricao: str
    rotulo: str = ""
    sistema_arquivos: str = ""
    bytes_livres: int = 0
    bytes_total: int = 0
    # Codigo de erro do Windows quando `GetVolumeInformationW` falhou (0 =
    # nao falhou). Antes era descartado, e com ele ia embora a unica pista
    # de que a unidade existe mas nao pode ser lida.
    codigo_erro_volume: int = 0
    # Campo OEM ID lido do primeiro setor, quando foi possivel le-lo.
    oem_id: str = ""
    bloqueio: str = BLOQUEIO_NENHUM


def rodando_no_windows() -> bool:
    return platform.system() == "Windows"


def usuario_e_administrador() -> bool:
    """
    Verifica se o processo atual está rodando com privilégios de
    Administrador — usado pelo extrator de Imagem Física, que precisa de
    acesso exclusivo de baixo nível ao volume bruto. Fora do Windows,
    sempre devolve `False` (não há "Administrador" a checar).
    """
    if not rodando_no_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except OSError:
        return False


def kernel32_tipado():
    """
    `kernel32` com os tipos declarados.

    Sem `restype`/`argtypes`, o `ctypes` assume `c_int` no retorno e
    converte os argumentos por conta própria. Num Windows de 64 bits isso
    trunca handles e faz `CreateFileW` devolver `-1` onde o chamador
    compara com `INVALID_HANDLE_VALUE` — foi assim que falha de abertura
    virou "Imagem física gerada (0.00 MB)" com sucesso. Declarar os tipos
    é o que torna a checagem de erro capaz de detectar erro.
    """
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.ReadFile.restype = ctypes.c_int
    kernel32.ReadFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    kernel32.DeviceIoControl.restype = ctypes.c_int
    kernel32.DeviceIoControl.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


def ler_oem_id_do_volume(letra: str) -> Optional[str]:
    """
    Lê o campo OEM ID do primeiro setor do volume (8 bytes a partir do
    offset 3) e devolve-o como texto, ou `None` quando o volume não pôde
    ser aberto para leitura bruta.

    `None` significa **não sei**, nunca "não é BitLocker": abrir o volume
    bruto exige privilégio de Administrador, e a suíte pode estar rodando
    sem ele. Distinguir as duas coisas é o motivo de esta função existir.

    Nada é gravado: o volume é aberto só para leitura, e são lidos 512
    bytes do início. Não substitui bloqueador de escrita — não impede o
    que o Windows já tenha escrito ao montar a unidade.
    """
    if not rodando_no_windows():
        return None

    kernel32 = kernel32_tipado()
    handle = kernel32.CreateFileW(
        f"{chr(92)}{chr(92)}.{chr(92)}{letra}:",
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle is None or handle == INVALID_HANDLE_VALUE:
        return None

    try:
        buffer = ctypes.create_string_buffer(512)
        lidos = ctypes.c_uint32(0)
        sucesso = kernel32.ReadFile(handle, buffer, 512, ctypes.byref(lidos), None)
        if not sucesso or lidos.value < OFFSET_OEM_ID + TAMANHO_OEM_ID:
            return None
        bruto = buffer.raw[OFFSET_OEM_ID : OFFSET_OEM_ID + TAMANHO_OEM_ID]
        return bruto.decode("ascii", errors="replace")
    finally:
        kernel32.CloseHandle(handle)


def diagnosticar_bloqueio(
    letra: str, codigo_erro: int, leitor=None
) -> Tuple[str, str]:
    """
    Devolve `(bloqueio, oem_id)` para um volume cuja leitura de rótulo
    falhou. Só é chamada quando `GetVolumeInformationW` falhou — volume
    que responde normalmente não é aberto em modo bruto à toa.

    A regra é a mesma do resto da suíte: só afirma BitLocker quando leu a
    assinatura. Sem conseguir ler o setor, o estado é INDETERMINADO, e a
    tela diz isso com todas as letras em vez de exibir 0 GB em silêncio.
    """
    if codigo_erro == 0:
        return BLOQUEIO_NENHUM, ""

    # `leitor` existe para o teste: sem ele, exercitar o caminho do
    # BitLocker exigiria um volume cifrado ligado à máquina, e o caminho
    # ficaria sem execução nenhuma até o dia em que valesse um laudo.
    oem_id = (leitor or ler_oem_id_do_volume)(letra)
    if oem_id is None:
        return BLOQUEIO_INDETERMINADO, ""
    if oem_id == ASSINATURA_BITLOCKER:
        return BLOQUEIO_BITLOCKER, oem_id
    return BLOQUEIO_ILEGIVEL, oem_id


def descrever_bloqueio(unidade: "UnidadeDisco") -> str:
    """
    Frase que explica ao examinador o que está acontecendo com a unidade.
    Vive aqui, e não na UI, porque é conhecimento sobre o alvo — a tela
    só a exibe.
    """
    if unidade.bloqueio == BLOQUEIO_BITLOCKER:
        return (
            "Volume cifrado com BitLocker e BLOQUEADO. O conteúdo no disco é cifra: "
            "a imagem bit-a-bit é adquirível e íntegra, mas o dado só é interpretável "
            "com a chave. Se o protetor for o TPM da máquina de origem, o disco "
            "retirado não é destrancado por ela — a chave ficou na placa-mãe."
        )
    if unidade.bloqueio == BLOQUEIO_ILEGIVEL:
        return (
            f"O Windows não conseguiu ler o sistema de arquivos (erro "
            f"{unidade.codigo_erro_volume}). O primeiro setor traz "
            f"'{unidade.oem_id}', que não é a assinatura do BitLocker. O volume "
            "pode estar corrompido, não formatado ou usar sistema de arquivos que "
            "este Windows não monta."
        )
    if unidade.bloqueio == BLOQUEIO_INDETERMINADO:
        return (
            f"O Windows não conseguiu ler o sistema de arquivos (erro "
            f"{unidade.codigo_erro_volume}), e a suíte NÃO conseguiu abrir o volume "
            "para identificar a causa — leitura bruta exige Administrador. O motivo "
            "do bloqueio permanece indeterminado: execute como Administrador para "
            "que a ferramenta possa dizer se é BitLocker."
        )
    return ""


def listar_unidades(apenas_removiveis: bool = False) -> List[UnidadeDisco]:
    """
    Lista as unidades de disco visíveis no Windows (letra, tipo, rótulo,
    sistema de arquivos e espaço livre/total). Fora do Windows, devolve
    lista vazia — ver `disponivel()` em `extractors/base.py` para a
    mensagem explicativa mostrada ao usuário nesse caso.

    `apenas_removiveis=True` filtra só unidades removíveis (USB/externo) —
    útil para não listar o próprio disco C:\\ do examinador por engano.
    """
    if not rodando_no_windows():
        return []

    unidades: List[UnidadeDisco] = []
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    bitmask = kernel32.GetLogicalDrives()

    for indice, letra in enumerate(string.ascii_uppercase):
        if not (bitmask & (1 << indice)):
            continue

        caminho = f"{letra}:\\"
        tipo_codigo = kernel32.GetDriveTypeW(caminho)
        if apenas_removiveis and tipo_codigo != DRIVE_REMOVABLE:
            continue

        rotulo, sistema_arquivos, codigo_erro = _obter_rotulo_e_sistema_arquivos(
            caminho
        )
        bytes_livres, bytes_total = _obter_espaco(caminho)
        # Volume que responde normalmente não é aberto em modo bruto: só
        # se a leitura do rótulo falhou é que vale investigar a causa.
        bloqueio, oem_id = diagnosticar_bloqueio(letra, codigo_erro)

        unidades.append(
            UnidadeDisco(
                letra=letra,
                caminho=caminho,
                tipo_codigo=tipo_codigo,
                tipo_descricao=_DESCRICAO_TIPO.get(tipo_codigo, "Desconhecido"),
                rotulo=rotulo,
                sistema_arquivos=sistema_arquivos,
                bytes_livres=bytes_livres,
                bytes_total=bytes_total,
                codigo_erro_volume=codigo_erro,
                oem_id=oem_id,
                bloqueio=bloqueio,
            )
        )

    return unidades


def _obter_rotulo_e_sistema_arquivos(caminho: str) -> Tuple[str, str, int]:
    """
    Lê o rótulo do volume (ex.: 'PENDRIVE_JOAO') e o sistema de arquivos
    (ex.: 'NTFS'), mais o código de erro do Windows quando a leitura falha.

    O código de erro é devolvido porque falhar aqui não é detalhe: um
    volume BitLocker bloqueado responde ERROR_ACCESS_DENIED, e a versão
    anterior desta função descartava esse fato e devolvia rótulo vazio —
    indistinguível de um pendrive sem nome. Quem chama é que decide o que
    fazer com o erro (ver `diagnosticar_bloqueio`).
    """
    buffer_rotulo = ctypes.create_unicode_buffer(261)
    buffer_sistema = ctypes.create_unicode_buffer(261)
    try:
        sucesso = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(caminho),
            buffer_rotulo,
            ctypes.sizeof(buffer_rotulo),
            None,
            None,
            None,
            buffer_sistema,
            ctypes.sizeof(buffer_sistema),
        )
        if not sucesso:
            return "", "", ctypes.GetLastError()  # type: ignore[attr-defined]
        return buffer_rotulo.value, buffer_sistema.value, 0
    except OSError as erro:
        # Unidade sem mídia (ex.: leitor de CD vazio) — não é um erro fatal,
        # mas o código continua sendo devolvido: some do fluxo de exceção,
        # não do registro.
        return "", "", getattr(erro, "winerror", 0) or 0


# ---------------------------------------------------------------------------
# Identificação da mídia
# ---------------------------------------------------------------------------
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400

# STORAGE_BUS_TYPE: por onde a mídia fala com a estação. É o que permite
# dizer se o número de série veio do disco ou de um adaptador no caminho.
_BARRAMENTOS = {
    1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "IEEE 1394", 6: "Fibre Channel",
    7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD",
    13: "MMC", 14: "Virtual", 15: "Virtual (arquivo)", 17: "NVMe",
}
BARRAMENTO_USB = "USB"


@dataclass
class IdentidadeMidia:
    """
    O que a mídia declara de si mesma, e o que o volume carrega.

    São duas identidades distintas, e nenhuma substitui a outra:

    - `numero_serie`, `fabricante` e `produto` vêm da INTERFACE de
      armazenamento. Identificam o equipamento — com a ressalva de que, em
      dock ou adaptador USB, quem responde pode ser a ponte, e o número é
      o do adaptador, não o do disco;
    - `serie_do_volume` é gravado pelo sistema de arquivos na formatação.
      Identifica o volume: muda se a mídia for formatada, e é copiado junto
      numa clonagem.

    Campo vazio significa NÃO APURADO, nunca "a mídia não tem".
    """

    fabricante: str = ""
    produto: str = ""
    revisao: str = ""
    numero_serie: str = ""
    barramento: str = ""
    serie_do_volume: str = ""

    @property
    def vazia(self) -> bool:
        return not (self.fabricante or self.produto or self.numero_serie
                    or self.serie_do_volume)


def obter_serie_do_volume(caminho: str) -> str:
    """
    Número de série do volume, no formato em que o Windows o exibe
    (`1A2B-3C4D`), ou vazio quando não pôde ser lido.

    A suíte já chamava `GetVolumeInformationW` e passava `None` neste
    parâmetro: pedia o rótulo e jogava fora a série. Rótulo é texto
    editável e vazio na maioria dos pendrives — o registro de um caso real
    saiu com `Dispositivo: D:`, que é a posição da mídia na estação do
    examinador, não a mídia.
    """
    if not rodando_no_windows():
        return ""
    serie = ctypes.c_uint32(0)
    try:
        sucesso = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(caminho), None, 0, ctypes.byref(serie), None, None, None, 0
        )
    except OSError:
        return ""
    if not sucesso:
        return ""
    return f"{serie.value >> 16:04X}-{serie.value & 0xFFFF:04X}"


def interpretar_descritor_de_armazenamento(bruto: bytes) -> IdentidadeMidia:
    """
    Lê um STORAGE_DEVICE_DESCRIPTOR. Separada da chamada ao Windows para
    poder ser exercitada com um descritor montado à mão.

    Os quatro textos são referenciados por deslocamento a partir do início
    do buffer; deslocamento zero significa que o equipamento não declarou
    aquele campo.
    """
    if len(bruto) < 32:
        return IdentidadeMidia()

    def texto_em(posicao_do_deslocamento: int) -> str:
        deslocamento = int.from_bytes(
            bruto[posicao_do_deslocamento : posicao_do_deslocamento + 4], "little"
        )
        if deslocamento <= 0 or deslocamento >= len(bruto):
            return ""
        fim = bruto.find(b"\x00", deslocamento)
        trecho = bruto[deslocamento : fim if fim != -1 else len(bruto)]
        return trecho.decode("ascii", errors="replace").strip()

    barramento = int.from_bytes(bruto[28:32], "little")
    return IdentidadeMidia(
        fabricante=texto_em(12),
        produto=texto_em(16),
        revisao=texto_em(20),
        numero_serie=texto_em(24),
        barramento=_BARRAMENTOS.get(barramento, f"código {barramento}"),
    )


def identificar_midia(letra: str) -> IdentidadeMidia:
    """
    Pergunta à interface de armazenamento o que a mídia declara de si, e
    junta o número de série do volume.

    O volume é aberto SEM direito de leitura nem de escrita (acesso 0), o
    que basta para a consulta e dispensa privilégio de Administrador. Nada
    é lido do conteúdo e nada é gravado.
    """
    identidade = IdentidadeMidia()
    if not rodando_no_windows() or not letra:
        return identidade

    kernel32 = kernel32_tipado()
    handle = kernel32.CreateFileW(
        f"{chr(92)}{chr(92)}.{chr(92)}{letra}:",
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle is not None and handle != INVALID_HANDLE_VALUE:
        try:
            # STORAGE_PROPERTY_QUERY zerado: StorageDeviceProperty,
            # PropertyStandardQuery.
            consulta = ctypes.create_string_buffer(12)
            resposta = ctypes.create_string_buffer(1024)
            devolvidos = ctypes.c_uint32(0)
            sucesso = kernel32.DeviceIoControl(
                handle,
                IOCTL_STORAGE_QUERY_PROPERTY,
                consulta,
                len(consulta),
                resposta,
                len(resposta),
                ctypes.byref(devolvidos),
                None,
            )
            if sucesso and devolvidos.value:
                identidade = interpretar_descritor_de_armazenamento(
                    resposta.raw[: devolvidos.value]
                )
        finally:
            kernel32.CloseHandle(handle)

    identidade.serie_do_volume = obter_serie_do_volume(f"{letra}:{chr(92)}")
    return identidade


def _obter_espaco(caminho: str) -> Tuple[int, int]:
    """Retorna (bytes_livres, bytes_total) da unidade, ou (0, 0) se não for possível ler."""
    bytes_livres = ctypes.c_ulonglong(0)
    bytes_total = ctypes.c_ulonglong(0)
    try:
        sucesso = ctypes.windll.kernel32.GetDiskFreeSpaceExW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(caminho),
            ctypes.pointer(bytes_livres),
            ctypes.pointer(bytes_total),
            None,
        )
        if not sucesso:
            return 0, 0
        return bytes_livres.value, bytes_total.value
    except OSError:
        return 0, 0
