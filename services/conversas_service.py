"""
Conversas de uma aquisição: a lista delas, e o PDF só das escolhidas.

Um WhatsApp de uso real tem dezenas de milhares de mensagens. Impressas
inteiras, viravam um relatório de milhares de páginas que ninguém lê e que
esconde o que importa. A íntegra continua entregue — na planilha e no
caderno HTML do Relatório de Conteúdo, onde se busca e se filtra —, e o
PDF passa a ser feito do que o examinador ESCOLHE: as conversas relevantes
ao exame, completas, com a procedência de cada mensagem.

Escolher conversas é ato do examinador, e o documento diz isso: ele não
afirma que as demais não tenham relevância, só que não foram selecionadas.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from reportlab.platypus import PageBreak, Paragraph, Spacer

from services import identidade_pdf as identidade
from services.dossie_service import montar_dossie
from services.relatorio_extracao_service import (
    DocumentoGerado,
    destino_livre,
    fuso_da_estacao,
    pasta_de_documentos,
)
from services.relatorio_service import levantar_artefatos

# Artefatos que são conversas: mensagens trocadas com um interlocutor.
# Chamadas e agenda não entram — não têm conteúdo a ler em sequência.
PREFIXOS_DE_CONVERSA = ("whatsapp", "sms", "mms", "email")


def e_artefato_de_conversa(chave: str) -> bool:
    return any(chave == p or chave.startswith(p + "_") for p in PREFIXOS_DE_CONVERSA)


def chave_da_conversa(registro) -> str:
    """O interlocutor: a conversa (WhatsApp), o remetente (e-mail) ou o número."""
    campos = registro.campos
    return str(
        campos.get("conversa") or campos.get("de") or campos.get("numero") or "(sem identificação)"
    )


@dataclass
class Conversa:
    artefato: str  # chave do artefato (whatsapp, sms_backup, sms_agente...)
    via: str  # título do artefato, para a tela
    chave: str
    nome: str = ""
    # Telefone, quando a conversa é identificada por outra coisa: o WhatsApp
    # identifica conversas por um código interno (`...@lid`), e o número só
    # aparece resolvido em cada mensagem.
    numero: str = ""
    registros: list = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return f"{self.numero} ({self.chave})" if self.numero else self.chave

    @property
    def quantidade(self) -> int:
        return len(self.registros)

    @property
    def periodo(self) -> str:
        momentos = [r.momento for r in self.registros if r.momento]
        if not momentos:
            return ""
        return f"{min(momentos).strftime('%d/%m/%Y')} a {max(momentos).strftime('%d/%m/%Y')}"


def agrupar(artefato) -> List[Conversa]:
    """As conversas de um artefato, da mais volumosa para a menor."""
    grupos: Dict[str, Conversa] = OrderedDict()
    for registro in artefato.resultado.registros if artefato.resultado else []:
        chave = chave_da_conversa(registro)
        conversa = grupos.setdefault(
            chave, Conversa(artefato=artefato.chave, via=artefato.titulo, chave=chave)
        )
        conversa.registros.append(registro)
        numero = str(registro.campos.get("numero") or "").strip()
        if numero and not numero.startswith("(") and numero != chave and not conversa.numero:
            conversa.numero = numero
        nome = str(registro.campos.get("contato") or "").strip()
        if nome and not nome.startswith("(") and not conversa.nome:
            conversa.nome = nome
    return sorted(grupos.values(), key=lambda c: -c.quantidade)


def listar_conversas(pasta_aquisicao: Path, fuso="estacao") -> Tuple[List[Conversa], list]:
    """`(conversas, artefatos)` da aquisição. Os artefatos vêm junto para o PDF."""
    if fuso == "estacao":
        fuso = fuso_da_estacao()
    artefatos = levantar_artefatos(Path(pasta_aquisicao), fuso)
    conversas: List[Conversa] = []
    for artefato in artefatos:
        if e_artefato_de_conversa(artefato.chave) and artefato.total:
            conversas.extend(agrupar(artefato))
    return conversas, artefatos


def gerar_pdf_conversas(
    pasta_aquisicao: Path,
    selecionadas: List[Tuple[str, str]],
    fuso="estacao",
    destino: Optional[Path] = None,
) -> DocumentoGerado:
    """
    PDF com as conversas escolhidas, `(chave do artefato, chave da conversa)`,
    completas e na ordem em que aconteceram.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    if not selecionadas:
        return DocumentoGerado(erro="Nenhuma conversa foi selecionada.")
    try:
        conversas, artefatos = listar_conversas(pasta_aquisicao, fuso)
        por_chave = {(c.artefato, c.chave): c for c in conversas}
        escolhidas = [por_chave[s] for s in selecionadas if s in por_chave]
        if not escolhidas:
            return DocumentoGerado(erro="As conversas selecionadas não foram encontradas.")
        origem = {a.chave: a for a in artefatos}
        dossie = montar_dossie(pasta_aquisicao)
        nome_do_fuso = next(
            (a.resultado.fuso_declarado for a in artefatos if a.resultado is not None), "UTC"
        )

        e = identidade.estilos()
        largura = identidade.largura_util(paisagem=True)
        historia = [
            Paragraph("CONVERSAS SELECIONADAS", e["titulo"]),
            Paragraph(
                f"Caso {identidade.escapar(dossie.caso)} — aquisição "
                f"{identidade.escapar(pasta_aquisicao.name)}",
                e["subtitulo"],
            ),
            identidade.tabela_de_pares([
                ("Conversas selecionadas", f"{len(escolhidas)} de {len(conversas)}"),
                ("Mensagens neste documento", str(sum(c.quantidade for c in escolhidas))),
                ("Fuso das datas", identidade.escapar(nome_do_fuso)),
                ("Gerado em", datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S %z")),
            ], largura, proporcao=0.25),
            Spacer(1, 6),
            Paragraph(
                "As conversas abaixo foram ESCOLHIDAS pelo examinador entre as existentes na "
                "aquisição, e são reproduzidas completas, na ordem em que aconteceram. A "
                "escolha não afirma que as demais sejam irrelevantes. A íntegra de todas as "
                "conversas está na planilha e no caderno HTML do Relatório de Conteúdo, e o "
                "material original permanece na aquisição selada. Cada mensagem traz o "
                "arquivo e a linha de origem, para ser conferida contra ele.",
                e["nota"],
            ),
        ]

        for indice, conversa in enumerate(escolhidas):
            artefato = origem.get(conversa.artefato)
            if indice:
                historia.append(PageBreak())
            titulo = conversa.rotulo + (f" — {conversa.nome}" if conversa.nome else "")
            historia += [
                Paragraph(identidade.escapar(titulo), e["secao"]),
                Paragraph(
                    f"{identidade.escapar(conversa.via)} · {conversa.quantidade} mensagem(ns)"
                    + (f" · {conversa.periodo}" if conversa.periodo else "")
                    + (f" · origem: {identidade.escapar(artefato.caminho_relativo)}"
                       if artefato else ""),
                    e["esquerda"],
                ),
                Spacer(1, 4),
            ]
            ordenadas = sorted(
                conversa.registros,
                key=lambda r: (r.momento is None, r.momento or datetime.min, r.linha_de_origem),
            )
            linhas = []
            for registro in ordenadas:
                campos = registro.campos
                quem = str(campos.get("contato") or campos.get("de") or "")
                conteudo = str(campos.get("conteudo") or "")
                if campos.get("assunto"):
                    conteudo = f"[{campos['assunto']}] {conteudo}"
                if campos.get("anexo"):
                    conteudo += f" [anexo: {campos['anexo']}]"
                linhas.append([
                    identidade.escapar(registro.momento_legivel),
                    identidade.escapar(campos.get("direcao")),
                    identidade.escapar(quem if quem and not quem.startswith("(") else ""),
                    identidade.escapar(conteudo),
                    Paragraph(
                        identidade.escapar(f"linha {registro.linha_de_origem}"),
                        e["mono_pequeno"],
                    ),
                ])
            historia.append(identidade.tabela(
                ["Data e hora", "Sentido", "Remetente", "Conteúdo", "Origem"],
                linhas,
                [largura * 0.13, largura * 0.09, largura * 0.14, largura * 0.56,
                 largura * 0.08],
            ))

        caminho = destino or destino_livre(
            pasta_de_documentos(pasta_aquisicao),
            f"Conversas_selecionadas_{pasta_aquisicao.name}",
        )
        identidade.montar_documento(
            caminho, "Conversas Selecionadas", historia, rastreio=dossie.rastreio,
            selo=dossie.sha256_do_manifesto, paisagem=True, teste=dossie.de_teste,
        )
        return DocumentoGerado(caminho=caminho)
    except Exception as erro:
        return DocumentoGerado(erro=f"{type(erro).__name__}: {erro}")

