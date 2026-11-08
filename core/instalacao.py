"""
Onde a suíte está instalada — a única fonte dessa resposta.

Quatro lugares calculavam a raiz do programa contando `parents` a partir de
`__file__`: o destino das extrações, a pasta do ADB, a dos perfis de marca
e a proteção contra a suíte copiar a si mesma. Rodando do código-fonte os
quatro acertam. Empacotada em executável, `__file__` aponta para dentro da
pasta interna do empacotador, e cada um erraria do seu jeito — o pior
deles gravando as extrações num lugar que não é o que o examinador vê.

Congelada, a referência que vale é a pasta do executável. É ao lado dele
que ficam `binario/`, `branding/` e `assets/`.

As EXTRAÇÕES têm resposta própria (`pasta_das_extracoes`). Rodando do
código-fonte ou da pasta portátil, ficam ao lado do programa — a pasta
portátil anda inteira, casos junto. INSTALADA pelo instalador, ficam fora
da pasta do programa: evidência não mora em pasta de aplicativo, que a
atualização substitui e a desinstalação remove.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Arquivo que o instalador grava na raiz. É a presença dele, e não um
# palpite sobre o caminho, que diz "esta cópia foi instalada".
MARCA_DE_INSTALACAO = "instalada.txt"


def empacotada() -> bool:
    """`True` quando a suíte roda como executável, e não do código-fonte."""
    return bool(getattr(sys, "frozen", False))


def raiz_da_instalacao() -> Path:
    """
    Pasta onde a suíte está instalada agora, descoberta a cada chamada.
    Uma instalação movida continua sendo encontrada.
    """
    if empacotada():
        return Path(sys.executable).resolve().parent
    # Este arquivo vive em <raiz>/core/instalacao.py.
    return Path(__file__).resolve().parents[1]


def modo_desenvolvimento() -> bool:
    """
    `True` só para quem roda o CÓDIGO-FONTE de um clone do repositório.

    O instalador gera executável (`empacotada`) e a pasta portátil não
    leva o `.git`: nas duas, isto é falso. É o que mantém a conta de testes
    (Forensic Admin) fora de toda estação de usuário.
    """
    return not empacotada() and (raiz_da_instalacao() / ".git").exists()


def instalada() -> bool:
    """`True` quando esta cópia foi posta na máquina pelo instalador."""
    return (raiz_da_instalacao() / MARCA_DE_INSTALACAO).is_file()


def pasta_das_extracoes() -> Path:
    """
    Onde os casos são gravados.

    Instalada: `<perfil do usuário>/HexisForensics-Casos`. Fica na
    raiz do perfil, e não em "Documentos", de propósito: em muitas máquinas
    "Documentos" é sincronizado com a nuvem, e um serviço de sincronização
    mexendo em pasta de evidência (ou trocando arquivo por atalho de nuvem)
    é exatamente o que uma aquisição não pode sofrer.
    """
    if instalada():
        perfil = Path(os.environ.get("USERPROFILE") or str(Path.home()))
        # Nome anterior da suíte (Forensic Extractor, até 01/11/2026): os
        # casos já gravados continuam onde estão, sem cópia nem movimento.
        anterior = perfil / "ForensicExtractor-Casos"
        atual = perfil / "HexisForensics-Casos"
        return anterior if anterior.is_dir() and _vazia_ou_ausente(atual) else atual
    return raiz_da_instalacao() / "extracoes"


def _vazia_ou_ausente(pasta: Path) -> bool:
    """A pasta com o nome novo ainda não tem nada (o instalador a cria vazia)."""
    return not pasta.is_dir() or not any(pasta.iterdir())
