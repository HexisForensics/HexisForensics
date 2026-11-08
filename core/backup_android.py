"""
Leitura do arquivo `.ab` produzido pelo `adb backup`.

Por que existe. Num aparelho de fábrica o shell do ADB não lê SMS nem
chamadas: os providers recusam, e `pm grant` também — medido num moto x4
(Android 9) em 09/10/2026, o sistema respondeu "Package com.android.shell
has not requested permission". O que funcionou, sem root e sem instalar
nada, foi pedir o backup dos dois pacotes DO SISTEMA que guardam esses
dados:

- `com.android.providers.telephony` — SMS e MMS, em arquivos
  `NNNNNN_sms_backup` / `NNNNNN_mms_backup` (JSON comprimido);
- `com.android.calllogbackup` — chamadas, em formato chave/valor binário
  (exige `adb backup -keyvalue`).

A suíte já guardava o `.ab` "para decodificação posterior" e nunca o abria.
Aqui ele é aberto EM MEMÓRIA: o arquivo selado não é tocado, e nada é
gravado ao lado dele.

Três coisas que este leitor não faz, e diz que não faz:

- **não decifra**. Backup protegido por senha é recusado com esse motivo;
- **não atesta completude**. Quem decide o que entra no backup é o agente
  do próprio Android, que pode limitar volume. O que está aqui existia no
  aparelho; o que não está aqui não se pode dizer que não existia;
- **não traz anexo de MMS**: o agente do sistema não os inclui.
"""

from __future__ import annotations

import io
import json
import struct
import tarfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.normalizacao import (
    CAIXAS_MMS,
    ENDERECO_MMS_DE,
    TIPOS_CHAMADA,
    TIPOS_SMS,
    Descarte,
    Registro,
    ResultadoNormalizacao,
    _rotulo_do_codigo,
    momento_de_epoch,
    nome_do_fuso,
)

PACOTE_TELEFONIA = "com.android.providers.telephony"
PACOTE_CHAMADAS = "com.android.calllogbackup"

# Pacotes cujo agente só responde ao backup chave/valor (`-keyvalue`).
PACOTES_CHAVE_VALOR = (PACOTE_CHAMADAS,)

ASSINATURA = b"ANDROID BACKUP"
NOME_MANIFESTO = "_manifest"

_MAGICA_ENTIDADE = b"Data"

# Apresentação do número (CallLog.Calls.NUMBER_PRESENTATION).
APRESENTACOES = {
    1: "Identificado",
    2: "Restrito pelo chamador",
    3: "Desconhecido",
    4: "Telefone público",
}


@dataclass
class ConteudoBackup:
    """O que havia dentro de um `.ab`, ou por que não foi possível abri-lo."""

    legivel: bool = False
    motivo: str = ""
    cifrado: bool = False
    versao: str = ""
    # nome do membro dentro do tar -> bytes
    membros: dict = field(default_factory=dict)

    @property
    def arquivos_de_dados(self) -> list:
        """Membros que não são o manifesto do pacote — o conteúdo de fato."""
        return sorted(
            nome for nome, dado in self.membros.items()
            if not nome.endswith("/" + NOME_MANIFESTO) and dado
        )


def abrir(caminho: Path) -> ConteudoBackup:
    """Abre um `.ab` em memória. Nunca levanta exceção: devolve o motivo."""
    try:
        bruto = Path(caminho).read_bytes()
    except OSError as erro:
        return ConteudoBackup(motivo=f"o arquivo não pôde ser lido: {erro}")

    partes = bruto.split(b"\n", 4)
    if len(partes) < 5 or partes[0] != ASSINATURA:
        return ConteudoBackup(motivo="o arquivo não tem a assinatura de backup do Android")

    versao, comprimido, cifra = (p.decode("ascii", "replace") for p in partes[1:4])
    if cifra != "none":
        return ConteudoBackup(
            cifrado=True,
            versao=versao,
            motivo=(
                f"o backup está cifrado ({cifra}) — foi digitada uma senha na tela do "
                "aparelho. O conteúdo NÃO foi lido, e nada se pode afirmar sobre ele"
            ),
        )

    corpo = partes[4]
    try:
        if comprimido == "1":
            corpo = zlib.decompress(corpo)
        membros = {}
        with tarfile.open(fileobj=io.BytesIO(corpo)) as tar:
            for membro in tar.getmembers():
                if membro.isfile():
                    membros[membro.name] = tar.extractfile(membro).read()
    except (zlib.error, tarfile.TarError, OSError, EOFError) as erro:
        return ConteudoBackup(
            versao=versao,
            motivo=f"o conteúdo do backup está truncado ou corrompido: {erro}",
        )
    return ConteudoBackup(legivel=True, versao=versao, membros=membros)


VAZIO_NAO_E_AUSENCIA = (
    "O backup do sistema foi aberto e não trouxe nenhum registro deste tipo. Quem "
    "decide o que entra no backup é o agente do próprio Android, e a completude não "
    "é verificável por esta via: NÃO se pode concluir que o aparelho não continha "
    "esses dados."
)


