"""
Dossiê de uma aquisição: tudo o que os documentos precisam saber dela,
lido uma vez, do que está gravado.

O Relatório de Extração e o Laudo Pericial descrevem a mesma aquisição.
Se cada um lesse os registros do seu jeito, na primeira correção feita de
um lado só os dois passariam a discordar sobre o mesmo exame — e dois
documentos da mesma ferramenta em desacordo valem menos que nenhum.

Nada aqui é digitado nem recalculado a partir de suposição: cada campo
vem de um registro da aquisição (a maioria, selado). Registro ausente
fica ausente, e quem imprime decide como dizer isso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from core.android.extractors.base import PASTA_AQUISICAO
from core.aparelho import ler_caracteristicas
from core.categorias import Categoria, classificar
from core.case import (
    CAMPOS_DO_DISPOSITIVO,
    NOME_CADEIA_CUSTODIA,
    PASTA_FOTOS,
    descrever_aquisicao,
    pasta_do_caso,
)
from core.desfecho import PASTA_DESFECHO, DesfechoDaColeta, ler_desfecho
from core.fundamento import PASTA_AUTORIZACAO, Autorizacao, ler_autorizacao_da_aquisicao
from core.hashing import (
    PREFIXO_CONFERENCIA,
    calcular_sha256,
    ler_manifesto,
    localizar_manifesto,
)
from core.metodo import PASTA_METODO, MetodoDeclarado, ler_metodo
from core.operador import ler_da_aquisicao as ler_operador
from core.procedimento import NOME_ARQUIVO as NOME_REGISTRO
from core.relogio import ler_desvio_registrado
from services.case_service import ROTULOS_FORA_DO_CASO, VALORES_VAZIOS, ler_cadeia_custodia

_INICIO_DE_EVENTO = re.compile(r"^\[([^\]]+)\]\s+(.*)$")

# Pastas em que a própria aquisição grava os SEUS registros: prova de cópia,
# erros, desfecho, método, autorização e fotos da peça. Não são arquivos do
# dispositivo, e ficam fora da classificação por categoria — junto com os
# arquivos soltos na raiz da aquisição, que também são dela.
PASTAS_DE_REGISTRO = frozenset(
    [PASTA_AQUISICAO, "erros", PASTA_DESFECHO, PASTA_METODO, PASTA_AUTORIZACAO, PASTA_FOTOS]
)
EXTENSOES_DE_FOTO = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


@dataclass
class Evento:
    """Uma entrada do registro do procedimento."""

    carimbo: str
    titulo: str
    linhas: List[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.linhas)


@dataclass
class Dossie:
    pasta: Path
    caso: str
    plataforma: str = ""
    momento: Optional[datetime] = None

    # Cadeia de custódia: o que foi DECLARADO no cadastro.
    dados_do_caso: List[Tuple[str, str]] = field(default_factory=list)
    peca: List[Tuple[str, str]] = field(default_factory=list)
    tem_cadeia_de_custodia: bool = False
    fotos: List[Path] = field(default_factory=list)

    # O que a extração APUROU do próprio dispositivo.
    apuradas: List[Tuple[str, str]] = field(default_factory=list)

    # Registro do procedimento.
    cabecalho_do_registro: List[Tuple[str, str]] = field(default_factory=list)
    eventos: List[Evento] = field(default_factory=list)
    registro_bruto: str = ""
    # Desvio do relógio do aparelho medido na aquisição (segundos; None: não medido).
    desvio_do_relogio: Optional[int] = None

    # Quem executou. `None` = aquisição anterior ao registro de operador.
    operador: Optional[object] = None
    conta_da_estacao: str = ""

    metodo: MetodoDeclarado = field(default_factory=MetodoDeclarado)
    desfecho: DesfechoDaColeta = field(default_factory=DesfechoDaColeta)
    autorizacao: Autorizacao = field(default_factory=Autorizacao)

    # Selo.
    manifesto: Optional[Path] = None
    sha256_do_manifesto: str = ""
    hashes: dict = field(default_factory=dict)
    tamanhos: dict = field(default_factory=dict)
    ausentes_no_disco: List[str] = field(default_factory=list)
    ultima_conferencia: str = ""

    # ------------------------------------------------------------------
    @property
    def de_teste(self) -> bool:
        """Aquisição feita pela conta de testes (Forensic Admin)."""
        return bool(self.operador is not None and getattr(self.operador, "de_teste", False))

    @property
    def rastreio(self) -> str:
        return f"{self.caso}  ·  {self.pasta.name}"

    @property
    def lacre(self) -> str:
        return dict(self.peca).get("Lacre", "")

    @property
    def equipamento(self) -> str:
        return dict(self.peca).get("Equipamento", "")

    @property
    def identificador_do_dispositivo(self) -> str:
        return dict(self.cabecalho_do_registro).get("Dispositivo", "")

    @property
    def abertura(self) -> str:
        return dict(self.cabecalho_do_registro).get("Abertura", "")

    @property
    def encerramento(self) -> str:
        for evento in reversed(self.eventos):
            if evento.titulo.startswith("ENCERRAMENTO"):
                return evento.carimbo
        return ""

    def evento(self, titulo: str) -> Optional[Evento]:
        """O primeiro evento com este título, ou `None`."""
        for evento in self.eventos:
            if evento.titulo == titulo:
                return evento
        return None

    def eventos_com(self, titulo: str) -> List[Evento]:
        return [evento for evento in self.eventos if evento.titulo == titulo]

    @property
    def ambiente(self) -> List[Tuple[str, str]]:
        """O ambiente gravado NO DIA — nunca o da estação que imprime hoje."""
        evento = self.evento("AMBIENTE DA ESTAÇÃO FORENSE")
        pares = []
        for linha in evento.linhas if evento else []:
            if ":" in linha:
                chave, valor = linha.split(":", 1)
                pares.append((chave.strip(), valor.strip()))
        return pares

    @property
    def total_de_arquivos(self) -> int:
        return len(self.hashes)

    @property
    def total_de_bytes(self) -> int:
        return sum(self.tamanhos.values())

    @property
    def arquivos_adquiridos(self) -> List[Tuple[str, int]]:
        """
        `(caminho, bytes)` do material adquirido que está sob o selo, sem os
        registros da própria aquisição (ver `PASTAS_DE_REGISTRO`).
        """
        return [
            (relativo, self.tamanhos.get(relativo, 0))
            for relativo in sorted(self.hashes)
            if "/" in relativo and relativo.split("/", 1)[0] not in PASTAS_DE_REGISTRO
        ]

    @property
    def categorias(self) -> List[Categoria]:
        return classificar(self.arquivos_adquiridos)

    @property
    def inventario(self) -> List[Tuple[str, int, int]]:
        """(pasta de primeiro nível, arquivos, bytes) do material selado."""
        grupos: dict = {}
        for relativo in self.hashes:
            topo = relativo.split("/", 1)[0] if "/" in relativo else "(raiz da aquisição)"
            arquivos, tamanho = grupos.get(topo, (0, 0))
            grupos[topo] = (arquivos + 1, tamanho + self.tamanhos.get(relativo, 0))
        return sorted((nome, n, b) for nome, (n, b) in grupos.items())


def _ler_registro(dossie: Dossie) -> None:
    caminho = dossie.pasta / NOME_REGISTRO
    try:
        dossie.registro_bruto = caminho.read_text(encoding="utf-8")
    except OSError:
        return

    atual: Optional[Evento] = None
    for linha in dossie.registro_bruto.splitlines():
        inicio = _INICIO_DE_EVENTO.match(linha)
        if inicio:
            atual = Evento(carimbo=inicio.group(1), titulo=inicio.group(2).strip())
            dossie.eventos.append(atual)
        elif atual is not None:
            if linha.strip():
                atual.linhas.append(linha.strip())
        elif ":" in linha and not linha.startswith("="):
            chave, valor = linha.split(":", 1)
            dossie.cabecalho_do_registro.append((chave.strip(), valor.strip()))


def _ler_cadeia(dossie: Dossie) -> None:
    arquivo = dossie.pasta / NOME_CADEIA_CUSTODIA
    if not arquivo.is_file():
        return
    dossie.tem_cadeia_de_custodia = True
    dados = ler_cadeia_custodia(arquivo)

    def limpo(valor: str) -> str:
        return "" if valor in VALORES_VAZIOS else valor

    dossie.peca = [(rotulo, limpo(dados.get(rotulo, ""))) for _, rotulo in CAMPOS_DO_DISPOSITIVO]
    dossie.dados_do_caso = [
        (rotulo, limpo(valor)) for rotulo, valor in dados.items()
        if rotulo not in ROTULOS_FORA_DO_CASO
    ]

    pasta_fotos = dossie.pasta / PASTA_FOTOS
    if pasta_fotos.is_dir():
        dossie.fotos = sorted(
            foto for foto in pasta_fotos.iterdir()
            if foto.is_file() and foto.suffix.lower() in EXTENSOES_DE_FOTO
        )


def _ler_selo(dossie: Dossie) -> None:
    dossie.manifesto = localizar_manifesto(dossie.pasta)
    if dossie.manifesto is None:
        return
    dossie.sha256_do_manifesto = calcular_sha256(dossie.manifesto)
    try:
        dossie.hashes = ler_manifesto(dossie.manifesto)
    except (OSError, ValueError):
        dossie.hashes = {}
    for relativo in dossie.hashes:
        try:
            dossie.tamanhos[relativo] = (dossie.pasta / relativo).stat().st_size
        except OSError:
            # O manifesto lista, e o disco não tem. É fato de integridade,
            # e a conferência é quem o apura — aqui só não se inventa tamanho.
            dossie.ausentes_no_disco.append(relativo)

    relatorios = sorted(dossie.pasta.glob(f"{PREFIXO_CONFERENCIA}*.txt"))
    if relatorios:
        try:
            for linha in relatorios[-1].read_text(encoding="utf-8").splitlines():
                if linha.startswith("RESULTADO:"):
                    dossie.ultima_conferencia = linha.replace("RESULTADO:", "").strip()
                    break
        except OSError:
            pass


def montar_dossie(pasta_aquisicao: Path) -> Dossie:
    """Lê os registros da aquisição. Não escreve nada, em lugar nenhum."""
    pasta = Path(pasta_aquisicao)
    plataforma, momento = descrever_aquisicao(pasta.name)
    dossie = Dossie(
        pasta=pasta, caso=pasta_do_caso(pasta).name, plataforma=plataforma, momento=momento
    )

    _ler_registro(dossie)
    _ler_cadeia(dossie)
    _ler_selo(dossie)

    dossie.apuradas = ler_caracteristicas(pasta).em_pares()
    dossie.desvio_do_relogio = ler_desvio_registrado(dossie.registro_bruto)
    dossie.metodo = ler_metodo(pasta)
    dossie.desfecho = ler_desfecho(pasta)
    try:
        dossie.autorizacao = ler_autorizacao_da_aquisicao(pasta)
    except Exception:
        dossie.autorizacao = Autorizacao()

    lido = ler_operador(pasta)
    if lido is not None:
        dossie.operador, dossie.conta_da_estacao = lido
    return dossie


def tamanho_legivel(quantidade: int) -> str:
    valor = float(quantidade)
    for unidade in ("B", "KiB", "MiB", "GiB", "TiB"):
        if valor < 1024 or unidade == "TiB":
            return f"{int(valor)} B" if unidade == "B" else f"{valor:.2f} {unidade}"
        valor /= 1024
    return f"{quantidade} B"


def carimbo_legivel(iso: str) -> str:
    """`2026-08-30T19:25:43-03:00` vira `30/08/2026 19:25:43 (UTC-03:00)`."""
    try:
        momento = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    fuso = momento.strftime("%z")
    fuso = f" (UTC{fuso[:3]}:{fuso[3:]})" if fuso else ""
    return momento.strftime("%d/%m/%Y %H:%M:%S") + fuso
