"""
Decifragem do backup local do WhatsApp cifrado com chave conhecida
(`msgstore.db.crypt15`).

É a via do WhatsApp que não depende de root nem de versão do Android. O
aplicativo permite ativar o backup criptografado de ponta a ponta com uma
**chave de 64 dígitos** em vez de senha. Com o aparelho desbloqueado, o
examinador ativa a opção, anota a chave que o aplicativo exibe e manda
fazer o backup: o arquivo que o módulo de WhatsApp já copia do
armazenamento compartilhado passa a ser legível na estação.

O que este módulo faz é só a conta: deriva a chave de cifragem a partir da
chave de 64 dígitos, confere a autenticidade do arquivo (AES-GCM) e devolve
o banco SQLite. **A conferência do GCM é o que sustenta o resultado**: se a
chave estiver errada, se um dígito foi anotado trocado ou se o arquivo foi
alterado, a etiqueta de autenticação não confere e nada é devolvido — não
existe "decifrou mais ou menos".

O formato do cabeçalho não é documentado pelo fabricante e já mudou entre
versões. Por isso o vetor de inicialização não é lido de uma posição fixa:
todo campo de 16 bytes do cabeçalho é candidato, e o que valida o
candidato é, de novo, a etiqueta do GCM. Cabeçalho novo que mantenha a
cifra continua abrindo; cabeçalho que não abrir é recusado dizendo por quê.

Não alcança: backup `.crypt14`/`.crypt12` (a chave fica na área privada do
aplicativo) nem backup cifrado por SENHA (a chave é guardada num servidor
do fabricante).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import zlib
from pathlib import Path
from typing import Iterator, List

ASSINATURA_SQLITE = b"SQLite format 3\x00"
TAMANHO_DA_ETIQUETA = 16
INFO_DA_DERIVACAO = b"backup encryption"


class ErroDeDecifragem(Exception):
    """A decifragem não produziu um banco — a mensagem diz por quê."""


def normalizar_chave(texto: str) -> bytes:
    """
    A chave de 64 dígitos, como o examinador a digitou, em 32 bytes.

    O aplicativo a mostra em grupos de quatro; espaços, hifens e quebras de
    linha são ignorados. Qualquer outra coisa é recusada com a contagem: o
    erro típico é um dígito a menos, e "chave inválida" não ajudaria a
    achá-lo.
    """
    limpa = re.sub(r"[\s\-]", "", texto or "").lower()
    if not re.fullmatch(r"[0-9a-f]*", limpa):
        estranhos = sorted(set(re.sub(r"[0-9a-f]", "", limpa)))
        raise ErroDeDecifragem(
            "A chave só pode ter dígitos de 0 a 9 e letras de a a f. Caractere(s) "
            f"não aceito(s): {' '.join(estranhos)}"
        )
    if len(limpa) != 64:
        raise ErroDeDecifragem(
            f"A chave tem de ter 64 dígitos; foram digitados {len(limpa)}."
        )
    return bytes.fromhex(limpa)


def derivar_chave(chave_raiz: bytes) -> bytes:
    """Chave AES-256 do backup, derivada da chave de 64 dígitos (HKDF-SHA256)."""
    pseudoaleatoria = hmac.new(b"\x00" * 32, chave_raiz, hashlib.sha256).digest()
    return hmac.new(pseudoaleatoria, INFO_DA_DERIVACAO + b"\x01", hashlib.sha256).digest()


def _varint(dado: bytes, posicao: int):
    valor, deslocamento = 0, 0
    while True:
        if posicao >= len(dado) or deslocamento > 63:
            raise ValueError("varint truncado")
        byte = dado[posicao]
        posicao += 1
        valor |= (byte & 0x7F) << deslocamento
        if not byte & 0x80:
            return valor, posicao
        deslocamento += 7


def _campos_de_bytes(dado: bytes, profundidade: int = 0) -> Iterator[bytes]:
    """Todo campo de comprimento delimitado de uma mensagem protobuf, recursivamente."""
    posicao = 0
    while posicao < len(dado):
        etiqueta, posicao = _varint(dado, posicao)
        tipo = etiqueta & 7
        if tipo == 0:
            _, posicao = _varint(dado, posicao)
        elif tipo == 1:
            posicao += 8
        elif tipo == 5:
            posicao += 4
        elif tipo == 2:
            tamanho, posicao = _varint(dado, posicao)
            if posicao + tamanho > len(dado):
                raise ValueError("campo além do fim")
            campo = dado[posicao:posicao + tamanho]
            posicao += tamanho
            yield campo
            if profundidade < 4:
                try:
                    yield from list(_campos_de_bytes(campo, profundidade + 1))
                except ValueError:
                    pass  # não era uma mensagem aninhada: era só bytes
        else:
            raise ValueError("tipo de campo desconhecido")


def _separar(bruto: bytes) -> tuple:
    """`(cabeçalho protobuf, restante)` de um arquivo crypt15."""
    if len(bruto) < 64:
        raise ErroDeDecifragem("O arquivo é pequeno demais para ser um backup crypt15.")
    tamanho = bruto[0]
    inicio = 1
    # Um byte 0x01 logo depois indica a presença da tabela de recursos.
    if bruto[1] == 0x01:
        inicio = 2
    cabecalho = bruto[inicio:inicio + tamanho]
    if len(cabecalho) != tamanho or tamanho < 16:
        raise ErroDeDecifragem("O cabeçalho do arquivo não tem o formato de um backup crypt15.")
    return cabecalho, bruto[inicio + tamanho:]


def _vetores_candidatos(cabecalho: bytes) -> List[bytes]:
    try:
        campos = list(_campos_de_bytes(cabecalho))
    except ValueError as erro:
        raise ErroDeDecifragem(
            f"O cabeçalho do arquivo não pôde ser interpretado ({erro})."
        ) from erro
    vistos, candidatos = set(), []
    for campo in campos:
        if len(campo) == 16 and campo not in vistos:
            vistos.add(campo)
            candidatos.append(campo)
    if not candidatos:
        raise ErroDeDecifragem(
            "O cabeçalho não traz vetor de inicialização de 16 bytes: não é um backup "
            "crypt15 cifrado com chave, ou é de um formato que esta versão não conhece."
        )
    return candidatos


def decifrar(caminho: Path, chave_raiz: bytes) -> bytes:
    """
    Devolve o banco SQLite contido no backup. Levanta `ErroDeDecifragem`
    com o motivo quando não é possível — e nunca devolve conteúdo que não
    tenha passado na conferência de autenticidade.
    """
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as erro:
        raise ErroDeDecifragem(
            "A biblioteca 'cryptography' não está instalada nesta estação."
        ) from erro

    caminho = Path(caminho)
    if not caminho.name.lower().endswith(".crypt15"):
        raise ErroDeDecifragem(
            f"'{caminho.name}' não é um backup crypt15. Backups .crypt14 e .crypt12 usam "
            "chave guardada na área privada do aplicativo, e não a chave de 64 dígitos."
        )
    try:
        bruto = caminho.read_bytes()
    except OSError as erro:
        raise ErroDeDecifragem(f"O arquivo não pôde ser lido: {erro}") from erro

    cabecalho, restante = _separar(bruto)
    cifra = AESGCM(derivar_chave(chave_raiz))

    # Duas disposições do fim do arquivo já existiram: com e sem um resumo
    # MD5 de 16 bytes depois da etiqueta do GCM.
    disposicoes = []
    if len(restante) > 2 * TAMANHO_DA_ETIQUETA:
        disposicoes.append(restante[:-TAMANHO_DA_ETIQUETA])  # descarta o MD5 final
    disposicoes.append(restante)

    claro = None
    for vetor in _vetores_candidatos(cabecalho):
        for cifrado_com_etiqueta in disposicoes:
            try:
                claro = cifra.decrypt(vetor, cifrado_com_etiqueta, None)
                break
            except InvalidTag:
                continue
        if claro is not None:
            break
    if claro is None:
        raise ErroDeDecifragem(
            "A conferência de autenticidade FALHOU: a chave não é a deste backup (um "
            "dígito trocado basta), o backup foi cifrado por senha e não por chave de 64 "
            "dígitos, ou o arquivo foi alterado. Nada foi decifrado."
        )

    try:
        banco = zlib.decompress(claro)
    except zlib.error:
        banco = claro
    if not banco.startswith(ASSINATURA_SQLITE):
        raise ErroDeDecifragem(
            "O arquivo foi decifrado e autenticado, mas o conteúdo não é um banco SQLite. "
            "Formato não reconhecido por esta versão."
        )
    return banco
