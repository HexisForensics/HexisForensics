"""
Testes da normalizacao das saidas brutas dos Content Providers.

O que os extratores gravam e fiel e ilegivel: `date=1755123456789`. Este
modulo converte isso em registro estruturado, para o relatorio de conteudo e
para um futuro indexador -- os dois consomem o mesmo dado, e por isso o
parser nao pode viver dentro de nenhum deles.

ATENCAO ao contexto destes testes: os aparelhos de teste disponiveis (API 21
e API 28) NEGARAM acesso ao call log e devolveram SMS vazio. Ou seja, o
parser foi escrito contra o formato documentado do `content query`, e os
casos abaixo sao SINTETICOS. E por isso que o bloco [5] existe: o que o
parser nao compreender tem de aparecer contado, para que a divergencia surja
no primeiro aparelho real em vez de virar silencio.

As quatro armadilhas do formato, uma por bloco:

[1] corpo com quebra de linha  -- parte a mensagem em duas
[2] virgula dentro do valor    -- parte o campo no meio
[3] epoch em ms ou em segundos -- joga a data para 1970 ou para o ano 5000
[4] saida de erro nao e dado   -- vira "nenhuma mensagem", que e o oposto
"""
import sys
from datetime import timedelta, timezone
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.normalizacao import (
    indica_acesso_negado,
    normalizar_chamadas,
    normalizar_contatos,
    normalizar_sms,
)

falhas = []
BRASILIA = timezone(timedelta(hours=-3), "-03")


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
print("\n[1] Corpo com quebra de linha continua sendo UMA mensagem")
# ---------------------------------------------------------------------------
# O `content query` imprime um registro por linha, mas o corpo pode conter
# quebras. Quebrar por linha produziria duas mensagens: uma truncada,
# apresentada como completa, e um fragmento sem contexto.
bruto = (
    "Row: 0 _id=1, address=+5511988887777, date=1755123456789, type=1, read=1, "
    "body=Primeira linha\n"
    "segunda linha da mesma mensagem\n"
    "Row: 1 _id=2, address=+5511977776666, date=1755123999000, type=2, read=1, body=Resposta curta\n"
)
resultado = normalizar_sms(bruto, "sms_todas.txt", BRASILIA)

checar("duas mensagens, nao tres", resultado.total == 2)
checar("nada foi descartado", not resultado.descartes)
checar(
    "a primeira preserva as duas linhas do corpo",
    resultado.registros[0].campos["conteudo"] == "Primeira linha\nsegunda linha da mesma mensagem",
)
checar("a segunda mensagem nao foi contaminada", resultado.registros[1].campos["conteudo"] == "Resposta curta")
checar("a direcao da primeira e Recebida", resultado.registros[0].campos["direcao"] == "Recebida")
checar("e a da segunda, Enviada", resultado.registros[1].campos["direcao"] == "Enviada")

# ---------------------------------------------------------------------------
print("\n[2] Virgula dentro do corpo nao parte o campo")
# ---------------------------------------------------------------------------
bruto = "Row: 0 _id=7, address=+5511900000000, date=1755123456789, type=1, body=Oi, tudo bem, voce vem?, read=0\n"
resultado = normalizar_sms(bruto, "sms.txt", BRASILIA)

checar("uma mensagem", resultado.total == 1)
checar(
    "o corpo com virgulas fica inteiro",
    resultado.registros[0].campos["conteudo"] == "Oi, tudo bem, voce vem?",
)
checar("o campo seguinte foi lido", resultado.registros[0].campos["lida"] == "Não")

# ---------------------------------------------------------------------------
print("\n[3] Epoch em milissegundos e em segundos dao a MESMA data")
# ---------------------------------------------------------------------------
em_ms = normalizar_sms("Row: 0 _id=1, address=x, date=1755123456789, type=1, body=a\n", "a.txt", BRASILIA)
em_s = normalizar_sms("Row: 0 _id=1, address=x, date=1755123456, type=1, body=a\n", "b.txt", BRASILIA)

momento_ms = em_ms.registros[0].momento
momento_s = em_s.registros[0].momento
checar("os dois viram data", momento_ms is not None and momento_s is not None)
checar("e a mesma data", momento_ms.date() == momento_s.date())
checar("nao caiu em 1970", momento_ms.year > 2000)
checar("nem em um futuro absurdo", momento_ms.year < 2100)
checar("o fuso pedido e o aplicado", momento_ms.utcoffset() == timedelta(hours=-3))
checar("e o resultado declara o fuso usado", "-03" in em_ms.fuso_declarado)

