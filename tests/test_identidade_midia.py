"""
Testes da identificacao da midia na cadeia de custodia.

O registro do CASO_019 -- a primeira aquisicao de armazenamento contra
hardware real -- saiu com `Dispositivo: D:`. O pendrive nao tinha rotulo de
volume, e o identificador "estavel" caia para a letra da unidade, que e a
POSICAO da midia na estacao do examinador, nao a midia: outro pendrive
espetado na mesma porta recebe a mesma letra.

O Windows ja devolvia o numero de serie do volume na mesma chamada que a
suite fazia, e a suite passava `None` no parametro.
"""

import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.computador import disk_client  # noqa: E402
from core.computador.device import ComputadorDevice, descrever_identidade  # noqa: E402
from core.computador.disk_client import (  # noqa: E402
    IdentidadeMidia,
    interpretar_descritor_de_armazenamento,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def descritor(fabricante, produto, revisao, serie, barramento):
    """Monta um STORAGE_DEVICE_DESCRIPTOR como o Windows o devolve."""
    cabecalho = bytearray(36)
    corpo = bytearray()
    for posicao, texto in ((12, fabricante), (16, produto), (20, revisao), (24, serie)):
        if texto is None:
            continue  # deslocamento zero: campo nao declarado
        cabecalho[posicao : posicao + 4] = (36 + len(corpo)).to_bytes(4, "little")
        corpo += texto.encode("ascii") + b"\x00"
    cabecalho[28:32] = barramento.to_bytes(4, "little")
    return bytes(cabecalho + corpo)


# ---------------------------------------------------------------------------
print("\n[1] O descritor da interface e lido campo a campo")
# ---------------------------------------------------------------------------
lido = interpretar_descritor_de_armazenamento(
    descritor("Kingston", "DataTraveler 3.0 ", "PMAP", "E0D55EA574A1F5A0", 7)
)
checar("fabricante", lido.fabricante == "Kingston")
checar("produto, sem o preenchimento de espacos", lido.produto == "DataTraveler 3.0")
checar("numero de serie", lido.numero_serie == "E0D55EA574A1F5A0")
checar("barramento traduzido", lido.barramento == "USB")

sem_serie = interpretar_descritor_de_armazenamento(descritor(None, "Generic Flash", "1.0", None, 7))
checar("campo nao declarado fica VAZIO, sem ler lixo do buffer",
       sem_serie.numero_serie == "" and sem_serie.fabricante == "")
checar("e o que foi declarado continua lido", sem_serie.produto == "Generic Flash")
checar("buffer curto demais nao e interpretado",
       interpretar_descritor_de_armazenamento(b"\x00" * 8).vazia)
checar("barramento desconhecido preserva o codigo, sem adivinhar",
       "99" in interpretar_descritor_de_armazenamento(descritor("a", "b", "c", "d", 99)).barramento)


# ---------------------------------------------------------------------------
print("\n[2] A letra nunca mais e a identidade da midia")
# ---------------------------------------------------------------------------
texto = descrever_identidade(
    IdentidadeMidia("Kingston", "DataTraveler 3.0", "PMAP", "E0D55EA574A1F5A0", "USB", "1A2B-3C4D"),
    "",
    "D:",
)
checar("traz o equipamento", "Kingston DataTraveler 3.0" in texto)
checar("traz o numero de serie da interface", "E0D55EA574A1F5A0" in texto)
checar("traz o numero de serie do volume", "1A2B-3C4D" in texto)
checar("diz que nao ha rotulo, em vez de omitir", "sem rótulo de volume" in texto)
checar("a letra vem rotulada como POSICAO, nao como identidade",
       "posição na estação: D:" in texto and not texto.startswith("D:"))
checar("em USB, a serie carrega a ressalva do adaptador", "adaptador" in texto)

sata = descrever_identidade(
    IdentidadeMidia("", "WDC WD10EZEX", "", "WD-WCC6Y1234567", "SATA", "AAAA-BBBB"), "DADOS", "E:"
)
checar("em SATA direto nao ha ressalva de adaptador", "adaptador" not in sata)
checar("e o rotulo aparece nomeado", "rótulo: DADOS" in sata)

# Nada lido: o pior caso. Nao pode voltar a ser so a letra, calada.
nada = descrever_identidade(IdentidadeMidia(), "", "D:")
checar("sem leitura, cada campo e declarado NAO APURADO",
       nada.count("não apurado") == 3)
checar("e o texto nunca se reduz a letra", nada != "D:")


# ---------------------------------------------------------------------------
print("\n[3] obter_id_unidade usa a identidade, com o que o Windows devolver")
# ---------------------------------------------------------------------------
original = disk_client.identificar_midia
pedidos = []


def identificar_dublado(letra):
    pedidos.append(letra)
    return IdentidadeMidia("SanDisk", "Cruzer", "1.0", "4C530001", "USB", "9F3E-11C2")


disk_client.identificar_midia = identificar_dublado
try:
    identificador = ComputadorDevice().obter_id_unidade("Z:\\")
finally:
    disk_client.identificar_midia = original

checar("a consulta e feita pela letra, sem dois-pontos nem barra", pedidos == ["Z"])
checar("o identificador traz a serie", "4C530001" in identificador)
checar("e a serie do volume", "9F3E-11C2" in identificador)
checar("cabe em UMA linha do registro (chave: valor)", "\n" not in identificador)

if disk_client.rodando_no_windows():
    real = disk_client.obter_serie_do_volume("C:\\")
    checar("contra a propria estacao: a serie do volume de C: tem o formato XXXX-XXXX",
           len(real) == 9 and real[4] == "-")


print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
