"""
Locais das fotos: coordenadas de GPS lidas do EXIF das imagens da aquisição.

Conferido também contra as fotos reais do moto x4 (CASO_001): 8 imagens, 3
com coordenadas, e a hora do GPS (19:12 UTC) batendo com a do relógio do
aparelho (16:12, fuso -03). Aqui, imagens sintéticas cobrem os casos que um
aparelho de teste não produz.
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.geolocalizacao import ler_dados_da_foto  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from services.relatorio_service import RelatorioService  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


# ---------------------------------------------------------------------------
# Montagem de EXIF sintético (TIFF little-endian)
# ---------------------------------------------------------------------------
def _ifd(entradas, inicio):
    n = len(entradas)
    area = inicio + 2 + 12 * n + 4
    corpo, dados = b"", b""
    for tag, tipo, contagem, valor in entradas:
        if len(valor) <= 4:
            campo = valor.ljust(4, b"\x00")
        else:
            campo = struct.pack("<I", area + len(dados))
            dados += valor + (b"\x00" if len(valor) % 2 else b"")
        corpo += struct.pack("<HHI", tag, tipo, contagem) + campo
    return struct.pack("<H", n) + corpo + struct.pack("<I", 0) + dados


def _racionais(*pares):
    return b"".join(struct.pack("<II", n, d) for n, d in pares)


def _graus(valor):
    valor = abs(valor)
    graus = int(valor)
    minutos = int((valor - graus) * 60)
    segundos = round(((valor - graus) * 60 - minutos) * 60 * 100)
    return _racionais((graus, 1), (minutos, 1), (segundos, 100))


def tiff(latitude=None, longitude=None, data=b"2026:10:12 16:12:28\x00", camera=b"motorola\x00",
         hora_gps=(19, 12, 26), dia_gps=b"2026:10:12\x00"):
    gps = []
    if latitude is not None:
        gps = [
            (1, 2, 2, b"S\x00" if latitude < 0 else b"N\x00"),
            (2, 5, 3, _graus(latitude)),
            (3, 2, 2, b"W\x00" if longitude < 0 else b"E\x00"),
            (4, 5, 3, _graus(longitude)),
            (5, 1, 1, b"\x00"),
            (6, 5, 1, _racionais((760, 1))),
            (7, 5, 3, _racionais(*[(v, 1) for v in hora_gps])),
            (29, 2, len(dia_gps), dia_gps),
        ]
    exif = [(0x9003, 2, len(data), data)]

    def montar(ponteiro_gps, ponteiro_exif):
        entradas = [(0x010F, 2, len(camera), camera),
                    (0x8769, 4, 1, struct.pack("<I", ponteiro_exif))]
        if gps:
            entradas.append((0x8825, 4, 1, struct.pack("<I", ponteiro_gps)))
        return _ifd(sorted(entradas), 8)

    tamanho0 = len(montar(0, 0))
    bloco_gps = _ifd(gps, 8 + tamanho0) if gps else b""
    inicio_exif = 8 + tamanho0 + len(bloco_gps)
    return (b"II*\x00" + struct.pack("<I", 8) + montar(8 + tamanho0, inicio_exif)
            + bloco_gps + _ifd(exif, inicio_exif))


def jpeg(bloco):
    carga = b"Exif\x00\x00" + bloco
    return b"\xff\xd8\xff\xe1" + struct.pack(">H", len(carga) + 2) + carga + b"\xff\xd9"


def heic(bloco):
    return b"\x00\x00\x00\x18ftypheic" + b"\x00" * 40 + b"\x00\x00\x00\x06Exif\x00\x00" + bloco


SAO_PAULO = (-23.550520, -46.633308)

print("\n[1] Leitura do EXIF")
with tempfile.TemporaryDirectory() as temporario:
    pasta = Path(temporario)
    (pasta / "a.jpg").write_bytes(jpeg(tiff(*SAO_PAULO)))
    dados = ler_dados_da_foto(pasta / "a.jpg")
    checar("JPEG: latitude e longitude com sinal (sul e oeste negativos)",
           abs(dados.latitude - SAO_PAULO[0]) < 1e-4 and abs(dados.longitude - SAO_PAULO[1]) < 1e-4)
    checar("data do relógio do aparelho, sem fuso inventado",
           str(dados.momento) == "2026-10-12 16:12:28")
    checar("hora do GPS em UTC", str(dados.hora_gps_utc) == "2026-10-12 19:12:26+00:00")
    checar("altitude e câmera", dados.altitude == 760 and dados.camera == "motorola")
    checar("link para o mapa", "maps?q=-23.5505" in dados.link_do_mapa and ",-46.6333" in dados.link_do_mapa)

    (pasta / "b.heic").write_bytes(heic(tiff(*SAO_PAULO)))
    checar("HEIC do iPhone: mesmo leitor",
           abs(ler_dados_da_foto(pasta / "b.heic").latitude - SAO_PAULO[0]) < 1e-4)

    (pasta / "c.jpg").write_bytes(jpeg(tiff()))
    sem = ler_dados_da_foto(pasta / "c.jpg")
    checar("foto sem GPS: sem localização e sem problema", sem.latitude is None and not sem.problema)

    (pasta / "d.jpg").write_bytes(jpeg(tiff(0.0, 0.0)))
    checar("coordenada 0,0 não vira local (GPS sem sinal)",
           ler_dados_da_foto(pasta / "d.jpg").problema.startswith("coordenada 0,0"))

    (pasta / "e.jpg").write_bytes(b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00II*\x00\xff\xff\xff\x7f\xff\xd9")
    quebrado = ler_dados_da_foto(pasta / "e.jpg")
    checar("EXIF malformado não derruba a leitura", quebrado.latitude is None)

print("\n[2] No Relatório de Conteúdo")
with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "android_20261030_184233"
    camera = aquisicao / "media" / "Camera" / "DCIM"
    camera.mkdir(parents=True)
    foto = jpeg(tiff(*SAO_PAULO))
    (camera / "IMG_1.jpg").write_bytes(foto)
    copia = aquisicao / "filesystem" / "DCIM"
    copia.mkdir(parents=True)
    (copia / "IMG_1.jpg").write_bytes(foto)  # a mesma foto pelo dump
    (camera / "IMG_2.jpg").write_bytes(jpeg(tiff()))
    (camera / "IMG_3.jpg").write_bytes(jpeg(tiff(0.0, 0.0)))
    fotos_da_peca = aquisicao / "evidencias_fotos"
    fotos_da_peca.mkdir()
    (fotos_da_peca / "frente.jpg").write_bytes(jpeg(tiff(-22.9, -43.2)))
    gerar_manifesto(aquisicao, log_callback=lambda _m: None)
    (camera / "IMG_4.jpg").write_bytes(jpeg(tiff(-15.8, -47.9)))  # entrou depois do lacre

    artefato = RelatorioService._levantar_locais(
        aquisicao, RelatorioService._hashes_do_manifesto(aquisicao))
    checar("a foto com GPS entra uma vez, mesmo copiada duas", artefato.total == 1)
    checar("as fotos que o EXAMINADOR tirou da peça não entram",
           all("evidencias_fotos" not in r.arquivo_de_origem for r in artefato.resultado.registros)
           and all("evidencias_fotos" not in d.texto for d in artefato.resultado.descartes))
    motivos = " ".join(d.motivo for d in artefato.resultado.descartes)
    checar("imagem fora do lacre não é interpretada, e é dita", "fora do lacre" in motivos)
    checar("GPS sem sinal vira descarte com motivo", "0,0" in motivos)
    checar("a nota conta tudo e diz o que a coordenada significa",
           "5 imagem(ns) examinada(s)" in artefato.nota_da_fonte
           and "1 cópia(s) idêntica(s)" in artefato.nota_da_fonte
           and "editável" in artefato.nota_da_fonte)

with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "android_20261030_184233"
    (aquisicao / "sms").mkdir(parents=True)
    artefato = RelatorioService._levantar_locais(aquisicao, {})
    checar("sem imagens: diz que o módulo de mídias pode não ter rodado",
           artefato.total == 0 and "não é prova" in artefato.explicacao)

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
