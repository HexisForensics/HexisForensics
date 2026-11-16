"""
Ficha do Aparelho: a capa de leitura rápida de uma aquisição.

Reúne, num só lugar, os campos que PRIMEIRO importam numa investigação —
o bloqueio em que o aparelho foi recebido, a identificação do aparelho e da
linha, o estado de segurança e o desfecho da coleta — cada um com a fonte,
dentro da aquisição selada, de onde o valor pode ser conferido.

Nasceu de uma constatação na leitura real das aquisições (15/11/2026): o
material bruto está sempre completo e selado, mas cada resumo de pasta
lidera com o que FALTOU (IMEI negado, agenda vazia) e enterra o que VEIO
(ICCID, número, chamadas). Quem lê a capa podia concluir "aparelho não
identificado" quando a linha estava, na verdade, plenamente identificada.

A regra desta ficha, por isso, é uma só: **abre com o que foi obtido; a
ressalva vem depois, não no lugar.** E para nunca virar a "capa de aparência
infalível" que serviria à tese de defesa, obedece a três limites:

1. **Derivada do que já está gravado e selado** — nada é digitado à mão nem
   adivinhado. Cada campo vem de um registro da aquisição.
2. **Cada campo cita a fonte** — o arquivo, dentro da aquisição, de onde o
   leitor confere o valor.
3. **Carrega a ressalva junto** — campo que a extração não obteve consta
   como NÃO APURADO. A ficha mostra o que faltou tanto quanto o que veio, e
   **NÃO APURADO nunca significa ausência do dado no aparelho**: significa
   que a coleta, por suas limitações, não o alcançou.

Pura por desenho: não conhece Qt nem PDF. Quem imprime (services) lê daqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from core.aparelho import ler_caracteristicas
from core.desfecho import NOME_DESFECHO, PASTA_DESFECHO, ler_desfecho
from core.idioma import traduzir

# Marcador canônico em PT, mantido para quem importa a constante (testes) e
# como valor de referência. A Ficha é documento DERIVADO: o que ela EXIBE é
# resolvido por `traduzir("fha_nao_apurado")` no idioma ativo (PT idêntico a
# esta constante). O "NÃO APURADO" dos extratores SELADOS é literal próprio
# deles, em PT, e não passa por aqui (Fase 3).
NAO_APURADO = "NÃO APURADO"

PASTA_ESTADO = "estado_inicial"
NOME_BLOQUEIO = "bloqueio_de_tela.txt"

# Fonte comum dos campos que a extração apura sobre o aparelho e a linha. Os
# dois módulos (características técnicas e identificação) gravam cada um o seu
# JSON; `ler_caracteristicas` os consolida. O texto fica no catálogo
# (`fha_fonte_apurado`); os nomes das pastas são dado e não se traduzem.

LARGURA = 70


@dataclass
class CampoDaFicha:
    """Uma linha da ficha: rótulo, valor, e a fonte de onde o valor veio."""

    rotulo: str
    valor: str
    fonte: str = ""
    apurado: bool = True  # False quando o valor é NÃO APURADO


@dataclass
class FichaDoAparelho:
    aquisicao: str
    campos: List[CampoDaFicha] = field(default_factory=list)
    # (nome do módulo, [chaves de ressalva]) de cada módulo que teve ressalva.
    ressalvas: List[Tuple[str, List[str]]] = field(default_factory=list)

    @property
    def algum_apurado(self) -> bool:
        return any(c.apurado for c in self.campos)


def ler_bloqueio_ao_receber(pasta_aquisicao: Path) -> Tuple[str, str]:
    """
    (valor, fonte) do estado de bloqueio em que o aparelho foi recebido.

    Lê o `deviceLocked` do `dumpsys` preservado em `estado_inicial/`. É
    defensivo de propósito: qualquer formato inesperado (ou arquivo ausente)
    vira NÃO APURADO, nunca um palpite. O formato do `dumpsys` varia entre
    aparelhos e versões de Android, e é exatamente aqui que um parser
    descuidado afirmaria o que não leu.
    """
    caminho = Path(pasta_aquisicao) / PASTA_ESTADO / NOME_BLOQUEIO
    fonte = f"{PASTA_ESTADO}/{NOME_BLOQUEIO}"
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return traduzir("fha_nao_apurado"), ""
    correspondencia = re.search(r"deviceLocked=([01])", texto)
    if not correspondencia:
        return traduzir("fha_nao_apurado"), fonte
    chave = "fha_desbloqueado" if correspondencia.group(1) == "0" else "fha_bloqueado"
    return traduzir(chave), fonte


# Campos fixos da ficha, na ordem da leitura de uma investigação: o aparelho,
# depois a linha, depois a segurança. Ausentes constam como NÃO APURADO — a
# ficha não esconde o que a coleta não alcançou.
# (chave do rótulo no catálogo, chave do valor nas características apuradas).
_CAMPOS_FIXOS = (
    ("fha_l_fabricante", "fabricante"),
    ("fha_l_modelo", "modelo"),
    ("fha_l_marca", "marca"),
    ("fha_l_numero_serie", "numero_serie"),
    ("fha_l_imei", "imei"),
    ("fha_l_numero_telefone", "numero_telefone"),
    ("fha_l_iccid", "iccid"),
    ("fha_l_operadora", "operadora_sim"),
    ("fha_l_patch", "patch_seguranca"),
    ("fha_l_cripto", "estado_criptografia"),
    ("fha_l_boot", "boot_verificado"),
    ("fha_l_bootloader", "bootloader_travado"),
)

# Campos que só entram quando foram apurados: não poluem a ficha com
# NÃO APURADO de coisa que nem todo aparelho tem (segundo chip, UDID de iOS).
_CAMPOS_OPCIONAIS = (
    ("fha_l_imei2", "imei_2"),
    ("fha_l_udid", "udid"),
    ("fha_l_nome_aparelho", "nome_do_aparelho"),
)


def montar_ficha(pasta_aquisicao: Path) -> FichaDoAparelho:
    """Monta a ficha a partir do que já está gravado e selado na aquisição."""
    pasta = Path(pasta_aquisicao)
    apuradas = ler_caracteristicas(pasta).valores
    desfecho = ler_desfecho(pasta)

    def apurado(chave: str) -> str:
        return str(apuradas.get(chave, "") or "").strip()

    nao_apurado = traduzir("fha_nao_apurado")
    fonte_apurado = traduzir("fha_fonte_apurado")
    campos: List[CampoDaFicha] = []

    # 1) Bloqueio ao receber — o campo-rei da cadeia de custódia, declarado
    #    pelo sistema (não pelo examinador).
    valor_bloqueio, fonte_bloqueio = ler_bloqueio_ao_receber(pasta)
    campos.append(
        CampoDaFicha(
            traduzir("fha_l_bloqueio"), valor_bloqueio, fonte_bloqueio,
            apurado=valor_bloqueio != nao_apurado,
        )
    )

    # 2) Versão do sistema — uma linha, seja Android ou iOS.
    versao = apurado("versao_android") or apurado("versao_ios")
    linhas_fixas = list(_CAMPOS_FIXOS)
    linhas_fixas.insert(8, ("fha_l_versao", "__versao__"))

    for rotulo_key, chave in linhas_fixas:
        rotulo = traduzir(rotulo_key)
        valor = versao if chave == "__versao__" else apurado(chave)
        if valor:
            campos.append(CampoDaFicha(rotulo, valor, fonte_apurado, apurado=True))
        else:
            campos.append(CampoDaFicha(rotulo, nao_apurado, fonte_apurado, apurado=False))

    # 2b) Opcionais, só quando apurados.
    for rotulo_key, chave in _CAMPOS_OPCIONAIS:
        valor = apurado(chave)
        if valor:
            campos.append(CampoDaFicha(traduzir(rotulo_key), valor, fonte_apurado, apurado=True))

    # 3) Desfecho da coleta — o que foi obtido, e o que ficou com ressalva.
    fonte_desfecho = f"{PASTA_DESFECHO}/{NOME_DESFECHO}"
    rotulo_desfecho = traduzir("fha_l_desfecho")
    if desfecho.vazio:
        campos.append(CampoDaFicha(rotulo_desfecho, nao_apurado, fonte_desfecho, apurado=False))
    else:
        campos.append(CampoDaFicha(rotulo_desfecho, desfecho.resumo, fonte_desfecho, apurado=True))

    ressalvas = [(m.nome, list(m.ressalvas)) for m in desfecho.modulos if m.ressalvas]

    return FichaDoAparelho(aquisicao=pasta.name, campos=campos, ressalvas=ressalvas)


def render_texto(ficha: FichaDoAparelho) -> str:
    """Versão em texto da ficha — a mesma que o PDF imprime, legível no bloco de notas."""
    linhas = [
        "=" * LARGURA,
        traduzir("fha_titulo_pdf").center(LARGURA),
        traduzir("fha_sub_txt").center(LARGURA),
        "=" * LARGURA,
        traduzir("fha_aquisicao_txt", valor=ficha.aquisicao),
        "",
    ]
    largura_rotulo = max((len(c.rotulo) for c in ficha.campos), default=0)
    for campo in ficha.campos:
        linhas.append(f"{campo.rotulo.ljust(largura_rotulo)}  {campo.valor}")
        if campo.fonte:
            linhas.append(f"{' ' * largura_rotulo}  {traduzir('fha_fonte_prefixo')}{campo.fonte}")

    if ficha.ressalvas:
        linhas += ["", "-" * LARGURA, traduzir("fha_ressalvas_txt")]
        for nome, chaves in ficha.ressalvas:
            linhas.append(f"  • {nome}: {', '.join(chaves)}")

    linhas += [
        "",
        "-" * LARGURA,
        traduzir("fha_rodape_txt"),
        "=" * LARGURA,
    ]
    return "\n".join(linhas) + "\n"
