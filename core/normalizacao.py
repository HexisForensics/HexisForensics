"""
Normalização das saídas brutas dos Content Providers do Android.

O que os extratores gravam é o texto do `content query` como o aparelho
devolveu — uma linha por registro, campos `chave=valor` separados por
vírgula, datas em epoch. É evidência fiel e ilegível: ninguém tira conclusão
de investigação lendo `date=1755123456789`.

Este módulo converte esse texto em **registros estruturados**. Ele não grava
nada e não decide formato de saída: quem renderiza CSV, PDF ou alimenta um
índice é outra camada. A separação é deliberada — o relatório de conteúdo e
um futuro indexador precisam exatamente do mesmo dado normalizado, e escrever
o parser dentro do relatório obrigaria a reescrevê-lo depois.

**Normalizar é interpretar.** Por isso todo registro carrega de onde veio —
arquivo e número da linha — e nada que não tenha sido compreendido é
descartado em silêncio: linha que não casa com o padrão vai para
`descartes`, contada e com o motivo. Um parser que engole o que não entende
produz relatório com menos registros do que a evidência tem, e ninguém
percebe.

As quatro armadilhas do formato, todas tratadas aqui:

1. **Corpo com quebra de linha.** O `content query` imprime um registro por
   linha, mas o corpo de um SMS pode conter `\\n`. Quebrar por linha parte a
   mensagem em duas — a segunda metade vira lixo e a primeira vira uma
   mensagem truncada apresentada como completa.
2. **Vírgula dentro do valor.** "Oi, tudo bem?" tem vírgula, e o separador
   de campos também é vírgula. Só se separa onde a vírgula é seguida de um
   nome de campo.
3. **Epoch em milissegundos ou em segundos.** Os dois aparecem conforme o
   provider. Errar joga a data para 1970 ou para daqui a milênios.
4. **Saída de erro não é dado.** O `SecurityException` de um provider que
   recusou acesso precisa ser reconhecido como recusa — nunca virar "nenhum
   registro encontrado", que sustenta conclusão oposta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Marcadores de recusa do provider. Moram aqui, e não no extrator, porque
# são a mesma regra em dois momentos: quem coleta precisa distinguir "sem
# dados" de "acesso negado", e quem normaliza precisa da mesma distinção
# meses depois. Duas definições divergiriam.
MARCADORES_ACESSO_NEGADO = (
    "Permission Denial",
    "SecurityException",
    "java.lang.SecurityException",
    "Error while accessing provider",
)

# Início de cada registro na saída do `content query`.
_INICIO_REGISTRO = re.compile(r"^Row:\s+(\d+)\s+(.*)$")
# A resposta do `content query` para fonte sem registro — inteira, e nada mais.
RESPOSTA_VAZIA = re.compile(r"^﻿?\s*No result found\.?\s*$", re.IGNORECASE)

# Separador de campos: vírgula seguida de espaço E de um nome de campo.
# É o que impede quebrar "Oi, tudo bem?" no meio.
_SEPARADOR_CAMPOS = re.compile(r",\s+(?=[A-Za-z_][A-Za-z0-9_]*=)")

# Acima deste valor, o epoch só pode estar em milissegundos: 10^11 segundos
# seriam o ano 5138, e 10^11 milissegundos são 1973.
_LIMITE_MILISSEGUNDOS = 10**11

# Códigos do Android. Código desconhecido NÃO é adivinhado: vira texto que
# diz que não foi reconhecido, preservando o número original.
TIPOS_SMS = {
    1: "Recebida",
    2: "Enviada",
    3: "Rascunho",
    4: "Caixa de saída",
    5: "Falha no envio",
    6: "Na fila",
}

TIPOS_CHAMADA = {
    1: "Recebida",
    2: "Efetuada",
    3: "Perdida",
    4: "Correio de voz",
    5: "Rejeitada",
    6: "Bloqueada",
    7: "Atendida em outro dispositivo",
}


def indica_acesso_negado(saida: str) -> bool:
    """
    `True` quando a saída é a recusa do provider, e não dado.

    Distinção que sustenta conclusões opostas: "o provider respondeu e não
    havia registro" e "o sistema recusou a consulta" produzem o mesmo
    arquivo vazio de dados, mas significam coisas contrárias no exame.
    """
    return any(marcador in (saida or "") for marcador in MARCADORES_ACESSO_NEGADO)


@dataclass
class Registro:
    """Um registro normalizado, com a procedência colada nele."""

    tipo: str
    campos: dict = field(default_factory=dict)
    momento: Optional[datetime] = None
    arquivo_de_origem: str = ""
    linha_de_origem: int = 0
    bruto: str = ""

    @property
    def momento_legivel(self) -> str:
        """Data e hora com o fuso explícito, ou a razão de não haver."""
        if self.momento is None:
            return "(sem data no registro)"
        return self.momento.strftime("%d/%m/%Y %H:%M:%S %Z").strip()


@dataclass
class Descarte:
    """Trecho que o normalizador não compreendeu — contado, nunca omitido."""

    linha_de_origem: int
    texto: str
    motivo: str


@dataclass
class ResultadoNormalizacao:
    """
    Desfecho da normalização de um arquivo bruto.

    `acesso_negado` e `registros` vazios são situações diferentes, e o
    relatório precisa dizer qual das duas ocorreu.
    """

    tipo: str
    arquivo_de_origem: str = ""
    fuso_declarado: str = "UTC"
    registros: list = field(default_factory=list)
    descartes: list = field(default_factory=list)
    acesso_negado: bool = False
    trecho_da_recusa: str = ""
    # O que significa esta fonte ter vindo sem registro algum, quando a
    # fonte NÃO é uma consulta a provider. Sem isto, todo vazio era
    # explicado como "o provider respondeu e não retornou nenhum registro"
    # — inclusive o de um backup, que não é consulta e não prova ausência.
    significado_do_vazio: str = ""

    @property
    def total(self) -> int:
        return len(self.registros)

    @property
    def explicacao_do_vazio(self) -> str:
        """
        Por que não há registros — nunca apenas "nenhum".

        Três causas levam a zero e sustentam conclusões diferentes: o
        provider recusou, o provider respondeu vazio, ou o arquivo não foi
        compreendido.
        """
        if self.registros:
            return ""
        if self.acesso_negado:
            return (
                "O sistema do aparelho RECUSOU a consulta. Não se obteve dado algum — "
                "o que é diferente de não existir dado no aparelho."
            )
        if self.descartes:
            return (
                f"Nenhum registro foi compreendido, e {len(self.descartes)} trecho(s) do "
                "arquivo não puderam ser interpretados. O arquivo bruto precisa ser "
                "examinado à mão."
            )
        if self.significado_do_vazio:
            return self.significado_do_vazio
        return "O provider respondeu à consulta e não retornou nenhum registro."


# ---------------------------------------------------------------------------
# Leitura do formato bruto
# ---------------------------------------------------------------------------
def _blocos(texto: str):
    """
    Separa a saída em blocos, um por registro, e devolve também o preâmbulo.

    Um bloco começa em `Row: N` e vai até o próximo `Row:` — e não até a
    próxima quebra de linha. É isso que preserva inteiro o corpo de uma
    mensagem que contém quebras.

    O que aparece ANTES do primeiro `Row:` é devolvido à parte, para virar
    descarte. A versão anterior simplesmente pulava essas linhas, e um
    arquivo real mostrou o custo disso: um BOM invisível no início fez o
    primeiro registro não casar com o padrão, e ele desapareceu sem que
    nada fosse contado. Preâmbulo silenciosamente ignorado é a receita do
    relatório incompleto que ninguém percebe — aviso do adb antes da saída
    produziria o mesmo efeito.

    Rende tuplas `(indice, numero_da_linha, bloco)`; o preâmbulo, quando
    existe, vem primeiro com `indice = None`.
    """
    # O BOM entra quando o arquivo é gravado ou reaberto por outra
    # ferramenta. Ele é invisível e gruda no primeiro caractere.
    texto = (texto or "").lstrip("﻿")

    linhas = texto.splitlines()
    indice_atual = None
    numero_linha = 0
    acumulado: list = []
    preambulo: list = []

    for numero, linha in enumerate(linhas, start=1):
        inicio = _INICIO_REGISTRO.match(linha)
        if inicio:
            if preambulo:
                yield None, 1, "\n".join(preambulo)
                preambulo = []
            if indice_atual is not None:
                yield indice_atual, numero_linha, "\n".join(acumulado)
            indice_atual = int(inicio.group(1))
            numero_linha = numero
            acumulado = [inicio.group(2)]
        elif indice_atual is not None:
            acumulado.append(linha)
        elif linha.strip():
            preambulo.append(linha)

    if preambulo:
        yield None, 1, "\n".join(preambulo)
    if indice_atual is not None:
        yield indice_atual, numero_linha, "\n".join(acumulado)


def _campos(bloco: str) -> dict:
    """Converte `chave=valor, chave=valor` em dicionário."""
    campos = {}
    for parte in _SEPARADOR_CAMPOS.split(bloco):
        chave, separador, valor = parte.partition("=")
        if not separador:
            continue
        valor = valor.strip()
        campos[chave.strip()] = None if valor == "NULL" else valor
    return campos


def _para_momento(valor, fuso: Optional[timezone]) -> Optional[datetime]:
    """
    Converte o epoch do Android em data e hora, no fuso informado.

    Zero e vazio devolvem `None`: o Android usa 0 para "não registrado", e
    apresentá-lo como 01/01/1970 seria inventar uma data que não existe no
    aparelho.
    """
    if valor in (None, "", "0"):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if numero <= 0:
        return None

    segundos = numero / 1000 if numero > _LIMITE_MILISSEGUNDOS else numero
    try:
        momento = datetime.fromtimestamp(segundos, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return momento.astimezone(fuso) if fuso is not None else momento


def _rotulo_do_codigo(valor, tabela: dict) -> str:
    """Rótulo do código, ou a declaração de que ele não foi reconhecido."""
    if valor in (None, ""):
        return "(não informado)"
    try:
        codigo = int(valor)
    except (TypeError, ValueError):
        return f"(código não numérico: {valor})"
    return tabela.get(codigo, f"(código {codigo} não reconhecido)")


def _nome_do_fuso(fuso: Optional[timezone]) -> str:
    if fuso is None:
        return "UTC (nenhum fuso informado)"
    agora = datetime.now(tz=fuso)
    return agora.strftime("%Z") or agora.strftime("UTC%z")


# ---------------------------------------------------------------------------
# Normalização por artefato
# ---------------------------------------------------------------------------
def _normalizar(
    texto: str,
    tipo: str,
    arquivo: str,
    fuso: Optional[timezone],
    montar_campos,
    campo_de_data: str,
) -> ResultadoNormalizacao:
    resultado = ResultadoNormalizacao(
        tipo=tipo, arquivo_de_origem=arquivo, fuso_declarado=_nome_do_fuso(fuso)
    )

    if indica_acesso_negado(texto):
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = (texto or "").strip().splitlines()[0] if texto else ""
        return resultado

    if RESPOSTA_VAZIA.match(texto or ""):
        # É a resposta do próprio `content query` quando a fonte não tem
        # registro. Tratada como trecho ilegível, ela mandava "examinar à mão"
        # um arquivo que diz com todas as letras que está vazio (Samsung sem
        # chip, 31/10/2026). Só vale se for a resposta INTEIRA.
        return resultado

    encontrou_algo = False
    for indice, numero_linha, bloco in _blocos(texto):
        encontrou_algo = True
        if indice is None:
            resultado.descartes.append(
                Descarte(
                    numero_linha,
                    bloco[:200],
                    "conteúdo antes do primeiro registro, fora do formato 'Row: N ...'",
                )
            )
            continue

        campos = _campos(bloco)
        if not campos:
            resultado.descartes.append(
                Descarte(numero_linha, bloco[:200], "nenhum campo reconhecido no registro")
            )
            continue
        resultado.registros.append(
            Registro(
                tipo=tipo,
                campos=montar_campos(campos),
                momento=_para_momento(campos.get(campo_de_data), fuso),
                arquivo_de_origem=arquivo,
                linha_de_origem=numero_linha,
                bruto=bloco,
            )
        )

    if not encontrou_algo and (texto or "").strip():
        # Havia conteúdo e nada foi reconhecido: é o sinal de que o formato
        # mudou. Melhor gritar aqui do que devolver "nenhuma mensagem".
        resultado.descartes.append(
            Descarte(1, (texto or "").strip()[:200], "o conteúdo não segue o formato 'Row: N ...'")
        )

    return resultado


def normalizar_sms(texto: str, arquivo: str = "", fuso: Optional[timezone] = None):
    """
    Mensagens SMS a partir da saída de `content://sms`.

    MMS NÃO está aqui: mora em outro provider (`content://mms`) e é lido por
    `normalizar_mms`. O título deste artefato dizia "SMS/MMS" sem que MMS
    algum fosse consultado.
    """

    def montar(campos: dict) -> dict:
        return {
            "numero": campos.get("address") or "(sem número)",
            "direcao": _rotulo_do_codigo(campos.get("type"), TIPOS_SMS),
            "conteudo": campos.get("body") or "",
            "lida": {"0": "Não", "1": "Sim"}.get(campos.get("read"), "(não informado)"),
            "identificador_no_aparelho": campos.get("_id") or "",
        }

    return _normalizar(texto, "sms", arquivo, fuso, montar, "date")


def normalizar_chamadas(texto: str, arquivo: str = "", fuso: Optional[timezone] = None):
    """Registro de chamadas a partir da saída de `content://call_log/calls`."""

    def montar(campos: dict) -> dict:
        duracao = campos.get("duration")
        return {
            "numero": campos.get("number") or "(sem número)",
            "contato": campos.get("name") or "(não consta na agenda)",
            "direcao": _rotulo_do_codigo(campos.get("type"), TIPOS_CHAMADA),
            "duracao_segundos": duracao if duracao not in (None, "") else "0",
            "identificador_no_aparelho": campos.get("_id") or "",
        }

    return _normalizar(texto, "chamada", arquivo, fuso, montar, "date")


def normalizar_contatos(texto: str, arquivo: str = "", fuso: Optional[timezone] = None):
    """
    Agenda a partir da saída de `content://com.android.contacts/data/phones`.

    Contato não tem data própria neste provider: o campo de momento fica
    vazio, e o relatório precisa exibi-lo como ausente em vez de inventar a
    data da coleta.
    """

    def montar(campos: dict) -> dict:
        return {
            "contato": campos.get("display_name") or "(sem nome)",
            "numero": campos.get("data1") or campos.get("number") or "(sem número)",
            "identificador_no_aparelho": campos.get("_id") or "",
        }

    return _normalizar(texto, "contato", arquivo, fuso, montar, "__sem_data__")


# Caixas do MMS (`msg_box`). Os códigos coincidem com os do SMS só até o 4.
CAIXAS_MMS = {
    1: "Recebida",
    2: "Enviada",
    3: "Rascunho",
    4: "Caixa de saída",
}

# Tipos de endereço do MMS (PduHeaders): quem enviou e a quem se destinava.
ENDERECO_MMS_DE = "137"
ENDERECOS_MMS_PARA = ("151", "130", "129")  # para, cc, cco

# O Android grava este marcador no lugar do número do PRÓPRIO aparelho.
_MARCADOR_PROPRIO_NUMERO = "insert-address-token"

NOME_PARTES_MMS = "mms_partes.txt"
PASTA_ENDERECOS_MMS = "mms_enderecos"

# Partes que são a mensagem em si (texto) ou só o leiaute dela (SMIL) —
# todo o resto é anexo.
TIPO_TEXTO_MMS = "text/plain"
TIPO_LEIAUTE_MMS = "application/smil"


def nome_do_arquivo_de_enderecos(identificador: str) -> str:
    """Nome do arquivo bruto com os endereços de uma mensagem MMS."""
    return f"mms_{identificador}_enderecos.txt"


def normalizar_mms(
    texto: str,
    arquivo: str = "",
    fuso: Optional[timezone] = None,
    pasta: Optional[Path] = None,
):
    """
    Mensagens MMS a partir da saída de `content://mms`.

    O MMS é espalhado em três consultas, e o cabeçalho sozinho não tem nem
    o texto nem o número: o texto está nas PARTES (`content://mms/part`) e
    os números nos ENDEREÇOS (`content://mms/<id>/addr`). `pasta` é onde os
    dois brutos irmãos foram gravados pelo extrator.

    Quando um deles falta ou foi recusado, o campo diz isso com todas as
    letras. Deixar em branco faria uma mensagem com texto parecer uma
    mensagem vazia.
    """
    partes, situacao_das_partes = _partes_do_mms(pasta)

    def montar(campos: dict) -> dict:
        identificador = campos.get("_id") or ""
        caixa = campos.get("msg_box")
        if situacao_das_partes:
            conteudo, anexos = situacao_das_partes, situacao_das_partes
        else:
            textos, lista_anexos = partes.get(identificador, ([], []))
            conteudo = " / ".join(textos)
            anexos = "; ".join(lista_anexos)
        return {
            "numero": _numero_do_mms(pasta, identificador, caixa),
            "direcao": _rotulo_do_codigo(caixa, CAIXAS_MMS),
            "conteudo": conteudo,
            "assunto": campos.get("sub") or "",
            "anexo": anexos,
            "lida": {"0": "Não", "1": "Sim"}.get(campos.get("read"), "(não informado)"),
            "identificador_no_aparelho": identificador,
        }

    return _normalizar(texto, "mms", arquivo, fuso, montar, "date")


def _partes_do_mms(pasta: Optional[Path]):
    """
    Devolve `({id_da_mensagem: (textos, anexos)}, situacao)`.

    `situacao` é vazia quando as partes foram lidas; do contrário é o texto
    que explica por que não há conteúdo, e vai para o campo no lugar dele.
    """
    if pasta is None:
        return {}, "(partes do MMS não informadas ao normalizador)"
    caminho = Path(pasta) / NOME_PARTES_MMS
    if not caminho.is_file():
        return {}, "(partes do MMS não coletadas)"
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    if indica_acesso_negado(texto):
        return {}, "(conteúdo não obtido: o sistema recusou a consulta às partes)"

    partes: dict = {}
    for campos in registros_brutos(texto):
        textos, anexos = partes.setdefault(campos.get("mid") or "", ([], []))
        tipo = (campos.get("ct") or "").lower()
        if tipo == TIPO_TEXTO_MMS:
            if campos.get("text"):
                textos.append(campos["text"])
        elif tipo != TIPO_LEIAUTE_MMS:
            nome = campos.get("name") or campos.get("cl") or campos.get("fn") or "sem nome"
            anexos.append(f"{nome} [{tipo or 'tipo não declarado'}, parte {campos.get('_id')}]")
    return partes, ""


def _numero_do_mms(pasta: Optional[Path], identificador: str, caixa) -> str:
    """O interlocutor: remetente da recebida, destinatário(s) das demais."""
    if pasta is None or not identificador:
        return "(endereços não coletados)"
    caminho = Path(pasta) / PASTA_ENDERECOS_MMS / nome_do_arquivo_de_enderecos(identificador)
    if not caminho.is_file():
        return "(endereços não coletados)"
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    if indica_acesso_negado(texto):
        return "(endereços não obtidos: consulta recusada)"

    procurados = (ENDERECO_MMS_DE,) if str(caixa) == "1" else ENDERECOS_MMS_PARA
    numeros = [
        campos.get("address")
        for campos in registros_brutos(texto)
        if campos.get("type") in procurados
        and campos.get("address")
        and campos.get("address") != _MARCADOR_PROPRIO_NUMERO
    ]
    return ", ".join(numeros) if numeros else "(sem número)"


# ---------------------------------------------------------------------------
# Reuso por outros leitores
# ---------------------------------------------------------------------------
def registros_brutos(texto: str) -> list:
    """
    Os registros `Row: N ...` de uma saída de `content query`, como
    dicionários, sem interpretação alguma.

    Serve a quem precisa de um campo do registro para decidir o próximo
    passo — o extrator de MMS lê daqui os identificadores para consultar
    endereços e anexos — sem manter um segundo parser do mesmo formato.
    """
    return [
        _campos(bloco) for indice, _linha, bloco in _blocos(texto) if indice is not None
    ]



# O leitor de banco SQLite precisa das mesmas duas conversões que o parser
# de texto usa. Reimplementá-las lá seria uma segunda fonte da mesma regra
# — e a armadilha do epoch em milissegundos ou em segundos é exatamente do
# tipo que se corrige num lugar e fica errada no outro.
def momento_de_epoch(valor, fuso: Optional[timezone] = None) -> Optional[datetime]:
    """Epoch do Android em data e hora, no fuso informado. Zero vira `None`."""
    return _para_momento(valor, fuso)


def nome_do_fuso(fuso: Optional[timezone] = None) -> str:
    """Nome do fuso, para o relatório declarar em que referência as datas estão."""
    return _nome_do_fuso(fuso)
