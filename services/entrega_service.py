"""
Entrega de material: copiar documentos e arquivos para fora da suíte
(pendrive, pasta de rede) como ato documentado da cadeia de custódia.

Cada entrega:

- vai para uma pasta própria no destino (`Entrega_<caso>_<aquisição>_<data>`),
  preservando o caminho de cada arquivo dentro da aquisição;
- tem cada cópia conferida pelo SHA-256 DEPOIS de gravada — cópia que não
  confere é falha dita, nunca "entregue";
- leva um recibo (PDF e texto) com a lista, os tamanhos, os hashes e, para
  o material adquirido, se o hash confere com o lacre;
- vira complemento do caso: o que saiu, por quem, quando e para onde.

Nada é gravado dentro da aquisição.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from reportlab.platypus import Paragraph, Spacer

from core.case import juntar_complemento, pasta_do_caso, sanitizar_nome
from core.hashing import calcular_sha256, gerar_manifesto, ler_manifesto, localizar_manifesto
from services import identidade_pdf as identidade
from services.dossie_service import montar_dossie

NOME_RECIBO = "Recibo_de_Entrega"


@dataclass
class ItemEntregue:
    nome: str            # caminho dentro da entrega
    tamanho: int
    sha256: str
    origem: str          # "material" (da aquisição) ou "documento"
    no_lacre: str = ""   # para material: o hash selado

    @property
    def situacao(self) -> str:
        if self.origem == "documento":
            return "documento gerado pela suíte"
        if not self.no_lacre:
            return "não consta do lacre"
        return "confere com o lacre" if self.no_lacre == self.sha256 else "DIVERGE do lacre"


@dataclass
class ResultadoEntrega:
    pasta: Optional[Path] = None
    itens: List[ItemEntregue] = field(default_factory=list)
    falhas: List[str] = field(default_factory=list)
    recibo_pdf: Optional[Path] = None
    erro: str = ""


def _expandir(pasta_aquisicao: Path, relativos: List[str]) -> List[str]:
    """Pastas viram a lista dos arquivos dentro delas."""
    arquivos = []
    for relativo in relativos:
        caminho = pasta_aquisicao / relativo
        if caminho.is_dir():
            arquivos += sorted(p.relative_to(pasta_aquisicao).as_posix()
                               for p in caminho.rglob("*") if p.is_file())
        elif caminho.is_file():
            arquivos.append(relativo)
    return list(dict.fromkeys(arquivos))


def exportar(
    pasta_aquisicao: Path,
    destino: Path,
    material: List[str] = (),
    documentos: List[Path] = (),
    examinador: str = "",
    finalidade: str = "",
    teste: bool = False,
) -> ResultadoEntrega:
    """
    Copia `material` (caminhos relativos à aquisição; pastas valem por todo
    o conteúdo) e `documentos` (PDFs gerados) para `destino`, confere cada
    cópia e emite o recibo.
    """
    pasta_aquisicao = Path(pasta_aquisicao).resolve()
    resultado = ResultadoEntrega()
    arquivos = _expandir(pasta_aquisicao, list(material))
    if not arquivos and not documentos:
        resultado.erro = "Nada foi escolhido para exportar."
        return resultado
    destino = Path(destino).resolve()
    if destino == pasta_aquisicao or pasta_aquisicao in destino.parents:
        resultado.erro = "O destino não pode ficar dentro da aquisição lacrada."
        return resultado

    caso = pasta_do_caso(pasta_aquisicao)
    momento = datetime.now().astimezone()
    base = sanitizar_nome(f"Entrega_{caso.name}_{pasta_aquisicao.name}_{momento:%Y%m%d_%H%M%S}")
    pasta, sufixo = destino / base, 2
    # Duas entregas no mesmo segundo não podem se sobrescrever.
    while pasta.exists():
        pasta, sufixo = destino / f"{base}_{sufixo}", sufixo + 1
    manifesto = localizar_manifesto(pasta_aquisicao)
    try:
        lacre = ler_manifesto(manifesto) if manifesto else {}
    except OSError:
        lacre = {}

    pares: List[Tuple[Path, str, str]] = [
        (pasta_aquisicao / rel, f"material/{rel}", "material") for rel in arquivos
    ] + [(Path(doc), f"documentos/{Path(doc).name}", "documento") for doc in documentos]

    for origem, nome, tipo in pares:
        alvo = pasta / nome
        try:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, alvo)
            original, copia = calcular_sha256(origem), calcular_sha256(alvo)
        except OSError as erro:
            resultado.falhas.append(f"{nome}: não copiado ({erro})")
            continue
        if original != copia:
            resultado.falhas.append(f"{nome}: a cópia NÃO é idêntica ao original")
            continue
        relativo = nome.split("/", 1)[1] if tipo == "material" else ""
        resultado.itens.append(ItemEntregue(nome, alvo.stat().st_size, copia, tipo,
                                            lacre.get(relativo, "") if relativo else ""))
    resultado.pasta = pasta
    if not resultado.itens:
        resultado.erro = "Nenhum arquivo foi entregue.\n" + "\n".join(resultado.falhas)
        return resultado

    texto = _recibo_em_texto(caso.name, pasta_aquisicao.name, momento, pasta, examinador,
                             finalidade, resultado, teste)
    (pasta / f"{NOME_RECIBO}.txt").write_text(texto, encoding="utf-8")
    try:
        resultado.recibo_pdf = _recibo_em_pdf(pasta_aquisicao, momento, pasta, examinador,
                                              finalidade, resultado, teste)
    except Exception as erro:  # o recibo em texto já existe
        resultado.falhas.append(f"recibo em PDF não gerado ({erro}); o recibo em texto existe")

    if caso != pasta_aquisicao:
        try:
            juntar_complemento(caso, f"Entrega de material - {pasta_aquisicao.name}", texto)
            gerar_manifesto(caso)
        except OSError as erro:
            resultado.falhas.append(f"a entrega NÃO pôde ser registrada no caso ({erro})")
    return resultado


def _recibo_em_texto(caso, aquisicao, momento, pasta, examinador, finalidade, resultado,
                     teste) -> str:
    linhas = [
        "RECIBO DE ENTREGA DE MATERIAL" + ("  —  TESTE, SEM VALOR PERICIAL" if teste else ""),
        "",
        f"Caso:        {caso}",
        f"Aquisição:   {aquisicao}",
        f"Entregue em: {momento.isoformat(timespec='seconds')}",
        f"Por:         {examinador or 'não informado'}",
        f"Destino:     {pasta}",
        f"Finalidade / destinatário: {finalidade or 'não informado'}",
        "",
        "Cada cópia foi conferida pelo SHA-256 depois de gravada e é idêntica ao original.",
        "",
        f"{len(resultado.itens)} arquivo(s) entregue(s):",
    ]
    for item in resultado.itens:
        linhas.append(f"  {item.sha256}  {item.tamanho:>12} bytes  {item.nome}  [{item.situacao}]")
    if resultado.falhas:
        linhas += ["", "NÃO entregues:"] + [f"  {f}" for f in resultado.falhas]
    return "\n".join(linhas) + "\n"


def _recibo_em_pdf(pasta_aquisicao, momento, pasta, examinador, finalidade, resultado,
                   teste) -> Path:
    dossie = montar_dossie(pasta_aquisicao)
    e = identidade.estilos()
    largura = identidade.largura_util(paisagem=True)
    historia = [
        Paragraph("RECIBO DE ENTREGA DE MATERIAL", e["titulo"]),
        Paragraph(f"Caso {identidade.escapar(dossie.caso)} — aquisição "
                  f"{identidade.escapar(pasta_aquisicao.name)}", e["subtitulo"]),
        identidade.tabela_de_pares([
            ("Entregue em", momento.strftime("%d/%m/%Y %H:%M:%S %z")),
            ("Por", identidade.escapar(examinador or "não informado")),
            ("Finalidade / destinatário", identidade.escapar(finalidade or "não informado")),
            ("Destino", identidade.escapar(str(pasta))),
            ("Arquivos entregues", str(len(resultado.itens))),
        ], largura, proporcao=0.22),
        Spacer(1, 6),
        Paragraph("Cada cópia foi conferida pelo SHA-256 depois de gravada e é idêntica ao "
                  "original. Para o material adquirido, a última coluna diz se o hash confere "
                  "com o lacre da aquisição.", e["nota"]),
        Spacer(1, 6),
    ]
    linhas = [[identidade.escapar(i.nome), f"{i.tamanho:,}".replace(",", "."),
               Paragraph(i.sha256, e["mono_pequeno"]), identidade.escapar(i.situacao)]
              for i in resultado.itens]
    historia.append(identidade.tabela(
        ["Arquivo", "Bytes", "SHA-256", "Situação"], linhas,
        [largura * 0.38, largura * 0.09, largura * 0.35, largura * 0.18]))
    if resultado.falhas:
        historia += [Spacer(1, 6), Paragraph("NÃO entregues", e["subsecao"])]
        historia += [Paragraph(identidade.escapar(f), e["alerta"]) for f in resultado.falhas]
    historia += [Spacer(1, 40),
                 Paragraph("_______________________________ &nbsp;&nbsp;&nbsp;&nbsp; "
                           "_______________________________", e["assinatura"]),
                 Paragraph("Entregue por &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                           "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                           "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                           "Recebido por", e["assinatura"])]
    caminho = pasta / f"{NOME_RECIBO}.pdf"
    identidade.montar_documento(
        caminho, "Recibo de Entrega", historia, rastreio=dossie.rastreio,
        selo=dossie.sha256_do_manifesto, paisagem=True, teste=teste or dossie.de_teste,
    )
    return caminho
