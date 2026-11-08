"""
Registro dos erros inesperados da suíte, num arquivo da estação.

Na versão instalada não há console: um erro que escapasse do código sumia
sem rastro, e o defeito só podia ser investigado por hipótese (primeira
instalação em campo, 04/11/2026). Agora cada erro inesperado vai para
`erros.log`, na pasta de dados da estação (a mesma dos perfis), com a data,
a versão e o rastro completo, e o examinador é avisado de onde está o
arquivo para mandá-lo a quem dá suporte.

O arquivo nunca fica dentro de uma aquisição: é da estação, não do caso.
"""

from __future__ import annotations

import faulthandler
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.versao import VERSAO
from services.perfil_service import local_do_perfil

NOME_ARQUIVO = "erros.log"

# Mantido aberto enquanto a suíte roda: o faulthandler escreve nele se o
# próprio interpretador cair (falha que nem chega a virar exceção).
_arquivo_de_falhas = None
_avisando = False


def caminho() -> Path:
    return Path(local_do_perfil()) / NOME_ARQUIVO


def registrar(tipo, valor, rastro) -> Optional[Path]:
    """Acrescenta o erro ao arquivo. Devolve o caminho, ou None se não gravou."""
    destino = caminho()
    texto = (
        f"\n===== {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} · "
        f"Hexis Forensics {VERSAO} · {platform.platform()} =====\n"
        + "".join(traceback.format_exception(tipo, valor, rastro))
    )
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as arquivo:
            arquivo.write(texto)
    except OSError:
        return None
    return destino


def instalar(avisar: Optional[Callable[[Optional[Path], str], None]] = None) -> None:
    """
    Passa a registrar todo erro inesperado.

    `avisar(caminho, resumo)` é chamado depois de gravar, para a interface
    mostrar a mensagem ao examinador. Um erro dentro do próprio aviso não
    gera outro aviso (o que travaria a tela em cascata).
    """
    global _arquivo_de_falhas

    def ao_ocorrer_erro(tipo, valor, rastro):
        global _avisando
        destino = registrar(tipo, valor, rastro)
        sys.__excepthook__(tipo, valor, rastro)
        if avisar is None or _avisando:
            return
        _avisando = True
        try:
            avisar(destino, f"{tipo.__name__}: {valor}")
        except Exception:  # noqa: BLE001 - o aviso nunca pode derrubar a suíte
            pass
        finally:
            _avisando = False

    sys.excepthook = ao_ocorrer_erro
    try:
        caminho().parent.mkdir(parents=True, exist_ok=True)
        _arquivo_de_falhas = caminho().open("a", encoding="utf-8")
        faulthandler.enable(file=_arquivo_de_falhas)
    except OSError:
        pass


def desinstalar() -> None:
    """Volta ao comportamento padrão e fecha o arquivo (usado nos testes)."""
    global _arquivo_de_falhas
    sys.excepthook = sys.__excepthook__
    if _arquivo_de_falhas is not None:
        faulthandler.disable()
        _arquivo_de_falhas.close()
        _arquivo_de_falhas = None