# Data zerada e "nao registrado" no Android. Exibi-la como 01/01/1970 seria
# inventar uma data que o aparelho nao tem.
sem_data = normalizar_sms("Row: 0 _id=1, address=x, date=0, type=1, body=a\n", "c.txt", BRASILIA)
checar("date=0 NAO vira 1970", sem_data.registros[0].momento is None)
checar("e o texto diz que nao ha data", "sem data" in sem_data.registros[0].momento_legivel)

# ---------------------------------------------------------------------------
print("\n[4] Recusa do provider nao vira 'nenhuma mensagem'")
# ---------------------------------------------------------------------------
# Trecho real, colhido do CASO_003 em aparelho de teste.
recusa = (
    "Error while accessing provider:call_log\n"
    "java.lang.SecurityException: Permission Denial: opening provider "
    "com.android.providers.contacts.CallLogProvider from (null) (pid=4424, uid=2000) "
    "requires android.permission.READ_CALL_LOG or android.permission.WRITE_CALL_LOG\n"
)
resultado = normalizar_chamadas(recusa, "registro_chamadas_bruto.txt", BRASILIA)

checar("a recusa e reconhecida", resultado.acesso_negado)
checar("nenhum registro e inventado", resultado.total == 0)
checar("e nada vira descarte", not resultado.descartes)
checar(
    "a explicacao do vazio diz que o sistema RECUSOU",
    "RECUSOU" in resultado.explicacao_do_vazio,
)
checar(
    "e adverte que isso nao e ausencia de dado no aparelho",
    "diferente de não existir" in resultado.explicacao_do_vazio,
)
checar("a funcao de deteccao concorda", indica_acesso_negado(recusa))

# Provider que respondeu vazio e outra coisa, e sustenta conclusao diferente.
vazio = normalizar_chamadas("", "chamadas.txt", BRASILIA)
checar("provider vazio NAO e acesso negado", not vazio.acesso_negado)
checar("e a explicacao e outra", "respondeu à consulta" in vazio.explicacao_do_vazio)

# ---------------------------------------------------------------------------
print("\n[5] O que nao foi compreendido aparece contado")
# ---------------------------------------------------------------------------
# O parser foi escrito sem amostra real. Se o formato for outro, isso tem de
# gritar -- e nao devolver "nenhuma mensagem encontrada".
formato_desconhecido = "id|numero|data\n1|+5511|2026-08-23\n"
resultado = normalizar_sms(formato_desconhecido, "sms.txt", BRASILIA)

checar("nada e inventado a partir de formato estranho", resultado.total == 0)
checar("o conteudo nao reconhecido vira descarte", len(resultado.descartes) == 1)
checar("com o motivo dito", "formato" in resultado.descartes[0].motivo)
checar(
    "e a explicacao manda examinar o bruto a mao",
    "examinado à mão" in resultado.explicacao_do_vazio,
)

# Registro sem nenhum campo reconhecivel tambem e contado, nao engolido.
meio_quebrado = "Row: 0 _id=1, address=x, date=1755123456789, type=1, body=ok\nRow: 1 lixo sem igual\n"
resultado = normalizar_sms(meio_quebrado, "sms.txt", BRASILIA)
checar("o registro bom e aproveitado", resultado.total == 1)
checar("e o ruim e contado como descarte", len(resultado.descartes) == 1)

# ---------------------------------------------------------------------------
print("\n[6] A procedencia fica colada em cada registro")
# ---------------------------------------------------------------------------
bruto = (
    "Row: 0 _id=1, address=+5511, date=1755123456789, type=1, body=um\n"
    "Row: 1 _id=2, address=+5522, date=1755123456789, type=2, body=dois\n"
)
resultado = normalizar_sms(bruto, "sms_todas.txt", BRASILIA)
checar("o arquivo de origem acompanha", all(r.arquivo_de_origem == "sms_todas.txt" for r in resultado.registros))
checar("a linha de origem e registrada", [r.linha_de_origem for r in resultado.registros] == [1, 2])
checar("o texto bruto e preservado no registro", "body=um" in resultado.registros[0].bruto)

# ---------------------------------------------------------------------------
print("\n[7] Codigo desconhecido NAO e adivinhado")
# ---------------------------------------------------------------------------
resultado = normalizar_chamadas(
    "Row: 0 _id=1, number=+5511, date=1755123456789, type=99, duration=42\n", "c.txt", BRASILIA
)
checar("o registro entra assim mesmo", resultado.total == 1)
checar(
    "e a direcao declara que o codigo nao foi reconhecido",
    resultado.registros[0].campos["direcao"] == "(código 99 não reconhecido)",
)

