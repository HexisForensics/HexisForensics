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

NAO_APURADO = "NÃO APURADO"

PASTA_ESTADO = "estado_inicial"
NOME_BLOQUEIO = "bloqueio_de_tela.txt"

# Fonte comum dos campos que a extração apura sobre o aparelho e a linha. Os
# dois módulos (características técnicas e identificação) gravam cada um o seu
# JSON; `ler_caracteristicas` os consolida. A ficha aponta as duas pastas,
# para o leitor conferir o campo na que o contém.
FONTE_APURADO = "device_specs/ e identificacao/ (características apuradas)"

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
        return NAO_APURADO, ""
    correspondencia = re.search(r"deviceLocked=([01])", texto)
    if not correspondencia:
        return NAO_APURADO, fonte
    return ("DESBLOQUEADO" if correspondencia.group(1) == "0" else "BLOQUEADO"), fonte


# Campos fixos da ficha, na ordem da leitura de uma investigação: o aparelho,
# depois a linha, depois a segurança. Ausentes constam como NÃO APURADO — a
# ficha não esconde o que a coleta não alcançou.
_CAMPOS_FIXOS = (
    ("Fabricante", "fabricante"),
    ("Modelo", "modelo"),
    ("Marca / nome comercial", "marca"),
    ("Número de série", "numero_serie"),
    ("IMEI", "imei"),
    ("Número de telefone", "numero_telefone"),
    ("ICCID do chip", "iccid"),
    ("Operadora do SIM", "operadora_sim"),
    ("Patch de segurança", "patch_seguranca"),
    ("Estado da criptografia", "estado_criptografia"),
    ("Estado do boot verificado", "boot_verificado"),
    ("Bootloader travado (1 = sim)", "bootloader_travado"),
)

# Campos que só entram quando foram apurados: não poluem a ficha com
# NÃO APURADO de coisa que nem todo aparelho tem (segundo chip, UDID de iOS).
_CAMPOS_OPCIONAIS = (
    ("IMEI (segundo)", "imei_2"),
    ("UDID", "udid"),
    ("Nome dado ao aparelho", "nome_do_aparelho"),
)


def montar_ficha(pasta_aquisicao: Path) -> FichaDoAparelho:
    """Monta a ficha a partir do que já está gravado e selado na aquisição."""
    pasta = Path(pasta_aquisicao)
    apuradas = ler_caracteristicas(pasta).valores
    desfecho = ler_desfecho(pasta)

    def apurado(chave: str) -> str:
        return str(apuradas.get(chave, "") or "").strip()

    campos: List[CampoDaFicha] = []

    # 1) Bloqueio ao receber — o campo-rei da cadeia de custódia, declarado
    #    pelo sistema (não pelo examinador).
    valor_bloqueio, fonte_bloqueio = ler_bloqueio_ao_receber(pasta)
    campos.append(
        CampoDaFicha(
            "Bloqueio ao ser recebido", valor_bloqueio, fonte_bloqueio,
            apurado=valor_bloqueio != NAO_APURADO,
        )
    )

    # 2) Versão do sistema — uma linha, seja Android ou iOS.
    versao = apurado("versao_android") or apurado("versao_ios")
    linhas_fixas = list(_CAMPOS_FIXOS)
    linhas_fixas.insert(8, ("Versão do sistema", "__versao__"))

    for rotulo, chave in linhas_fixas:
        valor = versao if chave == "__versao__" else apurado(chave)
        if valor:
            campos.append(CampoDaFicha(rotulo, valor, FONTE_APURADO, apurado=True))
        else:
            campos.append(CampoDaFicha(rotulo, NAO_APURADO, FONTE_APURADO, apurado=False))

    # 2b) Opcionais, só quando apurados.
    for rotulo, chave in _CAMPOS_OPCIONAIS:
        valor = apurado(chave)
        if valor:
            campos.append(CampoDaFicha(rotulo, valor, FONTE_APURADO, apurado=True))

    # 3) Desfecho da coleta — o que foi obtido, e o que ficou com ressalva.
    fonte_desfecho = f"{PASTA_DESFECHO}/{NOME_DESFECHO}"
    if desfecho.vazio:
        campos.append(CampoDaFicha("Desfecho da coleta", NAO_APURADO, fonte_desfecho, apurado=False))
    else:
        campos.append(CampoDaFicha("Desfecho da coleta", desfecho.resumo, fonte_desfecho, apurado=True))

    ressalvas = [(m.nome, list(m.ressalvas)) for m in desfecho.modulos if m.ressalvas]

    return FichaDoAparelho(aquisicao=pasta.name, campos=campos, ressalvas=ressalvas)


def render_texto(ficha: FichaDoAparelho) -> str:
    """Versão em texto da ficha — a mesma que o PDF imprime, legível no bloco de notas."""
    linhas = [
        "=" * LARGURA,
        "FICHA DO APARELHO".center(LARGURA),
        "Leitura rápida — abre com o que foi obtido".center(LARGURA),
        "=" * LARGURA,
        f"Aquisição: {ficha.aquisicao}",
        "",
    ]
    largura_rotulo = max((len(c.rotulo) for c in ficha.campos), default=0)
    for campo in ficha.campos:
        linhas.append(f"{campo.rotulo.ljust(largura_rotulo)}  {campo.valor}")
        if campo.fonte:
            linhas.append(f"{' ' * largura_rotulo}  fonte: {campo.fonte}")

    if ficha.ressalvas:
        linhas += ["", "-" * LARGURA, "RESSALVAS DECLARADAS"]
        for nome, chaves in ficha.ressalvas:
            linhas.append(f"  • {nome}: {', '.join(chaves)}")

    linhas += [
        "",
        "-" * LARGURA,
        "NÃO APURADO não significa ausência do dado no aparelho: significa que",
        "a coleta, por suas limitações, não o alcançou. O material bruto e",
        "selado de cada campo está na aquisição, no caminho indicado em 'fonte'.",
        "=" * LARGURA,
    ]
    return "\n".join(linhas) + "\n"