def _resultado(tipo: str, arquivo: str, fuso) -> ResultadoNormalizacao:
    return ResultadoNormalizacao(
        tipo=tipo,
        arquivo_de_origem=arquivo,
        fuso_declarado=nome_do_fuso(fuso),
        significado_do_vazio=VAZIO_NAO_E_AUSENCIA,
    )


def _recusar(resultado: ResultadoNormalizacao, motivo: str) -> ResultadoNormalizacao:
    # Mesmo canal que os outros leitores usam para "não foi possível ler":
    # é o que impede o relatório de dizer "nenhum registro".
    resultado.acesso_negado = True
    resultado.trecho_da_recusa = motivo
    return resultado


def _lotes_json(conteudo: ConteudoBackup, sufixo: str, resultado: ResultadoNormalizacao):
    """
    Entrega `(nome_do_membro, indice, objeto)` de cada mensagem dos lotes
    `NNNNNN_<sufixo>`. Lote que não abre vira descarte contado.
    """
    for nome in conteudo.arquivos_de_dados:
        if not nome.endswith(sufixo):
            continue
        try:
            itens = json.loads(zlib.decompress(conteudo.membros[nome]).decode("utf-8"))
        except (zlib.error, ValueError, UnicodeDecodeError) as erro:
            resultado.descartes.append(
                Descarte(0, nome, f"lote do backup não pôde ser aberto: {erro}")
            )
            continue
        if not isinstance(itens, list):
            resultado.descartes.append(Descarte(0, nome, "lote do backup fora do formato esperado"))
            continue
        for indice, item in enumerate(itens, 1):
            if isinstance(item, dict):
                yield nome, indice, item
            else:
                resultado.descartes.append(
                    Descarte(indice, f"{nome} item {indice}", "item do lote não é um registro")
                )


def _lida(valor) -> str:
    return {"0": "Não", "1": "Sim"}.get(str(valor), "(não informado)")


