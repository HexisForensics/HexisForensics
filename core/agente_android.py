"""
Leitura do que o aplicativo agente coletou no aparelho.

O agente (`agente_android/`) grava cada provedor do sistema num arquivo de
linhas JSON — uma linha por registro, com todas as colunas — e um
`estado.json` dizendo, por fonte, quantos registros vieram ou que erro o
sistema deu. Aqui esses arquivos viram os mesmos registros normalizados que
os demais leitores produzem, para o relatório de conteúdo e os documentos
não precisarem saber por que via o dado chegou.

Duas situações nunca se confundem com "nenhum registro":

- a fonte consta do `estado.json` com ERRO (o sistema recusou a leitura ao
  agente): o resultado sai como acesso negado, com o texto do erro;
- uma linha do arquivo não é JSON válido: vira descarte contado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from core.normalizacao import (
    CAIXAS_MMS,
    ENDERECO_MMS_DE,
    ENDERECOS_MMS_PARA,
    TIPO_TEXTO_MMS,
    TIPOS_CHAMADA,
    TIPOS_SMS,
    Descarte,
    Registro,
    ResultadoNormalizacao,
    _rotulo_do_codigo,
    momento_de_epoch,
    nome_do_fuso,
)

PASTA = "agente"
NOME_ESTADO = "estado.json"
PACOTE = "br.forensicextractor.agente"

# Arquivos que o agente grava, na ordem em que a estação os recolhe.
ARQUIVOS = (
    "contatos.jsonl", "chamadas.jsonl", "sms.jsonl",
    "mms.jsonl", "mms_partes.jsonl", "mms_enderecos.jsonl",
)

VAZIO = "O provedor do sistema respondeu ao agente e não retornou nenhum registro."
MARCADOR_DO_PROPRIO_NUMERO = "insert-address-token"


def ler_estado(pasta: Path) -> Optional[dict]:
    """O `estado.json` do agente, ou `None` se não existe ou não é legível."""
    try:
        dados = json.loads((Path(pasta) / NOME_ESTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def situacao_das_fontes(estado: Optional[dict]) -> dict:
    """`{nome da fonte: {"registros": n, "erro": texto ou None, ...}}`."""
    fontes = (estado or {}).get("fontes") or []
    return {str(f.get("nome")): f for f in fontes if isinstance(f, dict)}


def _linhas(caminho: Path, resultado: ResultadoNormalizacao) -> Iterator[tuple]:
    """Rende `(numero_da_linha, objeto)`; linha ilegível vira descarte."""
    try:
        texto = Path(caminho).read_text(encoding="utf-8")
    except OSError as erro:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = f"o arquivo do agente não pôde ser lido: {erro}"
        return
    for numero, linha in enumerate(texto.splitlines(), 1):
        if not linha.strip():
            continue
        try:
            objeto = json.loads(linha)
        except ValueError:
            resultado.descartes.append(Descarte(numero, linha[:200], "linha que não é JSON válido"))
            continue
        if isinstance(objeto, dict):
            yield numero, objeto
        else:
            resultado.descartes.append(Descarte(numero, linha[:200], "linha que não é um registro"))


def _resultado(tipo: str, caminho: Path, arquivo: str, fuso, fonte: str) -> ResultadoNormalizacao:
    resultado = ResultadoNormalizacao(
        tipo=tipo, arquivo_de_origem=arquivo, fuso_declarado=nome_do_fuso(fuso),
        significado_do_vazio=VAZIO,
    )
    situacao = situacao_das_fontes(ler_estado(Path(caminho).parent)).get(fonte)
    if situacao is None:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = (
            "o estado da coleta do agente não registra esta fonte — a coleta pode não "
            "ter terminado"
        )
    elif situacao.get("erro"):
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = str(situacao["erro"])
    elif situacao.get("provedor_respondeu") is False:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = "o provedor não respondeu à consulta do agente"
    return resultado


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def _lida(valor) -> str:
    return {"0": "Não", "1": "Sim"}.get(_texto(valor), "(não informado)")


def ler_sms(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    resultado = _resultado("sms", caminho, arquivo, fuso, "sms")
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado):
        resultado.registros.append(Registro(
            tipo="sms",
            campos={
                "numero": _texto(item.get("address")) or "(sem número)",
                "direcao": _rotulo_do_codigo(_texto(item.get("type")), TIPOS_SMS),
                "conteudo": _texto(item.get("body")),
                "lida": _lida(item.get("read")),
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_chamadas(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    resultado = _resultado("chamada", caminho, arquivo, fuso, "chamadas")
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado):
        duracao = item.get("duration")
        resultado.registros.append(Registro(
            tipo="chamada",
            campos={
                "numero": _texto(item.get("number")) or "(sem número)",
                "contato": _texto(item.get("name")) or "(não consta no registro da chamada)",
                "direcao": _rotulo_do_codigo(_texto(item.get("type")), TIPOS_CHAMADA),
                "duracao_segundos": _texto(duracao) if duracao not in (None, "") else "0",
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_contatos(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    resultado = _resultado("contato", caminho, arquivo, fuso, "contatos")
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado):
        resultado.registros.append(Registro(
            tipo="contato",
            campos={
                "contato": _texto(item.get("display_name")) or "(sem nome)",
                "numero": _texto(item.get("data1")) or _texto(item.get("number")) or "(sem número)",
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=None,  # contato não tem data própria neste provedor
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_mms(caminho: Path, arquivo: str = "", fuso=None) -> ResultadoNormalizacao:
    """
    MMS: o cabeçalho vem de `mms.jsonl`; o texto e os anexos, de
    `mms_partes.jsonl`; os números, de `mms_enderecos.jsonl`.
    """
    resultado = _resultado("mms", caminho, arquivo, fuso, "mms")
    if resultado.acesso_negado:
        return resultado
    pasta = Path(caminho).parent
    auxiliar = ResultadoNormalizacao(tipo="mms")

    partes: dict = {}
    for _, parte in _linhas(pasta / "mms_partes.jsonl", auxiliar):
        partes.setdefault(_texto(parte.get("mid")), []).append(parte)
    enderecos: dict = {}
    for _, endereco in _linhas(pasta / "mms_enderecos.jsonl", auxiliar):
        chave = _texto(endereco.get("_mms_id")) or _texto(endereco.get("msg_id"))
        enderecos.setdefault(chave, []).append(endereco)
    resultado.descartes.extend(auxiliar.descartes)

    for numero, item in _linhas(caminho, resultado):
        identificador = _texto(item.get("_id"))
        caixa = _texto(item.get("msg_box"))
        textos, anexos = [], []
        for parte in partes.get(identificador, []):
            tipo = _texto(parte.get("ct"))
            if tipo == TIPO_TEXTO_MMS:
                textos.append(_texto(parte.get("text")))
            elif tipo and tipo != "application/smil":
                nome = _texto(parte.get("name")) or _texto(parte.get("cl")) or "(sem nome)"
                anexos.append(f"{nome} [{tipo}]")
        # Recebida: interessa quem enviou. Nas demais, para quem foi.
        procurados = (ENDERECO_MMS_DE,) if caixa == "1" else ENDERECOS_MMS_PARA
        numeros = [
            _texto(e.get("address")) for e in enderecos.get(identificador, [])
            if _texto(e.get("type")) in procurados
            and _texto(e.get("address")) not in ("", MARCADOR_DO_PROPRIO_NUMERO)
        ]
        resultado.registros.append(Registro(
            tipo="mms",
            campos={
                "numero": ", ".join(numeros) or "(número não consta nos endereços do MMS)",
                "direcao": _rotulo_do_codigo(caixa, CAIXAS_MMS),
                "assunto": _texto(item.get("sub")),
                "conteudo": "\n".join(t for t in textos if t),
                "anexo": "; ".join(anexos),
                "lida": _lida(item.get("read")),
                "identificador_no_aparelho": identificador,
            },
            # A data do MMS vem em SEGUNDOS; `momento_de_epoch` distingue pela grandeza.
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado
