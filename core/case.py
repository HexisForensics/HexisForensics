"""
Gestão de casos: as pastas, o registro do caso e a cadeia de custódia de
cada dispositivo.

Um **caso** é um projeto: reúne várias aquisições, inclusive de
dispositivos diferentes (dois telefones e um disco do mesmo exame, ou o
mesmo aparelho coletado duas vezes). Por isso a estrutura tem dois níveis:

    extracoes/
      └── CASO_001/                    <- o caso (projeto)
          ├── caso.json                <- o registro do caso, UM só
          ├── android_20260822_152249/ <- uma aquisição (um dispositivo)
          └── android_20260823_094010/ <- outra aquisição, do mesmo caso

O que descreve o CASO (referência, descrição, solicitante) mora em
`caso.json`, no nível do caso. O que descreve o DISPOSITIVO (equipamento,
estado, lacre) mora em `cadeia_custodia.txt`, dentro da aquisição. Quando
os dados do caso eram gravados dentro de cada aquisição, a segunda
aquisição gravava "N/A" em vez de herdar, e duas aquisições do mesmo caso
discordavam sobre o próprio caso.

Cada aquisição é uma pasta própria, com timestamp, e **nunca é
reaproveitada**. Isso não é organização estética: duas coletas gravadas na
mesma pasta sobrescrevem arquivos, misturam evidência de origens
possivelmente distintas e produzem um manifesto de hashes que cobre a
mistura sem que nada indique que houve duas aquisições.

O identificador do dispositivo (serial ADB, UDID, etc.) não entra no nome
da pasta — para não competir com o identificador do caso — mas é
registrado dentro dela, em `informacoes_caso.txt`, reforçando a cadeia de
custódia.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

# Os nomes do indice de complementos moram em `core.hashing`, onde vale a
# regra de selagem que os torna especiais: o indice cresce a cada juntada e
# por isso nao entra em manifesto nenhum. Uma unica definicao -- duas ja
# causaram defeito neste projeto.
from .hashing import NOME_INDICE_COMPLEMENTOS, PASTA_COMPLEMENTOS

PREFIXO_PADRAO = "CASO"

NOME_ARQUIVO_CASO = "caso.json"
NOME_CADEIA_CUSTODIA = "cadeia_custodia.txt"
PASTA_FOTOS = "evidencias_fotos"

# (chave em `caso.json`, rótulo no registro). Nenhum é obrigatório: o que
# identifica o caso é o identificador, e o que identifica a peça é o lacre.
CAMPOS_DO_CASO = (
    ("referencia", "Referência"),
    ("descricao", "Descrição"),
    ("solicitante", "Solicitante"),
)

# (chave do formulário, rótulo no registro) do dispositivo examinado.
CAMPOS_DO_DISPOSITIVO = (
    ("marca_modelo", "Equipamento"),
    ("cor", "Cor"),
    ("estado", "Estado"),
    ("lacre", "Lacre"),
)

NAO_INFORMADO = "não informado"

# Material DECIFRADO a partir da aquisição (hoje, o backup do WhatsApp). É
# derivado, produzido depois do selo, e por isso mora no nível do caso.
PASTA_DECIFRADOS = "decifrados"


def sanitizar_nome(nome: str) -> str:
    """Remove caracteres inválidos para nomes de pasta, preservando legibilidade."""
    nome_limpo = re.sub(r"[^A-Za-z0-9_\-]+", "_", nome or "").strip("_")
    return nome_limpo or "SEM_IDENTIFICACAO"


def sugerir_proximo_identificador(raiz_extracoes: Path, prefixo: str = PREFIXO_PADRAO) -> str:
    """
    Sugere o próximo identificador de caso sequencial (ex.: `CASO_003`),
    com base no maior número já usado nas pastas de extração existentes em
    `raiz_extracoes` (independente da plataforma, já que o número de caso
    é uma sequência única do laboratório/perito).
    """
    raiz_extracoes = Path(raiz_extracoes)
    maior_numero = 0

    if raiz_extracoes.exists():
        # O número precisa vir logo após o prefixo, e a pasta pode terminar
        # aí (`CASO_001`) ou continuar (`CASO_001_algo`). Um padrão frouxo
        # como `\d+` em qualquer posição capturaria a data de uma pasta
        # chamada "teste_dia_220826" e sugeriria CASO_220827.
        padrao = re.compile(rf"^{re.escape(prefixo)}_(\d+)(?:_|$)", re.IGNORECASE)
        for pasta in raiz_extracoes.iterdir():
            if not pasta.is_dir():
                continue
            correspondencia = padrao.match(pasta.name)
            if correspondencia:
                maior_numero = max(maior_numero, int(correspondencia.group(1)))

    return f"{prefixo}_{maior_numero + 1:03d}"


def criar_pasta_aquisicao(
    raiz_extracoes: Path,
    identificador_caso: str,
    plataforma: str,
    timestamp: Optional[datetime] = None,
) -> Path:
    """
    Cria a pasta de uma aquisição dentro da pasta do caso, no padrão
    `<caso>/<plataforma>_<AAAAMMDD_HHMMSS>`, e devolve seu caminho.

    A pasta do caso é reaproveitada (um caso reúne várias aquisições); a
    pasta da aquisição, jamais. No improvável choque de segundo, um sufixo
    numérico garante que duas coletas nunca compartilhem destino.
    """
    timestamp = timestamp or datetime.now()
    pasta_caso = Path(raiz_extracoes) / sanitizar_nome(identificador_caso)

    base = f"{sanitizar_nome(plataforma).lower()}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
    pasta_aquisicao = pasta_caso / base

    sufixo = 2
    while pasta_aquisicao.exists():
        pasta_aquisicao = pasta_caso / f"{base}_{sufixo}"
        sufixo += 1

    pasta_aquisicao.mkdir(parents=True)
    return pasta_aquisicao


def descrever_aquisicao(nome: str) -> Tuple[str, Optional[datetime]]:
    """
    Separa o nome de uma pasta de aquisição em plataforma e momento.

    `android_20260822_183237` vira `("Android", datetime(2026, 8, 22, 18, 32, 37))`.
    Devolve `("", None)` quando o nome não segue o padrão.
    """
    correspondencia = re.match(r"^([a-z]+)_(\d{8})_(\d{6})(?:_\d+)?$", nome, re.IGNORECASE)
    if not correspondencia:
        return "", None

    plataforma = correspondencia.group(1)
    rotulo = {"android": "Android", "ios": "iOS", "computador": "Computador"}.get(
        plataforma.lower(), plataforma.capitalize()
    )

    try:
        momento = datetime.strptime(
            correspondencia.group(2) + correspondencia.group(3), "%Y%m%d%H%M%S"
        )
    except ValueError:
        momento = None
    return rotulo, momento


def e_pasta_de_aquisicao(nome: str) -> bool:
    """`True` se o nome segue o padrão de uma pasta de aquisição."""
    return bool(re.match(r"^[a-z]+_\d{8}_\d{6}(_\d+)?$", nome, re.IGNORECASE))


def pasta_do_caso(pasta: Path) -> Path:
    """
    Sobe de uma pasta de aquisição até a pasta do caso.

    Mesma razão de `raiz_das_extracoes`: a distância é consequência da
    estrutura documentada no topo, e contar `parent` no ponto de uso já
    produziu defeito neste projeto. Recebendo a pasta de um caso, devolve
    ela mesma — quem chama nem sempre sabe qual das duas tem em mãos.
    """
    pasta = Path(pasta).resolve()
    return pasta.parent if e_pasta_de_aquisicao(pasta.name) else pasta


def pasta_dos_decifrados(pasta_aquisicao: Path) -> Path:
    """
    Onde fica o que foi decifrado desta aquisição:
    `<caso>/decifrados/<aquisição>/`. Fora da pasta selada, sempre — mesmo
    quando a pasta não segue o padrão de nome e `pasta_do_caso` devolveria
    ela mesma.
    """
    pasta_aquisicao = Path(pasta_aquisicao).resolve()
    caso = pasta_do_caso(pasta_aquisicao)
    if caso == pasta_aquisicao:
        return pasta_aquisicao.parent / f"{pasta_aquisicao.name}_{PASTA_DECIFRADOS}"
    return caso / PASTA_DECIFRADOS / pasta_aquisicao.name


def raiz_das_extracoes(pasta: Path) -> Path:
    """
    Sobe de uma pasta de aquisição até a raiz que guarda **todos** os casos.

    Existe aqui, e não em quem chama, porque a distância entre os dois é
    consequência direta da estrutura documentada no topo deste módulo
    (`<raiz>/<caso>/<plataforma>_<AAAAMMDD_HHMMSS>`), e esta é a única
    fonte dessa nomenclatura. Contar níveis de `parent` no ponto de uso já
    custou caro neste projeto: quem chama costuma pensar que recebeu a
    pasta do caso, quando o que os extratores recebem é a da aquisição —
    um nível abaixo. O erro é silencioso, porque `.parent` devolve uma
    pasta que existe e parece plausível.

    Aceita as duas formas para não depender dessa suposição: dada uma
    pasta de aquisição, sobe dois níveis; dada a pasta de um caso, sobe
    um. O reconhecimento usa `e_pasta_de_aquisicao`, não a contagem.
    """
    pasta = Path(pasta).resolve()
    if e_pasta_de_aquisicao(pasta.name):
        return pasta.parent.parent
    return pasta.parent


def registrar_info_caso(
    pasta_caso: Path,
    identificador_caso: str,
    plataforma: str,
    id_dispositivo: str,
    timestamp: Optional[datetime] = None,
) -> Path:
    """
    Grava `informacoes_caso.txt` na raiz da pasta do caso, documentando o
    identificador do caso, a plataforma e o identificador do dispositivo
    (que não aparece no nome da pasta). Reforça a cadeia de custódia.
    """
    timestamp = timestamp or datetime.now()
    caminho_arquivo = Path(pasta_caso) / "informacoes_caso.txt"

    conteudo = (
        "=" * 58 + "\n"
        "                 INFORMAÇÕES DO CASO\n"
        + "=" * 58 + "\n"
        f"Identificador do Caso:        {identificador_caso}\n"
        f"Plataforma:                   {plataforma}\n"
        f"Identificador do Dispositivo: {id_dispositivo}\n"
        f"Data/Hora de Abertura:        {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        + "=" * 58 + "\n"
    )
    caminho_arquivo.write_text(conteudo, encoding="utf-8")
    return caminho_arquivo




# ---------------------------------------------------------------------------
# Registro do caso e cadeia de custódia do dispositivo
# ---------------------------------------------------------------------------
def ler_caso(pasta_caso: Path) -> Dict[str, str]:
    """
    Dados do caso gravados em `caso.json`, pelas chaves de `CAMPOS_DO_CASO`.

    Devolve vazio quando o caso não tem o registro — o que acontece em todo
    caso aberto antes de ele existir. Vazio não é "em branco": quem chama
    distingue os dois por `tem_registro_do_caso`.
    """
    try:
        dados = json.loads((Path(pasta_caso) / NOME_ARQUIVO_CASO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {chave: str(dados.get(chave, "") or "") for chave, _ in CAMPOS_DO_CASO}


def tem_registro_do_caso(pasta_caso: Path) -> bool:
    return (Path(pasta_caso) / NOME_ARQUIVO_CASO).is_file()


def gravar_caso(pasta_caso: Path, dados: Dict[str, str]) -> Path:
    """
    Grava o registro do caso. `aberto_em` é preservado entre regravações:
    retificar a descrição não muda o dia em que o caso foi aberto.
    """
    pasta_caso = Path(pasta_caso)
    pasta_caso.mkdir(parents=True, exist_ok=True)
    caminho = pasta_caso / NOME_ARQUIVO_CASO

    agora = datetime.now().astimezone().isoformat(timespec="seconds")
    aberto_em = agora
    if caminho.is_file():
        try:
            aberto_em = json.loads(caminho.read_text(encoding="utf-8")).get("aberto_em") or agora
        except (OSError, ValueError):
            pass

    registro = {"identificador": pasta_caso.name, "aberto_em": aberto_em, "atualizado_em": agora}
    for chave, _ in CAMPOS_DO_CASO:
        registro[chave] = str(dados.get(chave, "") or "").strip()
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


def montar_cadeia_custodia(
    identificador_caso: str,
    dados_caso: Dict[str, str],
    dispositivo: Dict[str, str],
    fotos: Optional[list] = None,
    titulo: str = "CADEIA DE CUSTÓDIA",
) -> str:
    """
    Texto do `cadeia_custodia.txt` de uma aquisição — a única montagem dele.

    Traz os dados do caso COMO ESTAVAM no momento da aquisição (copiados de
    `caso.json`) e os do dispositivo. Campo em branco sai como "não
    informado": o registro diz que ninguém preencheu, em vez de calar.
    """
    def valor(dados, chave):
        return str(dados.get(chave, "") or "").strip() or NAO_INFORMADO

    linhas = [f"=== {titulo} ===", f"Caso: {identificador_caso}"]
    linhas += [f"{rotulo}: {valor(dados_caso, chave)}" for chave, rotulo in CAMPOS_DO_CASO]
    linhas.append("")
    linhas += [f"{rotulo}: {valor(dispositivo, chave)}" for chave, rotulo in CAMPOS_DO_DISPOSITIVO]
    linhas.append(f"Fotos Anexas: {', '.join(str(f) for f in fotos or []) or 'nenhuma'}")
    return "\n".join(linhas) + "\n"


def substituir_campos_da_cadeia(texto: str, novos: Dict[str, str], titulo: str) -> str:
    """
    Reescreve, num `cadeia_custodia.txt` já existente, só os rótulos dados
    em `novos` — as demais linhas saem como estavam, inclusive as de
    registros antigos, cujos campos não são mais os de hoje.
    """
    linhas = []
    for linha in texto.splitlines():
        if linha.startswith("==="):
            linhas.append(f"=== {titulo} ===")
            continue
        rotulo = linha.split(":", 1)[0].strip() if ":" in linha else ""
        if rotulo in novos:
            linhas.append(f"{rotulo}: {str(novos[rotulo]).strip() or NAO_INFORMADO}")
        else:
            linhas.append(linha)
    return "\n".join(linhas) + "\n"


def juntar_complemento(pasta_caso: Path, titulo: str, texto: str) -> Path:
    """
    Junta um complemento ao caso, sem tocar em nenhuma aquisição.

    Por que existe: a aquisição é selada no dia da coleta e não pode ser
    reescrita depois — reescrevê-la faria o caso divergir do próprio
    manifesto, e destruiria a prova de o que existia no momento do exame.
    Mas informação legítima chega depois: a referência do processo só é
    conhecida mais tarde, a autorização pode ser digitalizada dias depois,
    o titular de um aparelho pode ser identificado a partir do próprio
    exame.

    É a regra de todo registro formal: não se rasura folha, junta-se
    aditamento.
    Correção de dado errado também entra como complemento — uma retificação
    preserva o original e registra o que mudou, em vez de apagá-lo.
    """
    pasta = Path(pasta_caso) / PASTA_COMPLEMENTOS
    pasta.mkdir(parents=True, exist_ok=True)

    carimbo = datetime.now()
    base = f"{carimbo.strftime('%Y%m%d_%H%M%S')}_{sanitizar_nome(titulo).lower()[:40]}"
    caminho = pasta / f"{base}.txt"

    sufixo = 2
    while caminho.exists():
        caminho = pasta / f"{base}_{sufixo}.txt"
        sufixo += 1

    conteudo = [
        "=" * 70,
        "COMPLEMENTO AO CASO".center(70),
        "=" * 70,
        f"Assunto:   {titulo}",
        f"Juntado em: {carimbo.astimezone().isoformat(timespec='seconds')}",
        "=" * 70,
        "",
        texto,
        "",
        "=" * 70,
        "Este complemento NÃO altera as aquisições já seladas. O material",
        "coletado permanece exatamente como estava no momento do exame.",
        "=" * 70,
    ]
    caminho.write_text("\n".join(conteudo) + "\n", encoding="utf-8")

    # O índice é uma listagem de conveniência e cresce a cada juntada, por
    # isso fica FORA do selo (ver `core.hashing._arquivos_para_hashear`).
    # Ele diz isso de si mesmo: quem confere a integridade do caso precisa
    # saber que a prova está nos complementos, não nesta listagem.
    indice = pasta / NOME_INDICE_COMPLEMENTOS
    novo = not indice.exists()
    with open(indice, "a", encoding="utf-8") as arquivo_indice:
        if novo:
            arquivo_indice.write(
                "# Índice dos complementos deste caso — listagem de conveniência.\n"
                "# NÃO entra no manifesto: cresce a cada juntada. O que é selado\n"
                "# é cada complemento, no arquivo próprio indicado abaixo.\n"
            )
        arquivo_indice.write(
            f"{carimbo.astimezone().isoformat(timespec='seconds')}  {titulo}  ->  {caminho.name}\n"
        )

    return caminho
