"""
Características do aparelho apuradas pela própria extração.

O laudo descrevia o dispositivo apenas pelo que alguém digitou no cadastro —
marca, cor, estado, lacre. Isso é declaração, e declaração tem seu lugar;
mas a extração **lê do aparelho** fabricante, modelo, número de série,
versão do sistema e IMEI, e nada disso chegava ao documento.

Preferir o apurado ao digitado não é preciosismo: é a diferença entre o
laudo dizer "o examinador informou que é um Galaxy S20" e dizer "o aparelho
declarou-se um SM-G980F, série R58N..., Android 13". A segunda afirmação a
ferramenta sustenta; a primeira depende de quem preencheu.

Os módulos gravam o que apuraram em JSON, ao lado do relatório em prosa que
já produziam. O laudo lê daqui. Módulo que não rodou simplesmente não
contribui — e o laudo diz que aquele dado não foi apurado, em vez de
inventá-lo ou de silenciar.

**Nada aqui é verificado contra o hardware.** São os valores que o sistema
do aparelho declara de si mesmo, e num dispositivo com sistema modificado
podem não corresponder ao equipamento real. O laudo carrega essa ressalva.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .idioma import traduzir

NOME_DADOS_TECNICOS = "caracteristicas_tecnicas.json"

# Nomes que a ferramenta dá à aquisição quando NENHUM aparelho respondeu.
# Servem para nomear a pasta; não foram lidos de aparelho algum e nunca
# podem sair no laudo como "apurado do próprio dispositivo".
ID_GENERICO_ANDROID = "celular_android"
ID_GENERICO_IOS = "iphone_nao_identificado"
IDENTIFICADORES_GENERICOS = (ID_GENERICO_ANDROID, ID_GENERICO_IOS)
NOME_DADOS_IDENTIFICACAO = "identificacao.json"

PASTA_TECNICOS = "device_specs"
PASTA_IDENTIFICACAO = "identificacao"

# Rótulo de cada campo no laudo, e a ordem em que aparecem. Campo ausente
# não vira linha em branco: simplesmente não entra, e a ausência é dita.
# (chave do dado, chave do catálogo p/ o rótulo). O rótulo é exibido no laudo
# e traduz no idioma do caso; a chave e o valor apurado são o dado.
CAMPOS = (
    ("fabricante", "ap_fabricante"),
    ("modelo", "ap_modelo"),
    ("marca", "ap_marca"),
    ("numero_serie", "ap_numero_serie"),
    ("imei", "ap_imei"),
    ("versao_android", "ap_versao_android"),
    ("versao_ios", "ap_versao_ios"),
    ("build_ios", "ap_build_ios"),
    ("numero_do_modelo", "ap_numero_modelo"),
    ("nome_do_aparelho", "ap_nome_aparelho"),
    ("udid", "ap_udid"),
    ("imei_2", "ap_imei_2"),
    ("numero_telefone", "ap_numero_telefone"),
    ("iccid", "ap_iccid"),
    ("endereco_wifi", "ap_endereco_wifi"),
    ("backup_cifrado", "ap_backup_cifrado"),
    ("versao_sdk", "ap_versao_sdk"),
    ("patch_seguranca", "ap_patch_seguranca"),
    ("arquitetura_cpu", "ap_arquitetura_cpu"),
    ("impressao_digital_build", "ap_impressao_build"),
    ("tipo_build", "ap_tipo_build"),
    ("estado_criptografia", "ap_estado_cripto"),
    ("tipo_criptografia", "ap_tipo_cripto"),
    ("boot_verificado", "ap_boot_verificado"),
    ("bootloader_travado", "ap_bootloader_travado"),
    ("versao_bootloader", "ap_versao_bootloader"),
    ("banda_base", "ap_banda_base"),
    ("operadora_sim", "ap_operadora_sim"),
    ("fuso_horario", "ap_fuso_horario"),
    ("id_conexao", "ap_id_conexao"),
)


@dataclass
class CaracteristicasApuradas:
    """O que a extração leu do próprio aparelho."""

    valores: dict = field(default_factory=dict)

    @property
    def vazio(self) -> bool:
        return not any(str(v).strip() for v in self.valores.values())

    def em_pares(self, idioma=None) -> list:
        """(rótulo, valor) na ordem do laudo, só o que foi apurado. O rótulo
        sai no idioma pedido; o valor apurado nunca é traduzido."""
        pares = []
        for chave, rotulo_chave in CAMPOS:
            valor = str(self.valores.get(chave, "") or "").strip()
            if valor:
                pares.append((traduzir(rotulo_chave, idioma), valor))
        return pares


def gravar_tecnicos(pasta_aquisicao: Path, valores: dict) -> Path:
    """Grava o que o módulo de características técnicas apurou."""
    return _gravar(pasta_aquisicao, PASTA_TECNICOS, NOME_DADOS_TECNICOS, valores)


def gravar_identificacao(pasta_aquisicao: Path, valores: dict) -> Path:
    """Grava o que o módulo de identificação apurou (IMEI, contas)."""
    return _gravar(pasta_aquisicao, PASTA_IDENTIFICACAO, NOME_DADOS_IDENTIFICACAO, valores)


def _gravar(pasta_aquisicao: Path, subpasta: str, nome: str, valores: dict) -> Path:
    pasta = Path(pasta_aquisicao) / subpasta
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    limpos = {c: str(v) for c, v in valores.items() if str(v or "").strip()}
    caminho.write_text(
        json.dumps(limpos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho


def ler_caracteristicas(pasta_aquisicao: Path) -> CaracteristicasApuradas:
    """
    Consolida o que os módulos apuraram sobre o aparelho.

    Lê os dois registros de forma independente: se apenas um dos módulos foi
    executado, o laudo ainda mostra o que aquele apurou. Cada módulo é dono
    do que grava, e nenhum depende do outro ter rodado.
    """
    pasta = Path(pasta_aquisicao)
    valores: dict = {}
    for subpasta, nome in (
        (PASTA_TECNICOS, NOME_DADOS_TECNICOS),
        (PASTA_IDENTIFICACAO, NOME_DADOS_IDENTIFICACAO),
    ):
        caminho = pasta / subpasta / nome
        if not caminho.is_file():
            continue
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict):
            valores.update({c: v for c, v in dados.items() if str(v or "").strip()})
    return CaracteristicasApuradas(valores=valores)
