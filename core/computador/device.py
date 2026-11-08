"""
Representação da "unidade de disco alvo" (equivalente ao dispositivo
Android/iOS, mas aqui é uma letra de unidade do Windows, não um aparelho
conectado via cabo). Não existe "conexão/autorização" como no ADB — existe
"escolher qual unidade periciar" entre as detectadas pelo Windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import disk_client
from .disk_client import UnidadeDisco


@dataclass
class StatusUnidade:
    disponivel: bool
    unidade: Optional[UnidadeDisco]
    mensagem: str


class ComputadorDevice:
    """
    Fachada sobre `disk_client`, no mesmo espírito de `AndroidDevice`: a
    camada de cima (services/ui) não precisa saber que por baixo é
    `ctypes` chamando a API do Windows.
    """

    def listar_unidades(self, apenas_removiveis: bool = False) -> List[UnidadeDisco]:
        return disk_client.listar_unidades(apenas_removiveis=apenas_removiveis)

    def verificar_unidade(
        self, caminho_unidade: str, apenas_removiveis: bool = False
    ) -> StatusUnidade:
        """
        Confirma que `caminho_unidade` (ex.: 'E:\\\\') ainda está entre as
        unidades detectadas — chamado logo antes de iniciar uma extração,
        já que o examinador pode ter escolhido a unidade minutos antes e o
        pendrive pode ter sido removido nesse meio tempo.
        """
        if not disk_client.rodando_no_windows():
            return StatusUnidade(
                False,
                None,
                "Este módulo funciona apenas no Windows — nenhuma unidade pode ser verificada neste sistema.",
            )

        for unidade in self.listar_unidades(apenas_removiveis=apenas_removiveis):
            if unidade.caminho.upper() == caminho_unidade.upper():
                return StatusUnidade(
                    True, unidade, f"Unidade '{unidade.caminho}' disponível."
                )

        return StatusUnidade(
            False,
            None,
            f"A unidade '{caminho_unidade}' não foi encontrada. Ela pode ter sido "
            "removida/desconectada — atualize a lista e selecione novamente.",
        )

    def obter_id_unidade(self, caminho_unidade: str) -> str:
        """
        Identificação da mídia para a cadeia de custódia.

        Era o rótulo do volume, e na falta dele a letra da unidade — e a
        letra é a posição da mídia na estação do examinador, não a mídia. O
        registro de um caso real saiu com `Dispositivo: D:`.

        Hoje reúne o que a interface de armazenamento declara (fabricante,
        produto, número de série), o número de série do volume, o rótulo e
        a letra, cada um NOMEADO pelo que é. O que não pôde ser lido é dito
        como não apurado; a letra vem por último e rotulada como posição na
        estação, para não ser lida como identidade.
        """
        letra = caminho_unidade.rstrip("\\")
        status = self.verificar_unidade(caminho_unidade)
        rotulo = status.unidade.rotulo if status.unidade else ""
        identidade = disk_client.identificar_midia(letra.rstrip(":"))
        return descrever_identidade(identidade, rotulo, letra)


def descrever_identidade(identidade, rotulo: str, letra: str) -> str:
    """Texto único de identificação da mídia, para o registro do caso."""
    equipamento = " ".join(
        parte for parte in (identidade.fabricante, identidade.produto) if parte
    )
    partes = [equipamento or "equipamento não apurado"]

    if identidade.numero_serie:
        serie = f"n/s declarado pela interface {identidade.barramento}: {identidade.numero_serie}"
        if identidade.barramento == disk_client.BARRAMENTO_USB:
            # Em dock ou adaptador USB quem responde pode ser a ponte. A
            # ferramenta não tem como distinguir, então não afirma.
            serie += " (em adaptador ou dock, pode ser o do adaptador — conferir com a etiqueta)"
        partes.append(serie)
    else:
        partes.append("n/s da interface não apurado")

    partes.append(
        f"n/s do volume: {identidade.serie_do_volume}"
        if identidade.serie_do_volume
        else "n/s do volume não apurado"
    )
    partes.append(f"rótulo: {rotulo}" if rotulo else "sem rótulo de volume")
    partes.append(f"posição na estação: {letra}")
    return " | ".join(partes)
