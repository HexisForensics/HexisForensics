"""
Excluir um caso — com as cautelas de uma ferramenta forense.

- Confirmação digitando o nome do caso: não se apaga caso por um clique.
- O caso vai para a LIXEIRA do Windows, não é apagado de vez: um engano
  se desfaz restaurando. Apagar definitivamente é ato do Windows (esvaziar
  a Lixeira), fora da suíte.
- Caso com aquisição ainda aberta (sem lacre) não é excluído: pode haver
  extração em andamento gravando nele.
- A exclusão vai para o registro de acessos: quem, quando, qual caso.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Optional

from services import sessao_service
from services.case_service import CaseService


class ErroDeExclusao(Exception):
    """Exclusão recusada. A mensagem é para quem a pediu."""


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040  # é isto que manda para a Lixeira, em vez de apagar
FOF_NOERRORUI = 0x0400


def enviar_para_lixeira(caminho: Path) -> None:
    """Manda a pasta para a Lixeira do Windows. Levanta `ErroDeExclusao` se não conseguir."""
    if sys.platform != "win32":
        raise ErroDeExclusao("Envio à Lixeira disponível só no Windows.")
    operacao = _SHFILEOPSTRUCTW()
    operacao.wFunc = FO_DELETE
    operacao.pFrom = str(Path(caminho).resolve()) + "\0"  # lista terminada em dois nulos
    operacao.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    codigo = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operacao))
    if codigo != 0 or operacao.fAnyOperationsAborted or Path(caminho).exists():
        raise ErroDeExclusao(
            f"O Windows não enviou o caso à Lixeira (código {codigo}). Nada foi apagado "
            "definitivamente; verifique se algum arquivo do caso está aberto."
        )


def excluir_caso(
    pasta_caso: Path,
    confirmacao: str,
    lixeira: Callable[[Path], None] = enviar_para_lixeira,
    casos: Optional[CaseService] = None,
) -> None:
    pasta_caso = Path(pasta_caso)
    if confirmacao.strip() != pasta_caso.name:
        raise ErroDeExclusao(
            f"Confirmação não confere: para excluir, digite exatamente {pasta_caso.name}.")
    if not pasta_caso.is_dir():
        raise ErroDeExclusao("O caso não foi encontrado.")
    servico = casos or CaseService(pasta_caso.parent)
    abertas = [a.pasta.name for a in servico.resumo_do_caso(pasta_caso).aquisicoes if not a.selada]
    if abertas:
        raise ErroDeExclusao(
            "O caso tem aquisição ainda sem lacre (" + ", ".join(abertas) + "): pode haver "
            "extração em andamento. Aguarde o fim dela antes de excluir.")
    lixeira(pasta_caso)
    sessao_service.registrar_evento(
        "CASO EXCLUÍDO", f"{pasta_caso.name} — enviado à Lixeira do Windows ({pasta_caso})")
