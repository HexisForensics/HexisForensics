"""
Versão da suíte e identificação do ambiente de execução.

Por que isso é uma exigência, e não um detalhe de engenharia: a ISO/IEC
27037 impõe **repetibilidade** (mesmas condições, mesmo resultado) e
**reprodutibilidade** (outro examinador chega ao mesmo resultado). Nenhuma
das duas é verificável se não se sabe qual versão da ferramenta, de que
ambiente e com qual ADB a aquisição foi feita. Sem esse carimbo, uma
divergência entre dois exames do mesmo aparelho é indecidível.
"""

from __future__ import annotations

import platform
import sys

VERSAO = "1.0.0"
NOME_FERRAMENTA = "HexisForensics"


def identificacao_ferramenta() -> str:
    """Nome e versão da suíte, como devem aparecer no registro do caso."""
    return f"{NOME_FERRAMENTA} {VERSAO}"


def descrever_ambiente() -> dict:
    """
    Ambiente da estação forense no momento da aquisição.

    Coletado na abertura do caso e gravado junto do resultado — é o que
    permite a um terceiro reproduzir as condições do exame.
    """
    # Import local: `instalacao` não importa `versao`, mas manter a referência
    # aqui dentro deixa claro que é só para carimbar a origem no ambiente.
    from core.instalacao import empacotada
    return {
        "ferramenta": identificacao_ferramenta(),
        # Instalador (executável empacotado) ou código-fonte (py main.py). A
        # defesa pode perguntar como a estação rodou; o carimbo responde.
        "origem": "instalador" if empacotada() else "código-fonte",
        "python": sys.version.split()[0],
        "sistema": f"{platform.system()} {platform.release()}",
        "arquitetura": platform.machine(),
        "estacao": platform.node(),
    }
