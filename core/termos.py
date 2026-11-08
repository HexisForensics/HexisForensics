"""
Termos de uso: o texto, a versão, e o aceite de cada examinador.

Fonte única do texto. O instalador mostra o mesmo texto (o empacotador o
grava em `instalador/TERMOS_DE_USO.txt` a partir daqui), a tela de entrada
o mostra no cadastro, e a tela "Sobre" o deixa à consulta.

O aceite do instalador é de quem instalou — que pode ser o setor de TI.
O que vale para o exame é o aceite de cada EXAMINADOR, em nome próprio,
guardado no cadastro e anotado no registro de acessos com a versão. Se o
texto mudar, a versão sobe e cada um aceita de novo no próximo acesso.
"""

from __future__ import annotations

VERSAO_DOS_TERMOS = 1
DATA_DOS_TERMOS = "31/10/2026"

TITULO = "TERMOS DE USO DO HEXIS FORENSICS"

CLAUSULAS = (
    ("Uso autorizado",
     "A ferramenta destina-se exclusivamente ao exame de dispositivos e mídias cujo "
     "acesso esteja amparado em autorização legal ou judicial, ou no consentimento de "
     "quem tem direito sobre os dados. O usuário declara que só a utilizará nessas "
     "condições."),
    ("Responsabilidade do usuário",
     "O uso da ferramenta, a observância das normas aplicáveis ao exame e as conclusões "
     "extraídas do material são de responsabilidade exclusiva de quem a utiliza. O autor "
     "não responde por uso indevido, ilícito ou sem autorização."),
    ("Sem garantia",
     "A ferramenta é fornecida gratuitamente, \"no estado em que se encontra\", sem "
     "garantia de qualquer espécie, nos termos da licença GNU GPL-3.0. Os documentos que "
     "ela gera declaram as limitações de cada coleta, e cabe ao examinador avaliá-las."),
)

DECLARACAO = ("Ao clicar em \"Eu aceito\", o usuário declara ter lido e concordado com "
              "estes termos.")


def cabecalho() -> str:
    return f"{TITULO} — versão {VERSAO_DOS_TERMOS}, de {DATA_DOS_TERMOS}"


def texto() -> str:
    """O texto integral, em texto simples (instalador, registro, tela)."""
    partes = [cabecalho(), ""]
    for numero, (titulo, corpo) in enumerate(CLAUSULAS, 1):
        partes += [f"{numero}. {titulo}. {corpo}", ""]
    partes.append(DECLARACAO)
    return "\n".join(partes) + "\n"


def html() -> str:
    """O mesmo texto, para as telas da ferramenta."""
    partes = [f"<p><b>{cabecalho()}</b></p>"]
    for numero, (titulo, corpo) in enumerate(CLAUSULAS, 1):
        partes.append(f"<p><b>{numero}. {titulo}.</b> {corpo}</p>")
    partes.append(f"<p>{DECLARACAO}</p>")
    return "".join(partes)


def aceite_vigente(registro: dict) -> bool:
    """`True` se o cadastro do examinador traz o aceite da versão atual."""
    try:
        return int(registro.get("termos_aceitos") or 0) >= VERSAO_DOS_TERMOS
    except (TypeError, ValueError):
        return False
