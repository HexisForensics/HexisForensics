"""
Geração do manifesto de integridade (SHA-256) para cadeia de custódia.

Refatoração do antigo `5_gerar_hashes.py`: mesma lógica de cálculo de hash,
mas sem `input()` no meio do caminho — a escolha da pasta agora é feita
pela UI, através de `services.hash_service` (ver `ui.widgets.hash_dialog.HashDialog`),
e o progresso/log são reportados via callbacks para poderem alimentar a
interface gráfica.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

NOME_MANIFESTO = "manifesto_hashes.txt"
PADRAO_MANIFESTO = "manifesto_hashes*.txt"
PREFIXO_CONFERENCIA = "conferencia_integridade"
SUFIXO_HASH_AVULSO = ".sha256"

# Índice dos complementos do caso. Os nomes moram aqui, e não em `core.case`,
# porque quem precisa saber o que NÃO entra no selo é quem sela — e uma
# segunda definição do mesmo nome já custou caro neste projeto.
PASTA_COMPLEMENTOS = "complementos"
NOME_INDICE_COMPLEMENTOS = "INDICE.txt"


class EscritorComHash:
    """
    Envolve um arquivo binário aberto para escrita e calcula o SHA-256 dos
    bytes **no mesmo momento em que eles são gravados**.

    Por que isso importa em perícia: calcular o hash depois, relendo o
    arquivo do disco, prova apenas que o arquivo não mudou *desde a
    releitura*. Hashear durante a gravação vincula o valor ao fluxo de
    bytes que realmente saiu do dispositivo — e, de quebra, evita uma
    segunda passagem de leitura sobre imagens que podem ter dezenas de GB.
    """

    def __init__(self, arquivo, algoritmo: str = "sha256"):
        self._arquivo = arquivo
        self._hash = hashlib.new(algoritmo)
        self.algoritmo = algoritmo
        self.bytes_gravados = 0

    def escrever(self, bloco: bytes) -> None:
        self._arquivo.write(bloco)
        self._hash.update(bloco)
        self.bytes_gravados += len(bloco)

    @property
    def hash_hex(self) -> str:
        return self._hash.hexdigest()


def gravar_hash_avulso(caminho_arquivo: Path, hash_hex: str, algoritmo: str = "sha256") -> Path:
    """
    Grava `<arquivo>.sha256` ao lado do arquivo, no formato reconhecido por
    `sha256sum -c` e por ferramentas periciais de terceiros:

        <hash>  *<nome_do_arquivo>

    Serve para que a integridade de uma aquisição específica possa ser
    conferida isoladamente, sem depender do manifesto consolidado da pasta.
    """
    caminho_arquivo = Path(caminho_arquivo)
    caminho_hash = caminho_arquivo.with_name(caminho_arquivo.name + f".{algoritmo}")
    caminho_hash.write_text(f"{hash_hex} *{caminho_arquivo.name}\n", encoding="utf-8")
    return caminho_hash


def calcular_sha256(caminho_arquivo: Path, tamanho_bloco: int = 65536) -> str:
    """Calcula o SHA-256 de um arquivo em blocos, sem carregá-lo inteiro em memória."""
    sha256_hash = hashlib.sha256()
    try:
        with open(caminho_arquivo, "rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(tamanho_bloco), b""):
                sha256_hash.update(bloco)
        return sha256_hash.hexdigest()
    except OSError as exc:
        return f"ERRO_LEITURA ({exc})"


def listar_pastas_extracao(raiz_extracoes: Path) -> List[Path]:
    """
    Lista os destinos possíveis de um manifesto: as pastas de caso e, dentro
    delas, cada pasta de aquisição.

    Os dois níveis são oferecidos porque servem a propósitos diferentes — o
    manifesto de uma aquisição isolada sela aquela coleta; o do caso inteiro
    sela o conjunto, útil ao encerrar o projeto.
    """
    from .case import e_pasta_de_aquisicao

    raiz_extracoes = Path(raiz_extracoes)
    if not raiz_extracoes.exists():
        return []

    pastas: List[Path] = []
    for pasta_caso in sorted(p for p in raiz_extracoes.iterdir() if p.is_dir()):
        pastas.append(pasta_caso)
        pastas.extend(
            sorted(
                sub
                for sub in pasta_caso.iterdir()
                if sub.is_dir() and e_pasta_de_aquisicao(sub.name)
            )
        )
    return pastas


def _arquivos_para_hashear(pasta_alvo: Path, excluir: Optional[Path] = None) -> List[Path]:
    """
    Arquivos que entram no manifesto desta pasta.

    Só um arquivo fica de fora por natureza: **o manifesto que está sendo
    escrito**, que não pode conter o próprio hash. Todos os demais entram,
    inclusive manifestos anteriores e o selo de cada aquisição.

    Isso forma uma **cadeia de selos**: cada manifesto novo cobre os que
    vieram antes. Quem alterasse um arquivo e regerasse o manifesto para
    encobrir a alteração deixaria o selo antigo — que ainda registra o hash
    original — dentro do selo novo, e a divergência continuaria demonstrável.

    A exceção são os relatórios de conferência, excluídos em qualquer nível:
    são gerados repetidamente por construção, e selá-los faria cada
    conferência invalidar a seguinte.

    Pelo mesmo motivo fica de fora o **índice dos complementos**: ele cresce
    a cada juntada. Selá-lo fazia com que a segunda juntada legítima num
    caso divergisse do selo original — e o caso ficava permanentemente
    inconferível justamente por ter recebido informação nova, que é o que a
    máquina de complementos existe para permitir. Nada se perde: o índice é
    uma listagem derivada, e cada complemento é um arquivo próprio, esse sim
    selado. Apagar ou alterar um complemento continua sendo detectado.

    A exclusão é do índice **deste** caso, por caminho exato, e não de todo
    arquivo chamado `INDICE.txt`: um índice vindo do aparelho é evidência e
    tem de ser selado como qualquer outro dado coletado.
    """
    indice_complementos = pasta_alvo / PASTA_COMPLEMENTOS / NOME_INDICE_COMPLEMENTOS

    arquivos = []
    for caminho in pasta_alvo.rglob("*"):
        if not caminho.is_file():
            continue
        if caminho.name.startswith(PREFIXO_CONFERENCIA):
            continue
        if caminho == indice_complementos:
            continue
        if excluir is not None and caminho == excluir:
            continue
        arquivos.append(caminho)
    return sorted(arquivos)


def listar_manifestos(pasta_alvo: Path) -> List[Path]:
    """
    Manifestos da pasta, do mais antigo ao mais recente.

    O original chama-se `manifesto_hashes.txt` e os posteriores carregam
    carimbo de tempo no nome, de modo que a ordem alfabética é a cronológica.
    """
    return sorted(Path(pasta_alvo).glob(PADRAO_MANIFESTO))


def ler_manifesto(caminho_manifesto: Path) -> dict:
    """
    Lê um manifesto e devolve `{caminho_relativo: hash}`.

    Aceita o formato `<hash> *<caminho>`, o mesmo do `sha256sum -c`,
    ignorando o cabeçalho.
    """
    hashes = {}
    texto = Path(caminho_manifesto).read_text(encoding="utf-8", errors="ignore")

    for linha in texto.splitlines():
        correspondencia = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", linha.strip())
        if correspondencia:
            hashes[correspondencia.group(2).strip()] = correspondencia.group(1).lower()
    return hashes


def localizar_manifesto(pasta_alvo: Path) -> Optional[Path]:
    """
    Selo **vigente** da pasta: o manifesto mais recente.

    É contra ele que a conferência corre, porque é ele que descreve o caso
    como está. Os anteriores não são descartados — ficam preservados e
    cobertos pelo selo seguinte, e a conferência os usa para detectar
    alteração encoberta por uma regeração de manifesto.
    """
    manifestos = listar_manifestos(pasta_alvo)
    return manifestos[-1] if manifestos else None


def gerar_manifesto(
    pasta_alvo: Path,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Path:
    """
    Varre recursivamente `pasta_alvo`, calcula o SHA-256 de cada arquivo e
    grava o manifesto na raiz da pasta. Retorna o caminho gerado.

    **Nunca sobrescreve um manifesto existente.** Se já houver um, o novo é
    gravado com carimbo de tempo no nome. A razão é direta: se um arquivo do
    caso tiver sido alterado, regravar por cima faria o manifesto passar a
    refletir o estado adulterado — e a prova da alteração seria destruída
    pelo próprio ato de "reforçar a cadeia de custódia". Para saber se algo
    mudou existe `conferir_manifesto`, e não uma nova geração.
    """
    log = log_callback or (lambda mensagem: None)
    progresso = progress_callback or (lambda percentual: None)

    pasta_alvo = Path(pasta_alvo)
    caminho_manifesto = pasta_alvo / NOME_MANIFESTO
    if caminho_manifesto.exists():
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_manifesto = pasta_alvo / f"manifesto_hashes_{carimbo}.txt"
        log(
            f"[*] Já existe um manifesto nesta pasta; o original foi PRESERVADO e o novo "
            f"será gravado como '{caminho_manifesto.name}', cobrindo também os anteriores."
        )

    arquivos = _arquivos_para_hashear(pasta_alvo, excluir=caminho_manifesto)
    total = len(arquivos)

    log(f"[*] Calculando hashes SHA-256 de {total} arquivo(s) em '{pasta_alvo.name}'... Aguarde...")

    with open(caminho_manifesto, "w", encoding="utf-8") as manifesto:
        manifesto.write("=" * 58 + "\n")
        manifesto.write("       MANIFESTO FORENSE DE HASHES (SHA-256)\n")
        manifesto.write("=" * 58 + "\n")
        manifesto.write(f"Pasta Analisada: {pasta_alvo.name}\n")
        manifesto.write(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for indice, caminho in enumerate(arquivos, 1):
            # `as_posix()` é deliberado: o manifesto usa barra normal em
            # qualquer sistema. Gravar a barra invertida do Windows tornaria
            # o arquivo incompatível com `sha256sum -c` e com ferramentas
            # periciais de terceiros — justamente quem precisa conferir.
            caminho_relativo = caminho.relative_to(pasta_alvo).as_posix()
            hash_calculado = calcular_sha256(caminho)
            manifesto.write(f"{hash_calculado} *{caminho_relativo}\n")

            if total:
                progresso(int(indice / total * 100))
            if indice % 25 == 0 or indice == total:
                log(f"  -> {indice}/{total} arquivos processados")

    log(f"[LACRE] Manifesto de hashes (SHA-256) gravado em: {caminho_manifesto}")
    return caminho_manifesto


@dataclass
class ResultadoConferencia:
    """
    Desfecho da conferência de um manifesto contra os arquivos em disco.

    As quatro categorias não são graus da mesma coisa: cada uma sustenta uma
    afirmação diferente no exame. Um arquivo ALTERADO diz que o conteúdo
    mudou desde a coleta; AUSENTE, que sumiu; ACRESCENTADO, que algo entrou
    na pasta depois do selo. Só a primeira categoria autoriza dizer que a
    evidência está preservada.
    """

    pasta: Path
    manifesto: Optional[Path] = None
    intactos: List[str] = field(default_factory=list)
    alterados: List[str] = field(default_factory=list)
    ausentes: List[str] = field(default_factory=list)
    acrescentados: List[str] = field(default_factory=list)
    ilegiveis: List[str] = field(default_factory=list)
    # Divergências em relação ao PRIMEIRO selo da pasta, quando há mais de um.
    # É o que impede alguém de alterar um arquivo e regerar o manifesto para
    # encobrir: o selo original continua registrando o hash de antes.
    alterados_desde_o_original: List[str] = field(default_factory=list)
    # Documentos de autorização (decisão judicial, termo) cujo conteúdo não
    # confere mais com o hash selado nesta aquisição. Eles moram um nível
    # acima, na pasta do caso, e por isso não entram no manifesto desta
    # pasta — mas o hash deles foi selado aqui, e é exatamente isso que
    # permite conferi-los sem re-hashear o caso inteiro.
    autorizacao_divergente: List[str] = field(default_factory=list)
    autorizacao_ausente: List[str] = field(default_factory=list)
    manifestos: List[str] = field(default_factory=list)
    erro: str = ""

    @property
    def integro(self) -> bool:
        """
        `True` somente quando nada foi alterado, perdido ou acrescentado —
        nem em relação ao selo vigente, nem em relação ao primeiro, nem
        entre os documentos que autorizaram o acesso.
        """
        return (
            not self.erro
            and self.manifesto is not None
            and not (
                self.alterados
                or self.ausentes
                or self.acrescentados
                or self.ilegiveis
                or self.alterados_desde_o_original
                or self.autorizacao_divergente
                or self.autorizacao_ausente
            )
        )

    @property
    def resumo(self) -> str:
        if self.erro:
            return f"Conferência não realizada: {self.erro}"
        if self.integro:
            return (
                f"ÍNTEGRO: {len(self.intactos)} arquivo(s) conferidos, todos idênticos ao "
                "manifesto."
            )
        partes = [
            f"{len(self.alterados)} alterado(s)",
            f"{len(self.ausentes)} ausente(s)",
            f"{len(self.acrescentados)} acrescentado(s)",
            f"{len(self.ilegiveis)} ilegível(is)",
        ]
        if self.alterados_desde_o_original:
            partes.append(
                f"{len(self.alterados_desde_o_original)} divergente(s) do SELO ORIGINAL"
            )
        if self.autorizacao_divergente:
            partes.append(
                f"{len(self.autorizacao_divergente)} documento(s) de AUTORIZAÇÃO alterado(s)"
            )
        if self.autorizacao_ausente:
            partes.append(
                f"{len(self.autorizacao_ausente)} documento(s) de AUTORIZAÇÃO ausente(s)"
            )
        return f"DIVERGÊNCIAS: {', '.join(partes)}, sobre {len(self.intactos)} íntegro(s)."


def conferir_manifesto(
    pasta_alvo: Path,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> ResultadoConferencia:
    """
    Recalcula os hashes da pasta e confronta com o manifesto existente.

    É a operação que dá sentido ao manifesto. Gerar um hash prova pouco: o
    que sustenta a cadeia de custódia é poder demonstrar, depois, que o
    material não mudou entre a coleta e o exame. Sem esta conferência, o
    manifesto era uma afirmação que ninguém jamais testava.

    O relatório é gravado na própria pasta, com carimbo de tempo, e nunca
    substitui um anterior: o histórico de conferências é parte do registro.
    """
    log = log_callback or (lambda mensagem: None)
    progresso = progress_callback or (lambda percentual: None)

    pasta_alvo = Path(pasta_alvo)
    resultado = ResultadoConferencia(pasta=pasta_alvo)

    caminho_manifesto = localizar_manifesto(pasta_alvo)
    if caminho_manifesto is None:
        resultado.erro = "não há manifesto nesta pasta para conferir"
        log(f"[ERRO] {resultado.erro}.")
        return resultado

    resultado.manifesto = caminho_manifesto
    resultado.manifestos = [c.name for c in listar_manifestos(pasta_alvo)]
    esperados = ler_manifesto(caminho_manifesto)
    if not esperados:
        resultado.erro = f"o manifesto '{caminho_manifesto.name}' não contém nenhum hash legível"
        log(f"[ERRO] {resultado.erro}.")
        return resultado

    log(f"[*] Conferindo {len(esperados)} arquivo(s) contra '{caminho_manifesto.name}'...")

    # O manifesto contra o qual se confere nao consta de si mesmo; incluir
    # o proprio selo na varredura o faria aparecer como "acrescentado".
    presentes = {
        caminho.relative_to(pasta_alvo).as_posix(): caminho
        for caminho in _arquivos_para_hashear(pasta_alvo, excluir=caminho_manifesto)
    }

    total = len(esperados)
    for indice, (relativo, hash_esperado) in enumerate(sorted(esperados.items()), 1):
        chave = relativo.replace("\\", "/")
        caminho = presentes.get(chave)

        if caminho is None:
            resultado.ausentes.append(chave)
        else:
            calculado = calcular_sha256(caminho)
            if calculado.startswith("ERRO_LEITURA"):
                resultado.ilegiveis.append(chave)
            elif calculado.lower() == hash_esperado:
                resultado.intactos.append(chave)
            else:
                resultado.alterados.append(chave)

        if total:
            progresso(int(indice / total * 100))

    esperados_normalizados = {r.replace("\\", "/") for r in esperados}
    resultado.acrescentados = sorted(set(presentes) - esperados_normalizados)
    resultado.alterados_desde_o_original = _confrontar_selo_original(
        pasta_alvo, presentes, caminho_manifesto
    )
    _conferir_documentos_de_autorizacao(pasta_alvo, resultado)

    _gravar_relatorio_conferencia(resultado)
    log(f"[CONCLUÍDO] {resultado.resumo}")
    return resultado


def _conferir_documentos_de_autorizacao(
    pasta_alvo: Path, resultado: ResultadoConferencia
) -> None:
    """
    Confere os documentos que autorizaram o acesso, que moram um nível acima.

    A decisão judicial e o termo pertencem ao **caso**, porque uma
    autorização cobre vários aparelhos. Ficam, portanto, fora do manifesto
    da aquisição — e o manifesto do caso não é gerado automaticamente,
    porque re-hashear todas as aquisições a cada nova coleta dobraria o
    tempo de uma extração física.

    Sem esta conferência, alterar o PDF da decisão depois da coleta não
    seria detectado por operação nenhuma: conferir a aquisição passaria,
    já que o documento não está nela. O que fecha a lacuna é o hash que a
    aquisição selou no dia — basta recalcular o hash dos documentos, e só
    deles. Custo desprezível, e a afirmação do registro passa a ser
    verdadeira.

    Documento ausente é reportado à parte de documento alterado: sumir e
    mudar sustentam afirmações diferentes no exame.
    """
    # Importação adiada: `core.fundamento` depende deste módulo para calcular
    # hashes. A dependência é mesmo mútua — quem grava precisa hashear, quem
    # confere precisa saber o que foi gravado — e resolvê-la aqui evita
    # espalhar os nomes dos arquivos do fundamento por dois módulos.
    from .fundamento import PASTA_FUNDAMENTO, ler_autorizacao_da_aquisicao

    autorizacao = ler_autorizacao_da_aquisicao(pasta_alvo)
    if autorizacao.vazia:
        return

    pasta_documentos = Path(pasta_alvo).parent / PASTA_FUNDAMENTO
    for documento in autorizacao.documentos:
        if not documento.sha256:
            continue
        caminho = pasta_documentos / Path(documento.arquivo).name
        if not caminho.is_file():
            resultado.autorizacao_ausente.append(caminho.name)
            continue

        calculado = calcular_sha256(caminho)
        if calculado.startswith("ERRO_LEITURA"):
            # Ilegível entra como ausente, e não como alterado: não se pode
            # afirmar que o conteúdo mudou quando não foi possível lê-lo.
            resultado.autorizacao_ausente.append(caminho.name)
        elif calculado.lower() != documento.sha256.lower():
            resultado.autorizacao_divergente.append(caminho.name)


def _confrontar_selo_original(
    pasta_alvo: Path, presentes: dict, manifesto_vigente: Path
) -> List[str]:
    """
    Confere os arquivos também contra o PRIMEIRO selo da pasta.

    Sem isso, bastaria alterar um arquivo e clicar em "Gerar Manifesto" para
    a conferência voltar a dizer ÍNTEGRO — o selo novo descreveria o estado
    adulterado. O selo original continua registrando o hash de antes, e é
    ele que denuncia a alteração.

    Arquivos legitimamente juntados depois (complementos) não constam do
    selo original e, por isso, não aparecem aqui.
    """
    manifestos = listar_manifestos(pasta_alvo)
    if len(manifestos) < 2 or manifestos[0] == manifesto_vigente:
        return []

    originais = ler_manifesto(manifestos[0])
    divergentes = []
    for relativo, hash_original in originais.items():
        chave = relativo.replace("\\", "/")
        caminho = presentes.get(chave)
        if caminho is None:
            continue
        if calcular_sha256(caminho).lower() != hash_original:
            divergentes.append(chave)
    return sorted(divergentes)


def _gravar_relatorio_conferencia(resultado: ResultadoConferencia) -> Optional[Path]:
    """Grava o relatório da conferência na pasta, sem apagar conferências anteriores."""
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = resultado.pasta / f"{PREFIXO_CONFERENCIA}_{carimbo}.txt"

    # O historico de conferencias e parte do registro: nenhuma pode apagar
    # outra, nem mesmo quando duas ocorrem no mesmo segundo.
    sufixo = 2
    while caminho.exists():
        caminho = resultado.pasta / f"{PREFIXO_CONFERENCIA}_{carimbo}_{sufixo}.txt"
        sufixo += 1

    linhas = [
        "=" * 70,
        "CONFERÊNCIA DE INTEGRIDADE (SHA-256)".center(70),
        "=" * 70,
        f"Pasta conferida: {resultado.pasta.name}",
        f"Selo vigente:    {resultado.manifesto.name if resultado.manifesto else '(nenhum)'}",
        f"Selos da pasta:  {', '.join(resultado.manifestos) or '(nenhum)'}",
        f"Data/Hora:       {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"RESULTADO: {resultado.resumo}",
        "=" * 70,
    ]

    for titulo, itens, nota in (
        ("ARQUIVOS ALTERADOS DESDE A COLETA", resultado.alterados,
         "O conteúdo destes arquivos MUDOU após o manifesto ter sido gerado."),
        ("ARQUIVOS AUSENTES", resultado.ausentes,
         "Constavam do manifesto e não foram encontrados na pasta."),
        ("ARQUIVOS ACRESCENTADOS APÓS O MANIFESTO", resultado.acrescentados,
         "Estão na pasta e não constavam do manifesto."),
        ("ARQUIVOS ILEGÍVEIS", resultado.ilegiveis,
         "Não foi possível ler o conteúdo para conferir."),
        ("ARQUIVOS QUE DIVERGEM DO SELO ORIGINAL", resultado.alterados_desde_o_original,
         "Conferem com o manifesto mais recente, porém NÃO com o primeiro selo "
         "da pasta. Isso ocorre quando um arquivo é alterado e o manifesto é "
         "regerado em seguida."),
        ("DOCUMENTOS DE AUTORIZAÇÃO ALTERADOS", resultado.autorizacao_divergente,
         "A decisão judicial ou o termo que amparou esta aquisição está na pasta "
         "do caso com conteúdo DIFERENTE do que foi selado aqui no dia da coleta. "
         "O documento examinado não é mais o mesmo."),
        ("DOCUMENTOS DE AUTORIZAÇÃO AUSENTES OU ILEGÍVEIS", resultado.autorizacao_ausente,
         "Constavam do registro desta aquisição e não foi possível encontrá-los "
         "ou lê-los na pasta do caso."),
    ):
        if itens:
            linhas += ["", titulo, "-" * len(titulo), nota, ""]
            linhas += [f"  - {nome}" for nome in itens]

    linhas += [
        "",
        "=" * 70,
        f"Arquivos íntegros: {len(resultado.intactos)}",
        "=" * 70,
    ]

    try:
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return caminho
    except OSError:
        return None
