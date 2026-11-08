"""
Registro em arquivo das operações de extração, para reforçar a cadeia de
custódia (todo módulo executado, sucesso/falha e horário ficam persistidos
dentro da própria pasta do caso, além de aparecerem no console da GUI).

Dois loggers são gerados por caso:
    - `extracao.log` (raiz da pasta do caso): tudo — todo módulo, toda
      linha de progresso, sucesso ou falha.
    - `erros/erros.log` (subpasta dedicada): só os módulos que falharam ou
      tiveram alguma ressalva (ex.: acesso negado a um provider), com os
      detalhes técnicos relevantes — para o examinador ver rapidamente "o
      que não funcionou" sem precisar vasculhar o log completo.
"""

from __future__ import annotations

import logging
from pathlib import Path


def configurar_logger_arquivo(pasta_caso: Path, nome_arquivo: str = "extracao.log") -> logging.Logger:
    pasta_caso = Path(pasta_caso)
    pasta_caso.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"forensic.{pasta_caso.resolve()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(pasta_caso / nome_arquivo, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)

    return logger


def configurar_logger_erros(pasta_caso: Path, nome_arquivo: str = "erros.log") -> logging.Logger:
    """
    Logger dedicado a falhas e ressalvas de extração, gravado em
    `<pasta_caso>/erros/<nome_arquivo>` — separado do log geral para que o
    examinador consiga ver rapidamente quais módulos não completaram com
    sucesso pleno, sem precisar ler o log inteiro.
    """
    pasta_caso = Path(pasta_caso)
    pasta_erros = pasta_caso / "erros"
    pasta_erros.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"forensic.erros.{pasta_caso.resolve()}")
    logger.setLevel(logging.WARNING)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(pasta_erros / nome_arquivo, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)

    return logger
