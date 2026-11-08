"""
Testes do relatorio de conteudo -- o entregavel que a investigacao le.

A suite faz aquisicao com cadeia de custodia impecavel e entrega dump de
maquina. Este relatorio fecha a distancia: planilha para o analista cruzar,
PDF para juntar aos autos.

Tres regras estruturais, uma por bloco:

[2] Fica FORA do selo. E documento derivado, produzido depois da coleta, e
    precisa poder ser REGERADO quando o normalizador melhorar -- sem tocar
    na evidencia. Gravar dentro da aquisicao a quebraria, como aconteceu com
    o laudo antes da correcao de hoje.
[3] Confere a origem contra o selo. Relatorio construido sobre arquivo que
    nao confere mais nao pode circular sem dizer isso em letras grandes.
[4] Zero nunca vem sozinho. Provider recusou, provider respondeu vazio e
    modulo nao executado sao tres zeros que sustentam conclusoes diferentes.
"""
import sys
import tempfile
from datetime import timedelta, timezone
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.hashing import conferir_manifesto, gerar_manifesto
from services.relatorio_service import (
    NOME_DESCARTES,
    NOME_PDF,
    NOME_PROCEDENCIA,
    PASTA_RELATORIOS,
    RelatorioService,
)

falhas = []
BRASILIA = timezone(timedelta(hours=-3), "-03")

SMS_BRUTO = (
    "Row: 0 _id=1, address=+5511988887777, date=1755123456789, type=1, read=1, "
    "body=Oi, tudo bem?\n"
    "segunda linha da mesma mensagem\n"
    "Row: 1 _id=2, address=+5511977776666, date=1755123999000, type=2, read=0, body=Resposta\n"
)
CHAMADAS_BRUTO = (
    "Row: 0 _id=1, number=+5511900001111, date=1755123456789, type=3, duration=0, name=Fulano\n"
)
RECUSA = (
    "java.lang.SecurityException: Permission Denial: opening provider "
    "com.android.providers.contacts.ContactsProvider2 requires "
    "android.permission.READ_CONTACTS\n"
)


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar_aquisicao(raiz: Path, sms=SMS_BRUTO, chamadas=CHAMADAS_BRUTO, agenda=RECUSA) -> Path:
    aquisicao = raiz / "CASO_001" / "android_20260823_150000"
    (aquisicao / "sms").mkdir(parents=True)
    (aquisicao / "contacts_calls").mkdir(parents=True)
    if sms is not None:
        (aquisicao / "sms" / "sms_todas.txt").write_text(sms, encoding="utf-8")
    if chamadas is not None:
        (aquisicao / "contacts_calls" / "registro_chamadas_bruto.txt").write_text(
            chamadas, encoding="utf-8"
        )
    if agenda is not None:
        (aquisicao / "contacts_calls" / "agenda_contatos_bruta.txt").write_text(
            agenda, encoding="utf-8"
        )
    gerar_manifesto(aquisicao)
    return aquisicao


# ---------------------------------------------------------------------------
print("\n[1] O bruto vira planilha que o analista consegue abrir")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    resultado = RelatorioService.gerar(aquisicao, fuso=BRASILIA)

    checar("gerou sem erro", not resultado.erro)
    checar("tres registros no total", resultado.total_registros == 3)
    checar("nada ficou por interpretar", resultado.total_descartes == 0)

    csv_sms = resultado.pasta / "sms.csv"
    checar("planilha de SMS gerada", csv_sms.is_file())
    checar("planilha de chamadas gerada", (resultado.pasta / "chamada.csv").is_file())
    checar("procedencia gravada", (resultado.pasta / NOME_PROCEDENCIA).is_file())
    checar("PDF gerado", (resultado.pasta / NOME_PDF).is_file())
    # Agenda recusou acesso: nao ha planilha, e a razao esta na procedencia.
    checar("sem planilha para o artefato recusado", not (resultado.pasta / "contato.csv").exists())

    corpo = csv_sms.read_text(encoding="utf-8-sig")
    checar("a data saiu legivel, nao em epoch", "13/08/2025" in corpo)
    checar("com o fuso declarado na propria celula", "-03" in corpo)
    checar("o tipo virou palavra", "Recebida" in corpo and "Enviada" in corpo)
    checar("o corpo com virgula ficou inteiro", "Oi, tudo bem?" in corpo)
    checar("a quebra de linha da mensagem foi preservada", "segunda linha da mesma mensagem" in corpo)
    checar("cada linha diz o arquivo de origem", "sms/sms_todas.txt" in corpo)
    # Excel em portugues abre UTF-8 sem BOM como Latin-1 e estraga os acentos.
    checar("gravada com BOM, para o Excel abrir certo", csv_sms.read_bytes().startswith(b"\xef\xbb\xbf"))

