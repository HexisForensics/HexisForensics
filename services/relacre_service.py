"""
Reaposição de lacre: registra, DEPOIS da perícia, o novo lacre aposto na
peça quando o lacre original é rompido para o exame.

Por que é complemento, e não campo da aquisição: a `cadeia_custodia.txt` é
SELADA no momento da coleta, e o novo lacre ainda não existe nesse instante
— ele é aposto depois, quando o relacre físico acontece. Registrá-lo no selo
seria selar um fato que não ocorreu. Então ele entra como COMPLEMENTO do
caso (a regra do aditamento: não se rasura folha selada, junta-se aditivo),
com a foto do novo lacre preservada no nível do caso, fora do selo, e com o
seu SHA-256 anotado.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.case import (
    idioma_para_selar,
    juntar_complemento,
    pasta_do_caso,
    sanitizar_nome,
)
from services.idioma import traduzir

# Fotos do novo lacre, no nível do caso e FORA de qualquer aquisição selada.
PASTA_REAPOSICOES = "reaposicoes"


@dataclass
class ResultadoReaposicao:
    sucesso: bool
    mensagem: str = ""
    caminho_complemento: Optional[Path] = None
    erro: str = ""


def registrar_reaposicao(pasta_aquisicao: Path, dados: dict) -> ResultadoReaposicao:
    """
    Grava o complemento de reaposição de lacre da aquisição.

    `dados`: {numero (obrigatório), data, por, registro, foto (Path, obrigatória)}.
    A foto do novo lacre é copiada para `<caso>/reaposicoes/`, fora do selo, e
    o seu SHA-256 entra no texto do complemento.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    caso = pasta_do_caso(pasta_aquisicao)
    idi = idioma_para_selar(caso)

    numero = str(dados.get("numero", "") or "").strip()
    foto = dados.get("foto")
    if not numero:
        return ResultadoReaposicao(False, erro=traduzir("rl_erro_numero", idi))
    if not foto or not Path(foto).is_file():
        return ResultadoReaposicao(False, erro=traduzir("rl_erro_foto", idi))

    carimbo = datetime.now()
    pasta_fotos = caso / PASTA_REAPOSICOES
    pasta_fotos.mkdir(parents=True, exist_ok=True)
    nome_foto = (f"lacre_{sanitizar_nome(numero).lower()[:32]}_"
                 f"{carimbo.strftime('%Y%m%d_%H%M%S')}{Path(foto).suffix.lower()}")
    destino = pasta_fotos / nome_foto
    try:
        shutil.copy2(foto, destino)
        sha = hashlib.sha256(destino.read_bytes()).hexdigest()
    except OSError as erro:
        return ResultadoReaposicao(False, erro=str(erro))

    def opcional(chave, chave_catalogo):
        valor = str(dados.get(chave, "") or "").strip()
        return [traduzir(chave_catalogo, idi, valor=valor)] if valor else []

    linhas = [
        traduzir("rl_comp_aquisicao", idi, aquisicao=pasta_aquisicao.name),
        traduzir("rl_comp_numero", idi, valor=numero),
    ]
    linhas += opcional("data", "rl_comp_data")
    linhas += opcional("por", "rl_comp_por")
    linhas += opcional("registro", "rl_comp_registro")
    linhas += [
        traduzir("rl_comp_foto", idi, nome=destino.name),
        traduzir("rl_comp_sha", idi, valor=sha),
        "",
        traduzir("rl_comp_nota", idi),
    ]
    texto = "\n".join(linhas)

    try:
        caminho = juntar_complemento(
            caso, traduzir("rl_comp_titulo", idi, aquisicao=pasta_aquisicao.name), texto)
    except OSError as erro:
        return ResultadoReaposicao(False, erro=str(erro))

    return ResultadoReaposicao(
        True, mensagem=traduzir("rl_ok", idi, aquisicao=pasta_aquisicao.name),
        caminho_complemento=caminho)