conhecidos = normalizar_chamadas(
    "Row: 0 _id=1, number=+5511, date=1755123456789, type=3, duration=0, name=Fulano\n", "c.txt", BRASILIA
)
checar("chamada perdida e reconhecida", conhecidos.registros[0].campos["direcao"] == "Perdida")
checar("o nome da agenda vem junto", conhecidos.registros[0].campos["contato"] == "Fulano")

sem_nome = normalizar_chamadas(
    "Row: 0 _id=1, number=+5511, date=1755123456789, type=1, duration=10, name=NULL\n", "c.txt", BRASILIA
)
checar("NULL vira texto explicito, nao vazio", sem_nome.registros[0].campos["contato"] == "(não consta na agenda)")

# ---------------------------------------------------------------------------
print("\n[8] Contatos nao ganham data que o provider nao tem")
# ---------------------------------------------------------------------------
resultado = normalizar_contatos(
    "Row: 0 _id=5, display_name=Maria Souza, data1=+5511911112222\n", "agenda.txt", BRASILIA
)
checar("um contato", resultado.total == 1)
checar("com nome", resultado.registros[0].campos["contato"] == "Maria Souza")
checar("e numero", resultado.registros[0].campos["numero"] == "+5511911112222")
checar("sem data inventada", resultado.registros[0].momento is None)

# ---------------------------------------------------------------------------
print("\n[9] Nada some antes do primeiro registro")
# ---------------------------------------------------------------------------
# Defeito encontrado na PRIMEIRA validacao contra saida real, num emulador
# Android 13. Tres mensagens injetadas, duas normalizadas, ZERO descartes: a
# terceira sumiu em silencio. Causa: um BOM invisivel no inicio do arquivo
# fez a primeira linha nao casar com "Row:", e o parser pulava tudo ate o
# primeiro registro reconhecido, sem contar nada.
#
# O BOM foi o gatilho, mas o defeito era outro e mais amplo: preambulo
# ignorado em silencio. Um aviso do adb impresso antes da saida produziria
# exatamente o mesmo estrago -- relatorio a menos, sem ninguem perceber.
com_bom = "﻿" + "Row: 0 _id=1, address=+5511, date=1755123456789, type=1, read=1, body=primeira\n"
resultado = normalizar_sms(com_bom, "sms.txt", BRASILIA)
checar("BOM no inicio NAO engole o primeiro registro", resultado.total == 1)
checar("e o conteudo vem intacto", resultado.registros[0].campos["conteudo"] == "primeira")
checar("sem inventar descarte", not resultado.descartes)

com_preambulo = (
    "adb: warning: algo impresso antes da saida\n"
    "Row: 0 _id=1, address=+5511, date=1755123456789, type=1, read=1, body=ok\n"
)
resultado = normalizar_sms(com_preambulo, "sms.txt", BRASILIA)
checar("o registro seguinte ao preambulo e lido", resultado.total == 1)
checar("e o preambulo vira descarte CONTADO", len(resultado.descartes) == 1)
checar(
    "com o motivo dito",
    "antes do primeiro registro" in resultado.descartes[0].motivo,
)
checar("preservando o texto ignorado", "adb: warning" in resultado.descartes[0].texto)

# ---------------------------------------------------------------------------
print("\n[10] Saida REAL de um Android 13, colhida em emulador")
# ---------------------------------------------------------------------------
# Formato exato devolvido por `content query --uri content://sms` num
# emulador AOSP API 33. Ate esta coleta o parser nunca havia sido exercitado
# contra saida real -- os aparelhos de teste negavam acesso ao provider.
REAL = (
    "Row: 0 _id=3, thread_id=3, address=+5511911112222, person=NULL, "
    "date=1787513890891, date_sent=1787513891000, protocol=0, read=0, status=-1, "
    "type=1, reply_path_present=0, subject=NULL, "
    "body=Mensagem com acento: coracao, atencao, ficarao, service_center=NULL, "
    "locked=0, sub_id=1, error_code=-1, creator=com.android.messaging, seen=1\n"
    "Row: 1 _id=2, thread_id=2, address=+5511977776666, person=NULL, "
    "date=1787513890843, date_sent=1787513891000, protocol=0, read=0, status=-1, "
    "type=1, reply_path_present=0, subject=NULL, "
    "body=Segunda mensagem, com virgula, para testar o separador, "
    "service_center=NULL, locked=0, sub_id=1, error_code=-1, "
    "creator=com.android.messaging, seen=1\n"
)
resultado = normalizar_sms(REAL, "sms_todas.txt", BRASILIA)