# ---------------------------------------------------------------------------
print("\n[2] O relatorio nasce FORA do selo e pode ser regerado")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    checar("a aquisicao comeca integra", conferir_manifesto(aquisicao).integro)

    primeiro = RelatorioService.gerar(aquisicao, fuso=BRASILIA)
    checar(
        "o relatorio fica fora da aquisicao",
        PASTA_RELATORIOS in primeiro.pasta.parts and aquisicao.name not in primeiro.pasta.parent.name,
    )
    checar("na pasta do caso", primeiro.pasta.parent.parent == aquisicao.parent)
    checar("e a aquisicao continua integra", conferir_manifesto(aquisicao).integro)

    # Regerar e legitimo: o normalizador melhora, o relatorio se refaz. O
    # anterior nao e sobrescrito -- cada geracao tem carimbo proprio.
    segundo = RelatorioService.gerar(aquisicao, fuso=BRASILIA, pasta_destino=primeiro.pasta.parent / "outro")
    checar("regerar nao toca na aquisicao", conferir_manifesto(aquisicao).integro)
    checar("e produz outra pasta", segundo.pasta != primeiro.pasta)
    checar("com o mesmo conteudo", segundo.total_registros == primeiro.total_registros)

# ---------------------------------------------------------------------------
print("\n[3] Origem que nao confere mais com o selo e denunciada")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    RelatorioService.gerar(aquisicao, fuso=BRASILIA)

    (aquisicao / "sms" / "sms_todas.txt").write_text(
        "Row: 0 _id=1, address=+55, date=1755123456789, type=1, read=1, body=TROCADO\n",
        encoding="utf-8",
    )
    resultado = RelatorioService.gerar(aquisicao, fuso=BRASILIA)

    checar("a divergencia e detectada", resultado.origens_divergentes == ["sms/sms_todas.txt"])
    procedencia = (resultado.pasta / NOME_PROCEDENCIA).read_text(encoding="utf-8")
    checar("a procedencia grita no topo", "ORIGEM DIVERGENTE DO SELO" in procedencia)
    checar("e diz o que isso significa", "não corresponde ao que foi selado" in procedencia)
    checar("apontando o arquivo", "sms/sms_todas.txt" in procedencia)
    checar("o relatorio ainda e gerado, com a ressalva", resultado.total_registros == 2)

    # Sem manifesto, nao se pode AFIRMAR que confere -- nem que diverge.
    sem_selo = Path(temporario) / "solto" / "android_y"
    (sem_selo / "sms").mkdir(parents=True)
    (sem_selo / "sms" / "sms_todas.txt").write_text(SMS_BRUTO, encoding="utf-8")
    resultado = RelatorioService.gerar(sem_selo, fuso=BRASILIA)
    checar("sem manifesto, nada e declarado como divergente", not resultado.origens_divergentes)
    procedencia = (resultado.pasta / NOME_PROCEDENCIA).read_text(encoding="utf-8")
    checar(
        "mas a procedencia diz que nao houve como confrontar",
        "não foi possível confrontá-lo com o selo" in procedencia,
    )

