"""
Locais das fotos: as coordenadas de GPS gravadas dentro de cada imagem (EXIF).

As fotos já vêm na aquisição (backup lógico do Android, backup do iPhone);
aqui só se LÊ o que a câmera gravou nelas. Nada toca no aparelho.

O que uma coordenada destas diz, e o que não diz — vai junto com ela:
- é onde a FOTO foi tirada, segundo o GPS do aparelho que a tirou (que pode
  nem ser o aparelho examinado: foto recebida também tem EXIF);
- o EXIF é editável; a coordenada é o que está gravado, não prova de que o
  aparelho esteve ali;
- a data da foto vem do RELÓGIO do aparelho que a tirou (ver
  `core.relogio`); a hora do GPS, quando gravada, vem dos satélites, em UTC,
  e não depende desse relógio.

Leitura sem biblioteca externa: o bloco EXIF é um TIFF, e o mesmo leitor
serve ao JPEG (segmento APP1) e ao HEIC do iPhone (item "Exif").
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

EXTENSOES_DE_IMAGEM = {".jpg", ".jpeg", ".heic", ".heif", ".dng"}

# O EXIF de um HEIC pode estar depois dos metadados do contêiner; nos
# arquivos do iPhone fica no começo. Lê-se até aqui, sem carregar a foto.
LIMITE_DE_LEITURA = 4 * 1024 * 1024

_TAMANHO_DO_TIPO = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


@dataclass
class DadosDaFoto:
    """O que o EXIF de uma imagem diz sobre onde e quando ela foi feita."""

    tem_exif: bool = False
    tem_gps: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    data_original: str = ""        # "AAAA:MM:DD HH:MM:SS", relógio do aparelho
    deslocamento: str = ""         # "-03:00", quando a câmera gravou
    hora_gps_utc: Optional[datetime] = None
    camera: str = ""
    problema: str = ""             # GPS presente mas inaproveitável: o porquê

    @property
    def momento(self) -> Optional[datetime]:
        """A data da foto; com fuso só se a câmera o gravou — nunca suposto."""
        if not self.data_original:
            return None
        try:
            momento = datetime.strptime(self.data_original.strip("\x00 "), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return None
        if self.deslocamento:
            try:
                sinal = -1 if self.deslocamento.startswith("-") else 1
                horas, minutos = self.deslocamento.lstrip("+-").split(":")
                fuso = timezone(sinal * timedelta(hours=int(horas), minutes=int(minutos)))
                momento = momento.replace(tzinfo=fuso)
            except (ValueError, IndexError):
                pass
        return momento

    @property
    def link_do_mapa(self) -> str:
        if self.latitude is None or self.longitude is None:
            return ""
        return f"https://www.google.com/maps?q={self.latitude:.6f},{self.longitude:.6f}"


# ---------------------------------------------------------------------------
# Localizar o bloco TIFF
# ---------------------------------------------------------------------------
def _tiff_do_jpeg(dados: bytes) -> Optional[bytes]:
    if not dados.startswith(b"\xff\xd8"):
        return None
    posicao = 2
    while posicao + 4 <= len(dados):
        if dados[posicao] != 0xFF:
            return None
        marcador = dados[posicao + 1]
        if marcador in (0xD9, 0xDA):  # fim da imagem / início dos dados
            return None
        tamanho = struct.unpack(">H", dados[posicao + 2:posicao + 4])[0]
        segmento = dados[posicao + 4:posicao + 2 + tamanho]
        if marcador == 0xE1 and segmento.startswith(b"Exif\x00\x00"):
            return segmento[6:]
        posicao += 2 + tamanho
    return None


def _tiff_por_busca(dados: bytes) -> Optional[bytes]:
    """HEIC e outros contêineres: o item Exif traz 'Exif\\0\\0' antes do TIFF."""
    inicio = 0
    while True:
        achado = dados.find(b"Exif\x00\x00", inicio)
        if achado == -1:
            return None
        tiff = dados[achado + 6:]
        if tiff[:4] in (b"II*\x00", b"MM\x00*"):
            return tiff
        inicio = achado + 1


# ---------------------------------------------------------------------------
# Ler o TIFF
# ---------------------------------------------------------------------------
class _Tiff:
    def __init__(self, dados: bytes):
        self.dados = dados
        self.ordem = "<" if dados[:2] == b"II" else ">"

    def _u(self, formato: str, posicao: int):
        return struct.unpack(self.ordem + formato, self.dados[posicao:posicao + struct.calcsize(formato)])[0]

    def ifd(self, posicao: int) -> dict:
        """`{tag: (tipo, quantidade, posição do valor)}`."""
        entradas = {}
        if posicao <= 0 or posicao + 2 > len(self.dados):
            return entradas
        quantidade = self._u("H", posicao)
        for indice in range(quantidade):
            base = posicao + 2 + indice * 12
            if base + 12 > len(self.dados):
                break
            tag = self._u("H", base)
            tipo = self._u("H", base + 2)
            contagem = self._u("I", base + 4)
            tamanho = _TAMANHO_DO_TIPO.get(tipo, 1) * contagem
            local = base + 8 if tamanho <= 4 else self._u("I", base + 8)
            entradas[tag] = (tipo, contagem, local)
        return entradas

    def valor(self, entrada):
        tipo, contagem, local = entrada
        if local + _TAMANHO_DO_TIPO.get(tipo, 1) * contagem > len(self.dados):
            raise ValueError("valor fora do bloco EXIF")
        if tipo == 2:
            return self.dados[local:local + contagem].split(b"\x00", 1)[0].decode("ascii", "replace")
        if tipo in (1, 7):
            return self.dados[local:local + contagem]
        if tipo == 3:
            return [self._u("H", local + 2 * i) for i in range(contagem)]
        if tipo == 4:
            return [self._u("I", local + 4 * i) for i in range(contagem)]
        if tipo in (5, 10):
            formato = "I" if tipo == 5 else "i"
            valores = []
            for i in range(contagem):
                numerador = self._u(formato, local + 8 * i)
                denominador = self._u(formato, local + 8 * i + 4)
                if denominador == 0:
                    raise ValueError("fração com denominador zero")
                valores.append(numerador / denominador)
            return valores
        raise ValueError(f"tipo EXIF {tipo} não lido")


def _graus(valores, referencia: str) -> float:
    graus = valores[0] + valores[1] / 60 + valores[2] / 3600
    return -graus if referencia.upper() in ("S", "W") else graus


def ler_dados_da_foto(caminho: Path) -> DadosDaFoto:
    """Lê o EXIF de uma imagem. Nunca levanta: o problema vem escrito."""
    dados_da_foto = DadosDaFoto()
    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read(LIMITE_DE_LEITURA)
    except OSError as erro:
        dados_da_foto.problema = f"arquivo ilegível ({erro})"
        return dados_da_foto

    tiff = _tiff_do_jpeg(dados) or _tiff_por_busca(dados)
    if not tiff or tiff[:4] not in (b"II*\x00", b"MM\x00*"):
        return dados_da_foto
    dados_da_foto.tem_exif = True

    try:
        leitor = _Tiff(tiff)
        ifd0 = leitor.ifd(leitor._u("I", 4))
        fabricante = leitor.valor(ifd0[0x010F]) if 0x010F in ifd0 else ""
        modelo = leitor.valor(ifd0[0x0110]) if 0x0110 in ifd0 else ""
        dados_da_foto.camera = " ".join(p for p in (fabricante.strip(), modelo.strip()) if p)
        if 0x8769 in ifd0:
            exif = leitor.ifd(leitor.valor(ifd0[0x8769])[0])
            if 0x9003 in exif:
                dados_da_foto.data_original = leitor.valor(exif[0x9003])
            if 0x9011 in exif:
                dados_da_foto.deslocamento = leitor.valor(exif[0x9011]).strip()
        if 0x8825 not in ifd0:
            return dados_da_foto
        gps = leitor.ifd(leitor.valor(ifd0[0x8825])[0])
    except (KeyError, IndexError, ValueError, struct.error) as erro:
        dados_da_foto.problema = f"EXIF malformado ({erro})"
        return dados_da_foto

    if not (2 in gps and 4 in gps):
        return dados_da_foto  # bloco de GPS sem coordenada: sem localização
    dados_da_foto.tem_gps = True
    try:
        referencia_lat = leitor.valor(gps[1]) if 1 in gps else "N"
        referencia_lon = leitor.valor(gps[3]) if 3 in gps else "E"
        latitude = _graus(leitor.valor(gps[2]), referencia_lat)
        longitude = _graus(leitor.valor(gps[4]), referencia_lon)
        if 6 in gps:
            altitude = leitor.valor(gps[6])[0]
            abaixo = 5 in gps and leitor.valor(gps[5])[:1] == b"\x01"
            dados_da_foto.altitude = -altitude if abaixo else altitude
        if 7 in gps and 29 in gps:
            h, m, s = leitor.valor(gps[7])
            dia = datetime.strptime(leitor.valor(gps[29]), "%Y:%m:%d")
            dados_da_foto.hora_gps_utc = (dia + timedelta(hours=h, minutes=m, seconds=s)).replace(
                tzinfo=timezone.utc)
    except (IndexError, ValueError, struct.error) as erro:
        dados_da_foto.problema = f"coordenada de GPS malformada ({erro})"
        return dados_da_foto

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        dados_da_foto.problema = f"coordenada fora do globo ({latitude}, {longitude})"
        return dados_da_foto
    if latitude == 0 and longitude == 0:
        dados_da_foto.problema = (
            "coordenada 0,0 — típica de câmera que gravou o campo sem ter sinal de GPS")
        return dados_da_foto
    dados_da_foto.latitude, dados_da_foto.longitude = latitude, longitude
    return dados_da_foto
