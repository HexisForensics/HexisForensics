"""
Autorização de acesso aos dados: o documento que ampara a extração.

Uma extração tecnicamente impecável sem autorização é prova contaminada.
Mas o documento que autoriza — decisão judicial, termo em que o titular
consente com o exame, requisição ou contrato do serviço pericial — **não
nasce aqui e não vive aqui**: ele existe no processo ou no arquivo de quem
requisitou o exame, e é lá que autenticidade, validade e datas se apuram,
por quem responde por isso.

O papel desta ferramenta é estreito de propósito, e por isso honesto:

- guardar uma **cópia** do documento dentro do caso, para quem examina o
  material não precisar sair dele para saber o que amparava a coleta;
- calcular o **SHA-256** dessa cópia e prendê-lo ao selo da aquisição.

É só isso que ela pode afirmar: *este arquivo, com este hash, estava
anexado ao caso no momento desta aquisição*. Ela não lê o PDF, não confere
assinatura e não interpreta o que está escrito — logo não declara nada
disso. Exigir que o examinador redigitasse aqui a qualificação das pessoas,
a data da decisão ou a peça em que o consentimento consta produziria uma
segunda via de dados que já existem no documento original. Duas vias do
mesmo dado divergem — e uma divergência entre registros que deveriam ser
idênticos é pior do que a ausência do registro aqui.

Pelo mesmo motivo o dispositivo não é vinculado a pessoas neste módulo. O
que esta ferramenta apura dele por conta própria — serial, modelo, IMEI —
ela colhe do próprio dispositivo e registra na identificação da aquisição.

A autorização pertence ao **caso**: um mesmo documento costuma cobrir todos
os dispositivos do exame. Cada aquisição guarda o hash dos documentos
vigentes no dia, e é isso que demonstra qual versão exata estava à vista
na hora da coleta. Trocar o PDF depois não passa despercebido.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .hashing import calcular_sha256

PASTA_FUNDAMENTO = "fundamento"
NOME_FUNDAMENTO = "fundamento.txt"
NOME_FUNDAMENTO_DADOS = "fundamento.json"
PASTA_AUTORIZACAO = "fundamento_legal"
NOME_AUTORIZACAO = "autorizacao.txt"
NOME_AUTORIZACAO_DADOS = "autorizacao.json"

LARGURA = 70


class TipoDocumento(Enum):
    """
    Que peça é o documento anexado.

    Serve para nomeá-la no relatório, e só. A ferramenta não verifica se o
    arquivo corresponde ao tipo escolhido — quem anexa é que sabe o que
    está anexando.
    """

    # Os NOMES são os gravados nos casos já existentes e por isso não
    # mudam; o que mudou foram os rótulos.
    DECISAO_JUDICIAL = "Decisão judicial"
    TERMO_DE_DECLARACOES = "Termo de consentimento do titular"
    REQUISICAO = "Requisição ou contrato do exame"
    OUTRO = "Outro documento"


@dataclass
class DocumentoAutorizacao:
    """
    Um documento de autorização anexado ao caso.

    `sha256` é o único campo que a ferramenta produz sozinha, e o único que
    ela sustenta sem depender do que alguém digitou.
    """

    tipo: TipoDocumento
    arquivo: Path
    sha256: str = ""
    descricao: str = ""
    juntado_em: str = ""

    @property
    def rotulo(self) -> str:
        if self.descricao:
            return f"{self.tipo.value} — {self.descricao}"
        return self.tipo.value


@dataclass
class Autorizacao:
    """Todos os documentos que amparam o acesso neste caso."""

    documentos: list = field(default_factory=list)

    @property
    def vazia(self) -> bool:
        return not self.documentos

    @property
    def resumo(self) -> str:
        if self.vazia:
            return "nenhum documento de autorização anexado ao caso"
        return "; ".join(
            f"{documento.rotulo}: {Path(documento.arquivo).name}"
            for documento in self.documentos
        )


# ---------------------------------------------------------------------------
# Persistência no caso
# ---------------------------------------------------------------------------
def _copiar_documento(
    pasta_caso: Path,
    autorizacao: Autorizacao,
    tipo: TipoDocumento,
    arquivo: Path,
    descricao: str = "",
) -> DocumentoAutorizacao:
    """
    Copia o documento para dentro do caso e o acrescenta à autorização
    **em memória**, sem gravar o registro.

    A cópia é deliberada: referenciar o arquivo onde ele estava deixaria o
    caso apontando para um caminho que pode ser movido, renomeado ou
    apagado — e um ponteiro quebrado não demonstra nada.

    Gravar fica por conta de quem chama, para que anexar três documentos
    num mesmo ato produza **um** registro, e não três.

    Levanta `ValueError` se o mesmo conteúdo já estiver na autorização.
    Anexar o mesmo documento duas vezes não acrescenta prova nenhuma e
    faria o relatório sugerir duas autorizações onde há uma.
    """
    origem = Path(arquivo)
    if not origem.is_file():
        raise ValueError(f"arquivo não encontrado: {origem}")

    hash_novo = calcular_sha256(origem)
    for existente in autorizacao.documentos:
        if existente.sha256 == hash_novo:
            nome = Path(existente.arquivo).name
            raise ValueError(f"este documento já está anexado ao caso como {nome}")

    pasta = Path(pasta_caso) / PASTA_FUNDAMENTO
    pasta.mkdir(parents=True, exist_ok=True)

    destino = pasta / origem.name
    sufixo = 2
    while destino.exists():
        destino = pasta / f"{origem.stem}_{sufixo}{origem.suffix}"
        sufixo += 1
    shutil.copy2(origem, destino)

    documento = DocumentoAutorizacao(
        tipo=tipo,
        arquivo=destino,
        # Hash da cópia, não do original: é a cópia que fica no caso, e é
        # ela que a conferência vai recalcular daqui para frente.
        sha256=calcular_sha256(destino),
        descricao=descricao,
        juntado_em=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    autorizacao.documentos.append(documento)
    return documento


def anexar_documento(
    pasta_caso: Path,
    tipo: TipoDocumento,
    arquivo: Path,
    descricao: str = "",
) -> DocumentoAutorizacao:
    """Anexa um documento ao caso e grava o registro."""
    autorizacao = ler_autorizacao(pasta_caso)
    documento = _copiar_documento(pasta_caso, autorizacao, tipo, arquivo, descricao)
    gravar_autorizacao(pasta_caso, autorizacao)
    return documento


def anexar_documentos(pasta_caso: Path, escolhas) -> Autorizacao:
    """
    Anexa vários documentos ao caso num único ato, gravando um só registro.

    `escolhas` é uma sequência de `(tipo, arquivo, descrição)`. Se qualquer
    um deles for recusado, nenhum registro é gravado — mas os que já foram
    copiados permanecem em disco, e o `ValueError` sobe para quem chamou
    decidir. Vale para a interface, que exibe o motivo e deixa o examinador
    corrigir a escolha antes de a aquisição começar.
    """
    autorizacao = ler_autorizacao(pasta_caso)
    for tipo, arquivo, descricao in escolhas:
        _copiar_documento(pasta_caso, autorizacao, tipo, arquivo, descricao)
    gravar_autorizacao(pasta_caso, autorizacao)
    return autorizacao


def registros_da_autorizacao(pasta_caso: Path) -> list:
    """
    Registros da autorização deste caso, do mais antigo ao mais recente.

    O primeiro chama-se `fundamento.json`; os posteriores carregam carimbo
    de tempo no nome, de modo que a ordem alfabética é a cronológica. É o
    mesmo arranjo dos manifestos, e pelo mesmo motivo — ver
    `gravar_autorizacao`.
    """
    pasta = Path(pasta_caso) / PASTA_FUNDAMENTO
    if not pasta.is_dir():
        return []

    base = pasta / NOME_FUNDAMENTO_DADOS
    registros = [base] if base.is_file() else []
    # `fundamento.json` não casa com `fundamento_*.json`: o separador impede.
    return registros + sorted(pasta.glob("fundamento_*.json"))


def gravar_autorizacao(pasta_caso: Path, autorizacao: Autorizacao) -> Autorizacao:
    """
    Grava a autorização do caso — inclusive quando não há documento algum.

    O arquivo é escrito mesmo com a lista vazia porque ausência silenciosa
    é indistinguível de esquecimento: quem abrir o caso precisa **ler** que
    nada foi anexado, e não simplesmente não encontrar nada.

    **Um registro, uma vez escrito, nunca é reescrito.** A juntada de um
    documento novo gera um registro próprio, com carimbo de tempo, e o
    anterior permanece intacto. É a regra de todo registro formal: não se rasura
    folha, junta-se aditamento.

    A condição já foi *"depois que o caso é selado"*, e estava errada: a
    extração sela a **aquisição**, não o caso, então na primeira juntada o
    caso quase nunca tem manifesto — e o registro original era sobrescrito
    justamente no caminho mais comum. Foi o que aconteceu num caso real. Não
    depender do selo é também mais correto de fundo: o registro documenta o
    que o caso declarava num momento, e sobrescrevê-lo apaga essa história
    esteja ou não selado.

    Registro idêntico ao último não é gravado de novo: uma aquisição que
    não trouxe documento nenhum não precisa acrescentar folha ao caso.
    """
    pasta = Path(pasta_caso) / PASTA_FUNDAMENTO
    pasta.mkdir(parents=True, exist_ok=True)

    dados = json.dumps(_para_dicionario(autorizacao), ensure_ascii=False, indent=2)
    registros = registros_da_autorizacao(pasta_caso)
    if registros:
        try:
            if registros[-1].read_text(encoding="utf-8") == dados:
                return autorizacao
        except OSError:
            pass

    atualizacao = bool(registros)
    if not atualizacao:
        caminho_texto = pasta / NOME_FUNDAMENTO
        caminho_dados = pasta / NOME_FUNDAMENTO_DADOS
    else:
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_texto = pasta / f"fundamento_{carimbo}.txt"
        caminho_dados = pasta / f"fundamento_{carimbo}.json"
        sufixo = 2
        while caminho_dados.exists() or caminho_texto.exists():
            caminho_texto = pasta / f"fundamento_{carimbo}_{sufixo}.txt"
            caminho_dados = pasta / f"fundamento_{carimbo}_{sufixo}.json"
            sufixo += 1

    caminho_texto.write_text(
        "\n".join(_linhas_do_caso(autorizacao, atualizacao=atualizacao)) + "\n",
        encoding="utf-8",
    )
    caminho_dados.write_text(dados, encoding="utf-8")
    return autorizacao


def ler_autorizacao(pasta_caso: Path) -> Autorizacao:
    """
    Documentos já anexados a este caso — autorização vazia se não houver.

    Lê o registro **mais recente**: ele é sempre completo, e não um delta
    do anterior. Os antigos ficam onde estão, cobertos pelos selos de suas
    épocas, demonstrando o que o caso tinha em cada momento.
    """
    registros = registros_da_autorizacao(pasta_caso)
    if not registros:
        return Autorizacao()

    try:
        dados = json.loads(registros[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Autorizacao()
    return _do_dicionario(dados, Path(pasta_caso) / PASTA_FUNDAMENTO)


def _para_dicionario(autorizacao: Autorizacao) -> dict:
    return {
        "documentos": [
            {
                "tipo": documento.tipo.name,
                "arquivo": Path(documento.arquivo).name,
                "sha256": documento.sha256,
                "descricao": documento.descricao,
                "juntado_em": documento.juntado_em,
            }
            for documento in autorizacao.documentos
        ]
    }


def _do_dicionario(dados: dict, pasta_fundamento: Path) -> Autorizacao:
    documentos = []
    for bruto in dados.get("documentos", []):
        nome = bruto.get("arquivo")
        if not nome:
            continue
        try:
            tipo = TipoDocumento[bruto["tipo"]]
        except KeyError:
            # Tipo desconhecido não descarta o documento: o hash continua
            # valendo, e perder o registro seria pior do que exibi-lo com
            # rótulo genérico.
            tipo = TipoDocumento.OUTRO
        documentos.append(
            DocumentoAutorizacao(
                tipo=tipo,
                arquivo=pasta_fundamento / nome,
                sha256=bruto.get("sha256", ""),
                descricao=bruto.get("descricao", ""),
                juntado_em=bruto.get("juntado_em", ""),
            )
        )
    return Autorizacao(documentos=documentos)


# ---------------------------------------------------------------------------
# Registro dentro da aquisição — o que entra no selo do dia
# ---------------------------------------------------------------------------
def gravar_autorizacao_da_aquisicao(
    pasta_aquisicao: Path, autorizacao: Autorizacao
) -> Path:
    """
    Grava, dentro da aquisição, quais documentos estavam anexados e seus
    hashes.

    É o ponto de toda a mecânica: este arquivo é selado junto do material
    coletado, então fixa no tempo qual autorização estava à vista no dia. O
    PDF em si mora um nível acima, no caso, e o caso pode receber outros
    depois — mas o que valia naquele momento fica provado aqui.
    """
    pasta = Path(pasta_aquisicao) / PASTA_AUTORIZACAO
    pasta.mkdir(parents=True, exist_ok=True)

    caminho = pasta / NOME_AUTORIZACAO
    caminho.write_text(
        "\n".join(_linhas_da_aquisicao(autorizacao)) + "\n", encoding="utf-8"
    )
    # O .txt é para quem lê a pasta; o .json é para o laudo montar a seção
    # da autorização com o que estava à vista NESTE dia, e não com o estado
    # atual do caso — que pode ter recebido documentos depois.
    (pasta / NOME_AUTORIZACAO_DADOS).write_text(
        json.dumps(_para_dicionario(autorizacao), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return caminho


def ler_autorizacao_da_aquisicao(pasta_aquisicao: Path) -> Autorizacao:
    """
    O que estava anexado ao caso no momento **desta** aquisição.

    Difere de `ler_autorizacao`, que devolve o estado atual do caso. Para o
    laudo de uma aquisição vale este: documento juntado depois não estava à
    vista quando o exame foi feito, e apresentá-lo como se estivesse seria
    afirmar o que não ocorreu.
    """
    caminho = Path(pasta_aquisicao) / PASTA_AUTORIZACAO / NOME_AUTORIZACAO_DADOS
    if not caminho.is_file():
        return Autorizacao()

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Autorizacao()
    # Os arquivos moram na pasta do caso, um nível acima da aquisição.
    return _do_dicionario(dados, Path(pasta_aquisicao).parent / PASTA_FUNDAMENTO)


# ---------------------------------------------------------------------------
# Texto para quem lê o caso
# ---------------------------------------------------------------------------
def _nota_alcance(tem_documento: bool) -> list:
    """
    O que a ferramenta afirma — e o que não afirma — sobre o que registrou.

    O texto muda conforme haja ou não documento porque a versão fixa,
    falando em "os arquivos acima", descrevia uma lista inexistente quando
    nada fora anexado. Registro que menciona arquivo que não está ali é da
    mesma família do defeito que este módulo existe para evitar.
    """
    if tem_documento:
        afirmacao = [
            "  Esta ferramenta afirma unicamente que os arquivos acima, com os",
            "  hashes indicados, estavam anexados ao caso.",
        ]
    else:
        afirmacao = [
            "  Não há o que esta ferramenta afirme aqui além da própria",
            "  ausência: nenhum documento lhe foi apresentado para copiar e",
            "  hashear.",
        ]

    return (
        ["-" * LARGURA, "ALCANCE DESTE REGISTRO", ""]
        + afirmacao
        + [
            "",
            "  Ela NÃO lê o conteúdo dos documentos: não atesta autenticidade, não",
            "  confere assinatura, não valida competência e não interpreta as datas",
            "  neles constantes. O original permanece com quem o emitiu ou no",
            "  processo a que pertence — é lá que autenticidade e validade se",
            "  apuram.",
            "-" * LARGURA,
        ]
    )


def _cabecalho(titulo: str) -> list:
    return ["=" * LARGURA, titulo.center(LARGURA), "=" * LARGURA]


def _linhas_dos_documentos(autorizacao: Autorizacao, indentacao: str = "  ") -> list:
    linhas = []
    for ordem, documento in enumerate(autorizacao.documentos, start=1):
        linhas += [
            f"{indentacao}[{ordem}] {documento.rotulo}",
            f"{indentacao}    Arquivo: {Path(documento.arquivo).name}",
            f"{indentacao}    SHA-256: {documento.sha256}",
        ]
        if documento.juntado_em:
            linhas.append(f"{indentacao}    Anexado: {documento.juntado_em}")
        linhas.append("")
    return linhas


def _linhas_do_caso(autorizacao: Autorizacao, atualizacao: bool = False) -> list:
    linhas = _cabecalho("AUTORIZAÇÃO DE ACESSO AOS DADOS") + [""]

    if atualizacao:
        linhas += [
            "[REGISTRO ATUALIZADO]",
            "",
            "  Este registro substitui o anterior desta mesma pasta, que",
            "  permanece onde está e NÃO foi alterado: ele continua provando o",
            "  que o caso declarava à época. Vale sempre o registro de carimbo",
            "  mais recente.",
            "",
        ]

    if autorizacao.vazia:
        linhas += [
            "[NENHUM DOCUMENTO ANEXADO]",
            "",
            "  Até este momento não foi anexado a este caso nenhum documento",
            "  de autorização.",
            "",
            "  Isto NÃO afirma que a autorização inexista: o documento que a",
            "  formaliza existe fora desta ferramenta, e pode ser juntado a",
            "  este caso depois, como complemento. Significa apenas",
            "  que esta ferramenta não teve documento algum à vista para",
            "  copiar e hashear.",
        ]
    else:
        linhas += ["[DOCUMENTOS ANEXADOS]", ""]
        linhas += _linhas_dos_documentos(autorizacao)
        linhas += [
            "  As cópias acima ficam nesta pasta, um nível acima das aquisições.",
            "  O que as prende ao exame é o hash: cada aquisição registra, dentro",
            "  do que foi selado no dia, o hash dos documentos que estavam",
            "  anexados naquele momento. Alterar um documento aqui faz a",
            "  conferência daquela aquisição acusar a divergência.",
        ]

    return linhas + [""] + _nota_alcance(not autorizacao.vazia) + ["=" * LARGURA]


def _linhas_da_aquisicao(autorizacao: Autorizacao) -> list:
    linhas = _cabecalho("AUTORIZAÇÃO VIGENTE NO MOMENTO DESTA AQUISIÇÃO") + [""]

    if autorizacao.vazia:
        linhas += [
            "[NENHUM DOCUMENTO ANEXADO]",
            "",
            "  No momento desta aquisição não havia documento de autorização",
            "  anexado ao caso.",
            "",
            "  Documento juntado ao caso DEPOIS desta data não consta deste",
            "  registro, e não deve ser lido como se estivesse à vista aqui.",
        ]
    else:
        linhas += _linhas_dos_documentos(autorizacao)

    return linhas + [""] + _nota_alcance(not autorizacao.vazia) + ["=" * LARGURA]