# ---------------------------------------------------------------------------
print("\n[4] Zero nunca vem sozinho: sempre com a razao do zero")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    # Agenda recusada, chamadas nao coletadas, SMS vazio de verdade.
    aquisicao = montar_aquisicao(Path(temporario), sms="", chamadas=None, agenda=RECUSA)
    resultado = RelatorioService.gerar(aquisicao, fuso=BRASILIA)
    procedencia = (resultado.pasta / NOME_PROCEDENCIA).read_text(encoding="utf-8")

    checar("nenhum registro", resultado.total_registros == 0)
    checar(
        "provider que RECUSOU e dito como recusa",
        "RECUSOU a consulta" in procedencia,
    )
    checar(
        "e advertindo que recusa nao e ausencia no aparelho",
        "diferente de não existir dado" in procedencia,
    )
    checar(
        "provider vazio e dito como resposta vazia",
        "respondeu à consulta e não retornou" in procedencia,
    )
    checar(
        "modulo nao executado e dito como ausencia de COLETA",
        "é ausência de coleta" in procedencia,
    )
    checar(
        "e o alcance adverte que zero nao prova ausencia",
        "NUNCA significa, por si só, ausência de dado" in procedencia,
    )

    # O motivo do zero precisa chegar NA TELA, junto do resultado. Na
    # primeira execucao real o examinador viu "0 registros" e saiu
    # procurando planilha que nao existia -- a explicacao estava num
    # arquivo que ele teria de abrir para descobrir que nao havia o que
    # abrir.
    resumo = "\n".join(resultado.resumo_por_artefato)
    # A contagem sai da propria lista de artefatos: e isso que a assercao
    # diz, e um numero fixo aqui passaria a falhar a cada artefato novo sem
    # que nada estivesse errado.
    checar(
        "o resumo tem uma linha por artefato",
        len(resultado.resumo_por_artefato) == len(resultado.artefatos),
    )
    checar("dizendo qual respondeu vazio", "respondeu à consulta" in resumo)
    checar("qual recusou", "RECUSOU" in resumo)
    checar("e qual nem foi coletado", "NÃO COLETADO" in resumo)
    checar(
        "sem deixar 'nao coletado' virar ausencia de dado",
        "Não é ausência de dado no aparelho" in resumo,
    )

with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    resultado = RelatorioService.gerar(aquisicao, fuso=BRASILIA)
    resumo = "\n".join(resultado.resumo_por_artefato)
    checar("havendo registros, o resumo aponta a planilha", "sms.csv" in resumo)
    checar("com a contagem junto", "2 registro(s)" in resumo)

# ---------------------------------------------------------------------------
print("\n[5] O que nao foi interpretado aparece, e o relatorio se declara incompleto")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    misturado = SMS_BRUTO + "Row: 2 lixo sem nenhum campo\n"
    aquisicao = montar_aquisicao(Path(temporario), sms=misturado)
    resultado = RelatorioService.gerar(aquisicao, fuso=BRASILIA)

    checar("os registros bons entram", resultado.total_registros == 3)
    checar("e o ruim e contado", resultado.total_descartes == 1)

    caminho = resultado.pasta / NOME_DESCARTES
    checar("o arquivo de descartes e gravado", caminho.is_file())
    corpo = caminho.read_text(encoding="utf-8")
    checar("dizendo que o relatorio esta INCOMPLETO", "INCOMPLETO" in corpo)
    checar("e mandando examinar o bruto selado", "aquisição selada" in corpo)

    procedencia = (resultado.pasta / NOME_PROCEDENCIA).read_text(encoding="utf-8")
    checar("a procedencia tambem avisa", "NÃO interpretado" in procedencia)

# ---------------------------------------------------------------------------
print("\n[6] Aquisicao sem artefato nenhum nao gera relatorio vazio")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    vazia = Path(temporario) / "CASO_001" / "android_z"
    vazia.mkdir(parents=True)
    resultado = RelatorioService.gerar(vazia, fuso=BRASILIA)

    checar("nao gera pasta", resultado.pasta is None)
    checar("e explica o motivo", "Nenhum arquivo bruto" in resultado.erro)
    checar("sugerindo a causa provavel", "podem não ter sido executados" in resultado.erro)

# ---------------------------------------------------------------------------
print("\n[7] Sem fuso informado, as datas ficam em UTC e isso e declarado")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = montar_aquisicao(Path(temporario))
    resultado = RelatorioService.gerar(aquisicao)
    procedencia = (resultado.pasta / NOME_PROCEDENCIA).read_text(encoding="utf-8")
    checar("o fuso ausente e declarado, nao suposto", "nenhum fuso informado" in procedencia)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