def ler_sms(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    """SMS a partir do backup de `com.android.providers.telephony`."""
    resultado = _resultado("sms", arquivo, fuso)
    conteudo = abrir(caminho)
    if not conteudo.legivel:
        return _recusar(resultado, conteudo.motivo)

    for nome, indice, item in _lotes_json(conteudo, "_sms_backup", resultado):
        resultado.registros.append(
            Registro(
                tipo="sms",
                campos={
                    "numero": item.get("address") or "(sem número)",
                    "direcao": _rotulo_do_codigo(item.get("type"), TIPOS_SMS),
                    "conteudo": item.get("body") or "",
                    "lida": _lida(item.get("read")),
                    "identificador_no_aparelho": "",
                },
                momento=momento_de_epoch(item.get("date"), fuso),
                arquivo_de_origem=f"{arquivo} :: {nome}",
                linha_de_origem=indice,
                bruto=json.dumps(item, ensure_ascii=False),
            )
        )
    return resultado


def ler_mms(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    """
    MMS a partir do mesmo backup. Só texto e endereços: o agente do Android
    não inclui os anexos, e a coluna diz isso em vez de ficar vazia.
    """
    resultado = _resultado("mms", arquivo, fuso)
    conteudo = abrir(caminho)
    if not conteudo.legivel:
        return _recusar(resultado, conteudo.motivo)

    for nome, indice, item in _lotes_json(conteudo, "_mms_backup", resultado):
        caixa = item.get("msg_box")
        enderecos = item.get("mms_addresses") or []
        procurado_de = str(caixa) == "1"
        numeros = [
            str(e.get("address"))
            for e in enderecos
            if isinstance(e, dict)
            and e.get("address")
            and (str(e.get("type")) == ENDERECO_MMS_DE) == procurado_de
            and e.get("address") != "insert-address-token"
        ]
        resultado.registros.append(
            Registro(
                tipo="mms",
                campos={
                    "numero": ", ".join(numeros) or "(sem número)",
                    "direcao": _rotulo_do_codigo(caixa, CAIXAS_MMS),
                    "conteudo": item.get("mms_body") or "",
                    "assunto": item.get("sub") or "",
                    "anexo": "(o backup do sistema não inclui anexos de MMS)",
                    "lida": _lida(item.get("read")),
                    "identificador_no_aparelho": "",
                },
                momento=momento_de_epoch(item.get("date"), fuso),
                arquivo_de_origem=f"{arquivo} :: {nome}",
                linha_de_origem=indice,
                bruto=json.dumps(item, ensure_ascii=False),
            )
        )
    return resultado


# ---------------------------------------------------------------------------
# Chamadas: formato chave/valor binário
# ---------------------------------------------------------------------------
class _Fluxo:
    """Leitor do que o `DataOutputStream` do Android gravou (big-endian)."""

    def __init__(self, dado: bytes):
        self._dado = dado
        self._posicao = 0

    def _ler(self, quantidade: int) -> bytes:
        trecho = self._dado[self._posicao : self._posicao + quantidade]
        if len(trecho) != quantidade:
            raise ValueError("registro termina antes do campo esperado")
        self._posicao += quantidade
        return trecho

    def inteiro(self) -> int:
        return struct.unpack(">i", self._ler(4))[0]

    def longo(self) -> int:
        return struct.unpack(">q", self._ler(8))[0]

    def texto(self) -> Optional[str]:
        """`writeString` do agente: um booleano de presença e o texto."""
        if self._ler(1) == b"\x00":
            return None
        tamanho = struct.unpack(">H", self._ler(2))[0]
        return self._ler(tamanho).decode("utf-8", "replace")

    @property
    def restante(self) -> int:
        return len(self._dado) - self._posicao


def entidades_chave_valor(dado: bytes):
    """
    Percorre o arquivo de dados de um backup chave/valor e entrega
    `(chave, valor)`. Cada entidade é: mágica `Data`, tamanho da chave,
    tamanho do valor (little-endian), chave terminada em nulo e valor,
    ambos alinhados em 4 bytes. Valor de tamanho -1 é uma exclusão.

    Levanta `ValueError` quando a estrutura se perde — quem chama conta o
    que sobrou como descarte, em vez de devolver só o que deu certo.
    """
    posicao = 0
    while posicao < len(dado):
        if dado[posicao : posicao + 4] != _MAGICA_ENTIDADE:
            raise ValueError(f"estrutura desconhecida no byte {posicao}")
        if posicao + 12 > len(dado):
            raise ValueError(f"cabeçalho truncado no byte {posicao}")
        tamanho_chave, tamanho_valor = struct.unpack("<ii", dado[posicao + 4 : posicao + 12])
        inicio_chave = posicao + 12
        chave = dado[inicio_chave : inicio_chave + tamanho_chave].decode("utf-8", "replace")
        inicio_valor = (inicio_chave + tamanho_chave + 1 + 3) & ~3
        if tamanho_valor < 0:
            yield chave, None
            posicao = inicio_valor
            continue
        fim_valor = inicio_valor + tamanho_valor
        if fim_valor > len(dado):
            raise ValueError(f"valor da chave '{chave}' truncado")
        yield chave, dado[inicio_valor:fim_valor]
        posicao = (fim_valor + 3) & ~3


def interpretar_chamada(valor: bytes) -> dict:
    """
    Campos de uma chamada como o `CallLogBackupAgent` os grava.

    Só são lidos os campos iniciais, que têm a mesma ordem desde a primeira
    versão do formato. O que vem depois (dados do fabricante, bloqueio,
    triagem) muda entre versões e fabricantes — medido no moto x4, a cauda
    não segue o leiaute do AOSP — e não é interpretado: `bytes_nao_lidos`
    diz quantos ficaram de fora.
    """
    fluxo = _Fluxo(valor)
    campos = {
        "versao_do_formato": fluxo.inteiro(),
        "data": fluxo.longo(),
        "duracao": fluxo.longo(),
        "numero": fluxo.texto(),
        "tipo": fluxo.inteiro(),
        "apresentacao": fluxo.inteiro(),
        "conta": fluxo.texto(),
        "id_da_conta": fluxo.texto(),
    }
    campos["bytes_nao_lidos"] = fluxo.restante
    return campos


def ler_chamadas(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    """Registro de chamadas a partir do backup de `com.android.calllogbackup`."""
    resultado = _resultado("chamada", arquivo, fuso)
    conteudo = abrir(caminho)
    if not conteudo.legivel:
        return _recusar(resultado, conteudo.motivo)

    for nome in conteudo.arquivos_de_dados:
        if not nome.endswith(".data"):
            continue
        try:
            for indice, (chave, valor) in enumerate(
                entidades_chave_valor(conteudo.membros[nome]), 1
            ):
                if valor is None:
                    resultado.descartes.append(
                        Descarte(indice, f"chave {chave}", "marcador de exclusão, sem dados")
                    )
                    continue
                try:
                    campos = interpretar_chamada(valor)
                except (ValueError, struct.error) as erro:
                    resultado.descartes.append(
                        Descarte(indice, f"chave {chave}: {valor[:40].hex()}",
                                 f"registro de chamada não compreendido: {erro}")
                    )
                    continue
                resultado.registros.append(
                    Registro(
                        tipo="chamada",
                        campos={
                            "numero": campos["numero"] or "(sem número)",
                            # O backup não traz o nome: ele é resolvido pela
                            # agenda no aparelho, e não é gravado aqui.
                            "contato": "(o backup não traz o nome do contato)",
                            "direcao": _rotulo_do_codigo(campos["tipo"], TIPOS_CHAMADA),
                            "duracao_segundos": str(campos["duracao"]),
                            "apresentacao": _rotulo_do_codigo(
                                campos["apresentacao"], APRESENTACOES
                            ),
                            "linha_utilizada": campos["id_da_conta"] or "",
                            "identificador_no_aparelho": chave,
                        },
                        momento=momento_de_epoch(campos["data"], fuso),
                        arquivo_de_origem=f"{arquivo} :: {nome}",
                        linha_de_origem=indice,
                        bruto=valor.hex(),
                    )
                )
        except ValueError as erro:
            resultado.descartes.append(
                Descarte(0, nome, f"leitura interrompida — {erro}; pode haver chamadas além deste ponto")
            )
    return resultado
