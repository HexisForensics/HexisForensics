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

from core.idioma import traduzir
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


def _linhas(caminho: Path, resultado: ResultadoNormalizacao, idioma=None) -> Iterator[tuple]:
    """Rende `(numero_da_linha, objeto)`; linha ilegível vira descarte."""
    try:
        texto = Path(caminho).read_text(encoding="utf-8")
    except OSError as erro:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = traduzir("ag_arquivo_ilegivel", idioma, erro=erro)
        return
    for numero, linha in enumerate(texto.splitlines(), 1):
        if not linha.strip():
            continue
        try:
            objeto = json.loads(linha)
        except ValueError:
            resultado.descartes.append(
                Descarte(numero, linha[:200], traduzir("ag_desc_nao_json", idioma)))
            continue
        if isinstance(objeto, dict):
            yield numero, objeto
        else:
            resultado.descartes.append(
                Descarte(numero, linha[:200], traduzir("ag_desc_nao_registro", idioma)))


def _resultado(tipo: str, caminho: Path, arquivo: str, fuso, fonte: str,
               idioma=None) -> ResultadoNormalizacao:
    resultado = ResultadoNormalizacao(
        tipo=tipo, arquivo_de_origem=arquivo, fuso_declarado=nome_do_fuso(fuso, idioma),
        significado_do_vazio=traduzir("ag_vazio", idioma), idioma=idioma,
    )
    situacao = situacao_das_fontes(ler_estado(Path(caminho).parent)).get(fonte)
    if situacao is None:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = traduzir("ag_fonte_ausente", idioma)
    elif situacao.get("erro"):
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = str(situacao["erro"])
    elif situacao.get("provedor_respondeu") is False:
        resultado.acesso_negado = True
        resultado.trecho_da_recusa = traduzir("ag_provedor_mudo", idioma)
    return resultado


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def _lida(valor, idioma=None) -> str:
    chave = {"0": "nm_nao", "1": "nm_sim"}.get(_texto(valor), "nm_nao_informado")
    return traduzir(chave, idioma)


def ler_sms(caminho: Path, arquivo: str = "", fuso=None, idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("sms", caminho, arquivo, fuso, "sms", idioma)
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado, idioma):
        resultado.registros.append(Registro(
            tipo="sms",
            campos={
                "numero": _texto(item.get("address")) or traduzir("nm_sem_numero", idioma),
                "direcao": _rotulo_do_codigo(_texto(item.get("type")), TIPOS_SMS, idioma),
                "conteudo": _texto(item.get("body")),
                "lida": _lida(item.get("read"), idioma),
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_chamadas(caminho: Path, arquivo: str = "", fuso=None, idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("chamada", caminho, arquivo, fuso, "chamadas", idioma)
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado, idioma):
        duracao = item.get("duration")
        resultado.registros.append(Registro(
            tipo="chamada",
            campos={
                "numero": _texto(item.get("number")) or traduzir("nm_sem_numero", idioma),
                "contato": _texto(item.get("name")) or traduzir("ag_sem_contato_chamada", idioma),
                "direcao": _rotulo_do_codigo(_texto(item.get("type")), TIPOS_CHAMADA, idioma),
                "duracao_segundos": _texto(duracao) if duracao not in (None, "") else "0",
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_contatos(caminho: Path, arquivo: str = "", fuso=None, idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("contato", caminho, arquivo, fuso, "contatos", idioma)
    if resultado.acesso_negado:
        return resultado
    for numero, item in _linhas(caminho, resultado, idioma):
        resultado.registros.append(Registro(
            tipo="contato",
            campos={
                "contato": _texto(item.get("display_name")) or traduzir("nm_sem_nome", idioma),
                "numero": (_texto(item.get("data1")) or _texto(item.get("number"))
                           or traduzir("nm_sem_numero", idioma)),
                "identificador_no_aparelho": _texto(item.get("_id")),
            },
            momento=None,  # contato não tem data própria neste provedor
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado


def ler_mms(caminho: Path, arquivo: str = "", fuso=None, idioma=None) -> ResultadoNormalizacao:
    """
    MMS: o cabeçalho vem de `mms.jsonl`; o texto e os anexos, de
    `mms_partes.jsonl`; os números, de `mms_enderecos.jsonl`.
    """
    resultado = _resultado("mms", caminho, arquivo, fuso, "mms", idioma)
    if resultado.acesso_negado:
        return resultado
    pasta = Path(caminho).parent
    auxiliar = ResultadoNormalizacao(tipo="mms")

    partes: dict = {}
    for _, parte in _linhas(pasta / "mms_partes.jsonl", auxiliar, idioma):
        partes.setdefault(_texto(parte.get("mid")), []).append(parte)
    enderecos: dict = {}
    for _, endereco in _linhas(pasta / "mms_enderecos.jsonl", auxiliar, idioma):
        chave = _texto(endereco.get("_mms_id")) or _texto(endereco.get("msg_id"))
        enderecos.setdefault(chave, []).append(endereco)
    resultado.descartes.extend(auxiliar.descartes)

    for numero, item in _linhas(caminho, resultado, idioma):
        identificador = _texto(item.get("_id"))
        caixa = _texto(item.get("msg_box"))
        textos, anexos = [], []
        for parte in partes.get(identificador, []):
            tipo = _texto(parte.get("ct"))
            if tipo == TIPO_TEXTO_MMS:
                textos.append(_texto(parte.get("text")))
            elif tipo and tipo != "application/smil":
                nome = (_texto(parte.get("name")) or _texto(parte.get("cl"))
                        or traduzir("nm_sem_nome", idioma))
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
                "numero": ", ".join(numeros) or traduzir("ag_mms_sem_endereco", idioma),
                "direcao": _rotulo_do_codigo(caixa, CAIXAS_MMS, idioma),
                "assunto": _texto(item.get("sub")),
                "conteudo": "\n".join(t for t in textos if t),
                "anexo": "; ".join(anexos),
                "lida": _lida(item.get("read"), idioma),
                "identificador_no_aparelho": identificador,
            },
            # A data do MMS vem em SEGUNDOS; `momento_de_epoch` distingue pela grandeza.
            momento=momento_de_epoch(item.get("date"), fuso),
            arquivo_de_origem=arquivo,
            linha_de_origem=numero,
            bruto=json.dumps(item, ensure_ascii=False),
        ))
    return resultado