checar("os dois registros reais sao lidos", resultado.total == 2)
checar("nada e descartado", not resultado.descartes)
checar(
    "o corpo com dois-pontos e virgulas fica inteiro",
    resultado.registros[0].campos["conteudo"] == "Mensagem com acento: coracao, atencao, ficarao",
)
checar(
    "o corpo seguinte tambem, sem invadir o campo posterior",
    resultado.registros[1].campos["conteudo"]
    == "Segunda mensagem, com virgula, para testar o separador",
)
checar("o epoch real de 13 digitos vira 2026", resultado.registros[0].momento.year == 2026)
checar("a direcao e Recebida", resultado.registros[0].campos["direcao"] == "Recebida")
checar("e 'read=0' vira Nao", resultado.registros[0].campos["lida"] == "Não")

# ---------------------------------------------------------------------------
print("\n[11] Armadilhas que so a agenda REAL revelou")
# ---------------------------------------------------------------------------
# Trechos colhidos de content://com.android.contacts/data/phones num Android
# 13. O provider de contatos devolve dezenas de colunas, e tres delas quebram
# parser ingenuo de um jeito que nem SMS nem chamadas revelavam.
AGENDA_REAL = (
    "Row: 0 account_type=local, "
    # (a) valor COM virgula, seguido de outro campo
    "display_name_alt=Santos, Maria Souza dos, sort_key_alt=Santos, Maria Souza dos, "
    "raw_contact_id=1, display_name=Maria Souza dos Santos, _id=1, "
    "data4=+5511911112222, data1=+5511911112222, "
    "mimetype=vnd.android.cursor.item/phone_v2, "
    # (b) valor terminado em '=' (base64) e (c) quebra de linha no meio do registro
    "hash_id=PiHEt1LlWvGEBzCXd/MIS+A36mo=\n"
    ", data15=NULL\n"
)
resultado = normalizar_contatos(AGENDA_REAL, "agenda_contatos_bruta.txt", BRASILIA)

checar("um contato lido", resultado.total == 1)
checar("nada descartado", not resultado.descartes)
checar("o nome vem inteiro", resultado.registros[0].campos["contato"] == "Maria Souza dos Santos")
checar("e o numero", resultado.registros[0].campos["numero"] == "+5511911112222")
checar("contato nao ganha data que o provider nao tem", resultado.registros[0].momento is None)

from core.normalizacao import _blocos, _campos  # noqa: E402

campos = next(_campos(bloco) for _, _, bloco in _blocos(AGENDA_REAL))
checar(
    "(a) valor com virgula nao e partido no meio",
    campos["display_name_alt"] == "Santos, Maria Souza dos",
)
checar(
    "(b) valor terminado em '=' e lido inteiro",
    campos["hash_id"] == "PiHEt1LlWvGEBzCXd/MIS+A36mo=",
)
checar("(c) campo apos a quebra de linha sobrevive", "data15" in campos)

# ---------------------------------------------------------------------------
print("\n[12] Chamadas REAIS: os tres tipos, colhidos em emulador")
# ---------------------------------------------------------------------------
CHAMADAS_REAIS = (
    "Row: 0 duration=2, number=+5511955551111, countryiso=US, "
    "geocoded_location=São Paulo, _id=1, date=1787514147793, name=NULL, type=1\n"
    "Row: 1 duration=0, number=+5511966662222, countryiso=US, "
    "geocoded_location=NULL, _id=2, date=1787514154982, name=NULL, type=3\n"
    "Row: 2 duration=0, number=+5511977773333, countryiso=US, "
    "geocoded_location=NULL, _id=3, date=1787514160194, name=NULL, type=2\n"
)
resultado = normalizar_chamadas(CHAMADAS_REAIS, "registro_chamadas_bruto.txt", BRASILIA)

checar("tres chamadas", resultado.total == 3)
direcoes = [r.campos["direcao"] for r in resultado.registros]
checar("recebida, perdida e efetuada, nesta ordem", direcoes == ["Recebida", "Perdida", "Efetuada"])
checar("a duracao da atendida e 2s", resultado.registros[0].campos["duracao_segundos"] == "2")
checar("a perdida tem duracao zero", resultado.registros[1].campos["duracao_segundos"] == "0")
checar("sem nome na agenda, o texto e explicito", resultado.registros[0].campos["contato"] == "(não consta na agenda)")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
