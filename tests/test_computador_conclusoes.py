"""
Testes das conclusoes dos modulos de Computador.

O modulo de Computador nasceu com o commit inicial e nunca passou pela
revisao de doutrina que o Android sofreu. Quando passou, apareceram quatro
defeitos da mesma familia de sempre -- a ferramenta afirmando o que nao
verificou -- e dois deles apresentavam como boa uma evidencia inexistente.

O bloco [1] guarda o pior. `CreateFileW` devolve INVALID_HANDLE_VALUE
quando nao consegue abrir o volume, e o codigo comparava com
`ctypes.c_void_p(-1).value` (18446744073709551615). Sem `restype`
declarado, porem, o ctypes devolve o handle num `c_long`: -1. Os dois
valores nunca sao iguais, entao a checagem de erro jamais disparava. O
codigo seguia com handle invalido, o ReadFile falhava no primeiro bloco,
o laco quebrava com zero byte gravado -- e o modulo retornava SUCESSO com
"Imagem fisica gerada (0.00 MB)". O teste chama as duas versoes lado a
lado, para que a diferenca fique registrada e nao volte.

O bloco [2] cobre a segunda metade do mesmo defeito: erro de leitura e fim
de volume eram a mesma condicao de saida do laco, e imagem truncada por
setor defeituoso saia como completa.

Os blocos [3] a [5] cobrem o que faltava aos outros tres modulos: recusa
do sistema contada e declarada, ausencia distinguida de negativa, e
resultado vazio deixando de ser sucesso.
"""
import ctypes
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.companheiros import companheiros_de
from core.computador.extractors import windows_artifacts
from core.computador.extractors.file_index import IndiceArquivosExtractor
from core.computador.extractors.logical_copy import CopiaLogicaExtractor
from core.computador.extractors.physical_image import (
    INVALID_HANDLE_VALUE,
    ImagemFisicaExtractor,
    kernel32_tipado,
)
from core.computador.extractors.windows_artifacts import (
    AUSENTE,
    COPIADO,
    NEGADO,
    ArtefatosWindowsExtractor,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def preparar(extrator, pasta):
    """Deixa um extrator pronto para `executar()` sobre uma pasta qualquer."""
    extrator.definir_unidade(str(pasta))
    return extrator


VOLUME_INEXISTENTE = "\\\\.\\ZZ:"
OPEN_EXISTING = 3

# ---------------------------------------------------------------------------
print("\n[1] Falha ao abrir o volume deixa de passar por sucesso")
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    # Instancia nova e sem tipos declarados: e exatamente o que o modulo
    # fazia antes. O handle invalido volta como -1 e escapa da comparacao.
    sem_tipos = ctypes.WinDLL("kernel32")
    handle_sem_tipos = sem_tipos.CreateFileW(
        VOLUME_INEXISTENTE, 0, 3, None, OPEN_EXISTING, 0, None
    )
    checar(
        "sem restype o handle invalido volta como -1",
        handle_sem_tipos == -1,
    )
    checar(
        "e por isso escapava da checagem (o defeito)",
        handle_sem_tipos != INVALID_HANDLE_VALUE,
    )

    kernel32 = kernel32_tipado()
    handle = kernel32.CreateFileW(
        VOLUME_INEXISTENTE, 0, 3, None, OPEN_EXISTING, 0, None
    )
    checar(
        "com restype declarado a checagem detecta a falha",
        (not handle) or handle == INVALID_HANDLE_VALUE,
    )
else:
    print("  (pulado: a API e do Windows)")

# ---------------------------------------------------------------------------
print("\n[2] A conferencia de tamanho da imagem")
# ---------------------------------------------------------------------------
conferir = ImagemFisicaExtractor._conferir_tamanho

completa, motivo = conferir(0, 1000)
checar("zero byte lido e FALHA, nunca imagem", not completa)
checar("e o motivo diz que nao ha imagem", "Nenhum byte" in motivo)

completa, _ = conferir(0, None)
checar("zero byte e FALHA mesmo sem tamanho esperado", not completa)

completa, motivo = conferir(1001, 1000)
checar("imagem MAIOR que o volume e FALHA", not completa)
checar("porque byte a mais nao pertence ao volume", "MAIOR" in motivo)

completa, _ = conferir(500, 1000)
checar("imagem com metade do volume e FALHA", not completa)

completa, ressalva = conferir(995, 1000)
checar("dentro da margem de 99% e sucesso", completa)
checar("mas com ressalva declarada", bool(ressalva))

completa, ressalva = conferir(1000, 1000)
checar("tamanho exato e sucesso sem ressalva", completa and not ressalva)

completa, ressalva = conferir(1000, None)
checar("sem tamanho do volume segue como sucesso", completa)
checar("declarando que a completude NAO foi verificada", "nao foi verificada" in
       ressalva.replace("ã", "a").replace("é", "e").replace("ú", "u"))

# ---------------------------------------------------------------------------
print("\n[3] Ausencia deixa de ser confundida com recusa")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    (base / "existe.txt").write_text("conteudo", encoding="utf-8")
    extrator = ArtefatosWindowsExtractor()

    estado = extrator._copiar_arquivo(base / "existe.txt", base / "saida" / "existe.txt")
    checar("arquivo que existe e copiado", estado == COPIADO)
    checar("e chega ao destino", (base / "saida" / "existe.txt").is_file())

    estado = extrator._copiar_arquivo(base / "nao_existe.txt", base / "saida" / "x.txt")
    checar("arquivo que nao existe e AUSENTE", estado == AUSENTE)

    # Recusa de leitura simulada no ponto exato onde ela ocorre.
    copy2_original = windows_artifacts.shutil.copy2
    windows_artifacts.shutil.copy2 = lambda *a, **k: (_ for _ in ()).throw(
        PermissionError("acesso negado pelo sistema")
    )
    try:
        estado = extrator._copiar_arquivo(
            base / "existe.txt", base / "saida2" / "existe.txt"
        )
    finally:
        windows_artifacts.shutil.copy2 = copy2_original
    checar("arquivo que existe e nao pode ser lido e NEGADO", estado == NEGADO)
    checar("os tres estados sao distintos entre si", len({COPIADO, AUSENTE, NEGADO}) == 3)

# ---------------------------------------------------------------------------
print("\n[4] Coleta de artefatos: vazio, recusado e parcial")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_sem_windows"
    unidade.mkdir()
    saida = Path(tmp) / "aquisicao_a"
    saida.mkdir()

    resultado = preparar(ArtefatosWindowsExtractor(), unidade).executar(saida)
    checar("unidade sem Windows e FALHA", not resultado.sucesso)
    checar(
        "e a mensagem diz que nada foi negado",
        "nenhum acesso foi negado" in resultado.mensagem,
    )
    checar(
        "sem ressalva de acesso negado, porque nada foi impedido",
        not resultado.detalhes.get("acesso_negado"),
    )

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_windows"
    config = unidade / "Windows" / "System32" / "config"
    config.mkdir(parents=True)
    for hive in ("SAM", "SYSTEM"):
        (config / hive).write_text("hive falso", encoding="utf-8")
    prefetch = unidade / "Windows" / "Prefetch"
    prefetch.mkdir()
    (prefetch / "APP.pf").write_text("pf falso", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_b"
    saida.mkdir()

    resultado = preparar(ArtefatosWindowsExtractor(), unidade).executar(saida)
    checar("com artefatos reais e sucesso", resultado.sucesso)
    checar("conta arquivos, nao categorias", resultado.detalhes["arquivos_copiados"] == 3)
    checar(
        "declara quais categorias sairam vazias",
        "Lixeira" in resultado.mensagem and "Navegadores" in resultado.mensagem,
    )
    checar("sem recusa, sem ressalva", not resultado.detalhes.get("acesso_negado"))

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_negada"
    config = unidade / "Windows" / "System32" / "config"
    config.mkdir(parents=True)
    for hive in ("SAM", "SYSTEM"):
        (config / hive).write_text("hive em uso", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_c"
    saida.mkdir()

    copy2_original = windows_artifacts.shutil.copy2
    windows_artifacts.shutil.copy2 = lambda *a, **k: (_ for _ in ()).throw(
        PermissionError("hive em uso pelo sistema")
    )
    try:
        resultado = preparar(ArtefatosWindowsExtractor(), unidade).executar(saida)
    finally:
        windows_artifacts.shutil.copy2 = copy2_original

    checar("tudo recusado e FALHA, nunca 'nao encontrado'", not resultado.sucesso)
    checar("com a recusa contada", resultado.detalhes.get("acesso_negado") == 2)
    checar(
        "e a mensagem recusa a conclusao negativa",
        "nada se pode afirmar" in resultado.mensagem.lower(),
    )

# ---------------------------------------------------------------------------
print("\n[5] Indice de arquivos: vazio deixa de ser sucesso")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_vazia"
    unidade.mkdir()
    saida = Path(tmp) / "aquisicao_d"
    saida.mkdir()

    resultado = preparar(IndiceArquivosExtractor(), unidade).executar(saida)
    checar("indice vazio e FALHA", not resultado.sucesso)
    checar(
        "distinguindo disco vazio de disco recusado",
        "nenhum acesso foi negado" in resultado.mensagem,
    )

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_com_arquivos"
    (unidade / "sub").mkdir(parents=True)
    (unidade / "a.txt").write_text("a", encoding="utf-8")
    (unidade / "sub" / "b.txt").write_text("b", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_e"
    saida.mkdir()

    resultado = preparar(IndiceArquivosExtractor(), unidade).executar(saida)
    checar("com arquivos e sucesso", resultado.sucesso)
    checar("indexando os dois", resultado.detalhes["arquivos_indexados"] == 2)
    checar("sem ressalva quando nada foi recusado",
           not resultado.detalhes.get("acesso_negado"))

    linhas = resultado.caminho_saida.read_text(encoding="utf-8").strip().splitlines()
    checar("o CSV tem cabecalho e uma linha por arquivo", len(linhas) == 3)

# ---------------------------------------------------------------------------
print("\n[6] Copia logica: pasta perdida vira ressalva, nao silencio")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_perfil"
    documentos = unidade / "Documentos"
    downloads = unidade / "Downloads"
    documentos.mkdir(parents=True)
    downloads.mkdir(parents=True)
    (documentos / "doc.txt").write_text("doc", encoding="utf-8")
    (downloads / "baixado.txt").write_text("baixado", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_f"
    saida.mkdir()

    resultado = preparar(CopiaLogicaExtractor(), unidade).executar(saida)
    checar("copia com duas pastas e sucesso", resultado.sucesso)
    checar("com os dois arquivos", resultado.detalhes["arquivos_copiados"] == 2)
    checar("e sem ressalva", not resultado.detalhes.get("copia_incompleta"))

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_parcial"
    documentos = unidade / "Documentos"
    downloads = unidade / "Downloads"
    documentos.mkdir(parents=True)
    downloads.mkdir(parents=True)
    (documentos / "doc.txt").write_text("doc", encoding="utf-8")
    (downloads / "baixado.txt").write_text("baixado", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_g"
    saida.mkdir()

    extrator = preparar(CopiaLogicaExtractor(), unidade)
    copiar_original = extrator._copiar_pasta

    def copiar_com_falha(origem, destino, ignoradas):
        if origem.name == "Documentos":
            raise OSError("dispositivo nao responde")
        return copiar_original(origem, destino, ignoradas)

    extrator._copiar_pasta = copiar_com_falha
    resultado = extrator.executar(saida)

    checar("uma pasta perdida nao anula a copia", resultado.sucesso)
    checar(
        "mas a perda vira ressalva declarada",
        "Documentos" in str(resultado.detalhes.get("copia_incompleta", "")),
    )
    checar(
        "e aparece na mensagem que vai ao laudo",
        "RESSALVA" in resultado.mensagem and "Documentos" in resultado.mensagem,
    )

# ---------------------------------------------------------------------------
print("\n[7] A copia acha toda variante, e nao renomeia a evidencia")
# ---------------------------------------------------------------------------
# Os dois defeitos deste bloco so apareceram na primeira execucao contra
# pendrive real, em 30/08/2026. A leitura do codigo nao os pegou.
with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_bilingue"
    # Disco com as DUAS grafias, o que acontece em maquina que trocou de
    # idioma ou teve dois donos. O laco parava na primeira, e a segunda
    # pasta inteira sumia sem uma linha no resultado.
    for nome in ("Documents", "Documentos", "Imagens"):
        (unidade / nome).mkdir(parents=True)
        (unidade / nome / "arquivo.txt").write_text(nome, encoding="utf-8")
    saida = Path(tmp) / "aquisicao_h"
    saida.mkdir()

    extrator = preparar(CopiaLogicaExtractor(), unidade)
    achadas = extrator._localizar_pastas_alvo(unidade)
    destinos = {destino for destino, _origem in achadas}
    origens = {origem.name for _destino, origem in achadas}

    checar("as duas grafias de Documentos sao achadas",
           {"Documents", "Documentos"} <= origens)
    checar("nenhuma pasta e listada duas vezes", len(achadas) == len(origens))
    checar("o destino usa o nome real do disco, nao o rotulo interno",
           "Imagens" in destinos and "Pictures" not in destinos)

    resultado = extrator.executar(saida)
    checar("os tres arquivos sao copiados", resultado.detalhes["arquivos_copiados"] == 3)
    checar("a pasta que antes sumia esta na copia",
           (saida / "copia_logica" / "Documentos" / "arquivo.txt").is_file())
    checar("e a outra grafia tambem, sem colidir",
           (saida / "copia_logica" / "Documents" / "arquivo.txt").is_file())

    mapa = {m["origem"]: m["destino"] for m in resultado.detalhes["pastas_copiadas"]}
    checar("o resultado registra origem e destino de cada pasta", len(mapa) == 3)
    checar("e a origem e o caminho real do disco",
           str(unidade / "Documentos") in mapa)

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade_perfis"
    for perfil in ("ana", "bruno"):
        pasta = unidade / "Users" / perfil / "Downloads"
        pasta.mkdir(parents=True)
        (pasta / "arquivo.txt").write_text(perfil, encoding="utf-8")
    saida = Path(tmp) / "aquisicao_i"
    saida.mkdir()

    resultado = preparar(CopiaLogicaExtractor(), unidade).executar(saida)
    checar("pastas homonimas de perfis diferentes nao se sobrepoem",
           resultado.detalhes["arquivos_copiados"] == 2)
    checar("porque o destino leva o nome do perfil",
           (saida / "copia_logica" / "ana_Downloads" / "arquivo.txt").is_file()
           and (saida / "copia_logica" / "bruno_Downloads" / "arquivo.txt").is_file())

# ---------------------------------------------------------------------------
print("\n[7b] O que a copia NAO leva e contado -- achado do pendrive real")
# ---------------------------------------------------------------------------
# Num pendrive o material mora na raiz, nao em pasta de usuario. A execucao
# real de 30/08 devolveu "Copia logica concluida (6 arquivo(s))", sucesso
# limpo, tendo ignorado o unico arquivo solto na raiz -- justamente o que o
# examinador esperava encontrar. A limitacao ja estava declarada em
# `limitacoes_conhecidas`, mas o RESULTADO contava so o que levou.

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "pendrive"
    (unidade / "Documentos").mkdir(parents=True)
    (unidade / "Documentos" / "dentro.txt").write_text("x", encoding="utf-8")
    (unidade / "teste pendrive.txt").write_text("solto na raiz", encoding="utf-8")
    (unidade / "Pasta Qualquer").mkdir()
    saida = Path(tmp) / "aquisicao_j"
    saida.mkdir()

    resultado = preparar(CopiaLogicaExtractor(), unidade).executar(saida)

    checar("a copia segue sendo sucesso -- dado foi obtido", resultado.sucesso)
    fora = resultado.detalhes.get("itens_fora_do_alcance", "")
    checar("mas o que ficou fora e contado", bool(fora))
    checar("o arquivo solto na raiz e nomeado", "teste pendrive.txt" in fora)
    checar("a pasta de nome nao reconhecido tambem", "Pasta Qualquer" in fora)
    checar("a pasta de usuario copiada NAO entra na conta", "Documentos" not in fora)
    checar("e a mensagem do resultado declara a ressalva",
           "RESSALVA" in resultado.mensagem and "raiz" in resultado.mensagem)
    checar("apontando onde o material fora do alcance pode ser obtido",
           "Índice de Arquivos" in resultado.mensagem)

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "disco_limpo"
    (unidade / "Documentos").mkdir(parents=True)
    (unidade / "Documentos" / "dentro.txt").write_text("x", encoding="utf-8")
    saida = Path(tmp) / "aquisicao_k"
    saida.mkdir()

    resultado = preparar(CopiaLogicaExtractor(), unidade).executar(saida)
    checar("unidade sem nada fora do alcance nao inventa ressalva",
           "itens_fora_do_alcance" not in resultado.detalhes)
    checar("e a mensagem fica limpa", "RESSALVA" not in resultado.mensagem)


# ---------------------------------------------------------------------------
print("\n[8] As ressalvas usam as chaves que o servico reconhece")
# ---------------------------------------------------------------------------
from services.extraction_service import CHAVES_RESSALVA, indica_ressalva  # noqa: E402

checar("acesso_negado e chave de ressalva", "acesso_negado" in CHAVES_RESSALVA)
checar("copia_incompleta e chave de ressalva", "copia_incompleta" in CHAVES_RESSALVA)
checar("itens_fora_do_alcance e chave de ressalva",
       "itens_fora_do_alcance" in CHAVES_RESSALVA)
checar(
    "recusa de acesso e reconhecida como ressalva",
    indica_ressalva({"acesso_negado": 3}),
)
checar(
    "resultado limpo nao vira ressalva",
    not indica_ressalva({"arquivos_copiados": 10}),
)

# ---------------------------------------------------------------------------
print("\n[9] Os arquivos companheiros vem junto")
# ---------------------------------------------------------------------------
# Um banco SQLite nao e um arquivo, sao tres: o `-wal` guarda o que ainda
# nao foi consolidado no principal -- as mensagens da vespera da coleta.
# Um hive do registro tem seus `.LOG1`/`.LOG2` pela mesma razao. Copiar so
# o arquivo principal perde isso, e o arquivo abre normalmente depois: nada
# avisa que faltou. Perda silenciosa de evidencia e a pior especie.
with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    (base / "History").write_text("banco", encoding="utf-8")
    (base / "History-wal").write_text("o que ainda nao entrou", encoding="utf-8")
    (base / "History-shm").write_text("indice do wal", encoding="utf-8")
    (base / "SYSTEM").write_text("hive", encoding="utf-8")
    (base / "SYSTEM.LOG1").write_text("transacao pendente", encoding="utf-8")
    (base / "sozinho.txt").write_text("sem companheiro", encoding="utf-8")

    achados = {c.name for c in companheiros_de(base / "History")}
    checar("o wal e achado", "History-wal" in achados)
    checar("o shm tambem", "History-shm" in achados)
    checar("e nada alheio entra", achados == {"History-wal", "History-shm"})

    achados = {c.name for c in companheiros_de(base / "SYSTEM")}
    checar("o log de transacao do hive e achado", achados == {"SYSTEM.LOG1"})

    checar("arquivo sem companheiro devolve lista vazia",
           companheiros_de(base / "sozinho.txt") == [])
    checar("arquivo inexistente nao inventa companheiro",
           companheiros_de(base / "nao_existe") == [])

with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade"
    config = unidade / "Windows" / "System32" / "config"
    config.mkdir(parents=True)
    (config / "SYSTEM").write_text("hive", encoding="utf-8")
    (config / "SYSTEM.LOG1").write_text("transacao pendente", encoding="utf-8")
    (config / "SYSTEM.LOG2").write_text("outra transacao", encoding="utf-8")

    perfil = unidade / "Users" / "ana" / "AppData" / "Local" / "Google" / "Chrome"
    padrao = perfil / "User Data" / "Default"
    padrao.mkdir(parents=True)
    (padrao / "History").write_text("banco", encoding="utf-8")
    (padrao / "History-wal").write_text("navegacao recente", encoding="utf-8")

    saida = Path(tmp) / "aquisicao_j"
    saida.mkdir()
    resultado = preparar(ArtefatosWindowsExtractor(), unidade).executar(saida)

    destino = saida / "artefatos_windows"
    checar("o hive e copiado", (destino / "registro" / "SYSTEM").is_file())
    checar("com seus dois logs de transacao",
           (destino / "registro" / "SYSTEM.LOG1").is_file()
           and (destino / "registro" / "SYSTEM.LOG2").is_file())

    historico = destino / "navegadores" / "ana" / "Chrome" / "Default"
    checar("o historico e copiado", (historico / "History").is_file())
    checar("com o write-ahead log junto", (historico / "History-wal").is_file())

    # 1 hive + 2 logs + 1 historico + 1 wal = 5. Companheiro e evidencia, e
    # conta como arquivo copiado -- nao pode entrar de carona sem aparecer.
    checar("os companheiros entram na contagem",
           resultado.detalhes["arquivos_copiados"] == 5)
    checar("e o conteudo do wal chega intacto",
           (historico / "History-wal").read_text(encoding="utf-8") == "navegacao recente")

# ---------------------------------------------------------------------------
print("\n[10] Os acervos de correio sao coletados, e nao interpretados")
# ---------------------------------------------------------------------------
# Um .pst e a caixa de correio inteira num arquivo so -- mensagens, pastas
# e anexos. E o artefato de e-mail mais denso que um disco periciado
# costuma ter, e o modulo nao o procurava.
def montar_perfil_com_correio(unidade: Path, usuario: str) -> None:
    perfil = unidade / "Users" / usuario

    outlook = perfil / "AppData" / "Local" / "Microsoft" / "Outlook"
    outlook.mkdir(parents=True)
    (outlook / "caixa.pst").write_text("acervo pst", encoding="utf-8")
    (outlook / "cache.ost").write_text("acervo ost", encoding="utf-8")

    # A pasta padrao do Outlook muda com o idioma de instalacao -- a mesma
    # armadilha que fez a copia logica perder uma pasta inteira.
    arquivos_pt = perfil / "Documentos" / "Arquivos do Outlook"
    arquivos_pt.mkdir(parents=True)
    (arquivos_pt / "arquivo_morto.pst").write_text("pst em portugues", encoding="utf-8")

    thunderbird = perfil / "AppData" / "Roaming" / "Thunderbird" / "Profiles" / "abc.default"
    (thunderbird / "Mail" / "Local Folders").mkdir(parents=True)
    (thunderbird / "Mail" / "Local Folders" / "Inbox").write_text("mbox", encoding="utf-8")
    (thunderbird / "global-messages-db.sqlite").write_text("indice", encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    unidade = Path(tmp) / "unidade"
    (unidade / "Windows" / "System32" / "config").mkdir(parents=True)
    montar_perfil_com_correio(unidade, "ana")
    saida = Path(tmp) / "aquisicao_k"
    saida.mkdir()

    resultado = preparar(ArtefatosWindowsExtractor(), unidade).executar(saida)
    correio = saida / "artefatos_windows" / "correio" / "ana"

    checar("o .pst do Outlook e copiado",
           (correio / "Outlook" / "caixa.pst").is_file())
    checar("o .ost tambem, que e o cache local do servidor",
           (correio / "Outlook" / "cache.ost").is_file())
    checar("a pasta padrao em portugues nao e esquecida",
           (correio / "Outlook_Arquivos_pt" / "arquivo_morto.pst").is_file())
    checar("o perfil do Thunderbird vem inteiro",
           (correio / "Thunderbird" / "abc.default" / "Mail" / "Local Folders" / "Inbox").is_file())
    checar("com o indice de mensagens junto",
           (correio / "Thunderbird" / "abc.default" / "global-messages-db.sqlite").is_file())

    checar("a categoria aparece na contagem por categoria",
           resultado.detalhes["copiados_por_categoria"]["Correio eletrônico"] == 5)
    checar("e nao e reportada como vazia",
           "Correio eletrônico" not in resultado.mensagem.split("Categorias sem")[-1]
           if "Categorias sem" in resultado.mensagem else True)

with tempfile.TemporaryDirectory() as tmp:
    # Disco de sistema sem cliente de e-mail instalado: zero coletado e
    # zero negado. Ausencia de acervo nao e recusa, e nao pode virar uma.
    unidade = Path(tmp) / "unidade"
    (unidade / "Users" / "bruno").mkdir(parents=True)
    (unidade / "Windows" / "System32" / "config").mkdir(parents=True)
    saida = Path(tmp) / "aquisicao_l"
    saida.mkdir()

    extrator = preparar(ArtefatosWindowsExtractor(), unidade)
    copiados, negados = extrator._coletar_correio(unidade, saida / "artefatos_windows")
    checar("sem cliente de e-mail, nada e copiado", copiados == 0)
    checar("e nada e reportado como negado", negados == 0)

# A ferramenta preserva o acervo e NAO o abre. Prometer leitura de .pst
# aqui seria afirmar o que ela nao sustenta -- mesma linha do backup
# .crypt do WhatsApp, preservado sem ser decifrado.
limitacoes = " ".join(ArtefatosWindowsExtractor.limitacoes_conhecidas)
checar("a limitacao declara que o acervo NAO e aberto",
       "NÃO são abertos por esta ferramenta" in limitacoes)
checar("e distingue ausencia de acervo local de ausencia de correspondencia",
       "não significa ausência de correspondência" in limitacoes)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
