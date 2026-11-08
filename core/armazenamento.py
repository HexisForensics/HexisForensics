"""
Verificação de espaço na estação forense antes de uma aquisição.

Por que isso é requisito, e não conveniência: uma imagem física de 64 GB ou
o dump de um `/sdcard` cheio numa estação com pouco espaço falha **no meio**
da cópia. O resultado é uma aquisição truncada — e, sem esta checagem, ela
chega ao exame como "cópia incompleta" sem dizer que a causa foi disco
cheio na estação, e não recusa ou ausência de dado no aparelho.

Atribuir ao aparelho examinado uma limitação que era da estação é o tipo de
erro que compromete a conclusão pericial.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, Tuple

# Folga sobre o tamanho estimado da origem. Cobre metadados de sistema de
# arquivos, arredondamento do `du` e o próprio manifesto de hashes.
MARGEM_PADRAO = 1.15


def formatar_bytes(quantidade: int) -> str:
    """Formata um tamanho em bytes de forma legível no relatório."""
    valor = float(quantidade)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if abs(valor) < 1024 or unidade == "TB":
            return f"{valor:.1f} {unidade}" if unidade != "B" else f"{int(valor)} B"
        valor /= 1024
    return f"{valor:.1f} TB"


def espaco_livre(caminho: Path) -> Optional[int]:
    """
    Bytes livres no volume onde `caminho` está (ou estará).

    Sobe até o primeiro diretório existente, já que a pasta do caso pode
    ainda não ter sido criada quando a checagem é feita.
    """
    alvo = Path(caminho).resolve()
    while not alvo.exists() and alvo.parent != alvo:
        alvo = alvo.parent

    try:
        return shutil.disk_usage(alvo).free
    except OSError:
        return None


def verificar_espaco(
    destino: Path, bytes_necessarios: Optional[int], margem: float = MARGEM_PADRAO
) -> Tuple[bool, str]:
    """
    Confere se há espaço para a aquisição.

    Devolve `(True, "")` quando há espaço **ou quando não foi possível
    estimar** — a checagem nunca impede uma aquisição por falta de
    informação, apenas por falta comprovada de espaço. Impedir uma coleta
    com base em estimativa ausente seria pior do que não checar.
    """
    if not bytes_necessarios:
        return True, ""

    livre = espaco_livre(destino)
    if livre is None:
        return True, ""

    exigido = int(bytes_necessarios * margem)
    if livre >= exigido:
        return True, ""

    return False, (
        f"Espaço insuficiente na estação forense: a origem ocupa "
        f"{formatar_bytes(bytes_necessarios)} (com folga, {formatar_bytes(exigido)}), "
        f"e há apenas {formatar_bytes(livre)} livres em '{Path(destino).anchor or destino}'. "
        "A aquisição NÃO foi iniciada, para não produzir cópia truncada. "
        "Libere espaço ou aponte a pasta de extrações para outro volume."
    )
