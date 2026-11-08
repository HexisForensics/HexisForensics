"""
Arquivos companheiros: o que acompanha um arquivo e sem o qual ele está
incompleto.

Um banco SQLite moderno não é um arquivo, são três. `msgstore.db` guarda o
que já foi consolidado; `msgstore.db-wal` guarda **o que ainda não foi** —
e é exatamente ali que ficam as mensagens mais recentes, as da véspera da
coleta. Copiar só o `.db` perde as últimas conversas, e o banco abre
normalmente: nada avisa que faltou coisa.

O mesmo vale para o registro do Windows. Um hive tem seus `.LOG1`/`.LOG2`,
os logs de transação. Copiado de um sistema em uso sem eles, o hive fica
num estado sujo e as transações pendentes se perdem — sem erro, sem aviso.

Este módulo não classifica o arquivo antes de procurar. Ele **sonda todos
os sufixos conhecidos** e devolve os que existem de fato. Um `-wal` ao lado
de um `SYSTEM` não existe, um `.LOG1` ao lado de um `History` também não, e
a sonda simplesmente não os encontra. Classificar por extensão seria adivinhar
o tipo do arquivo pelo nome — e nome de arquivo é a informação menos
confiável de um disco periciado.

**Ausência de companheiro não é defeito.** O `-wal` é removido quando o
banco fecha limpo, e a maioria dos hives não tem log pendente. O que não
pode acontecer é o companheiro existir e não ser copiado — e, mais adiante,
quem for ler o banco não poder saber se ele existia.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

# Sufixos que se somam ao nome inteiro do arquivo: `History` -> `History-wal`.
SUFIXOS_ANEXADOS = (
    "-wal",       # write-ahead log do SQLite: o que ainda não entrou no banco
    "-shm",       # memória compartilhada que indexa o WAL
    "-journal",   # rollback journal, o modo antigo do SQLite
    ".LOG",       # log de transação de hive do Windows
    ".LOG1",
    ".LOG2",
)


def companheiros_de(caminho: Path) -> List[Path]:
    """
    Arquivos que acompanham `caminho`, entre os que existem de fato.

    Devolve lista vazia quando não há nenhum — o que é o caso normal de um
    banco fechado limpo, e não uma anomalia.
    """
    caminho = Path(caminho)
    encontrados = []
    for sufixo in SUFIXOS_ANEXADOS:
        companheiro = caminho.with_name(caminho.name + sufixo)
        try:
            if companheiro.is_file():
                encontrados.append(companheiro)
        except OSError:
            # Sem acesso para sequer verificar. Quem chama trata a recusa do
            # arquivo principal; aqui a ausência de resposta não vira presença.
            continue
    return encontrados


def descrever_companheiros(caminhos) -> str:
    """
    Texto curto listando os companheiros copiados, para log e resultado.

    Sem companheiro devolve string vazia — a linha só aparece quando há o
    que dizer.
    """
    nomes = [Path(c).name for c in caminhos]
    if not nomes:
        return ""
    return ", ".join(sorted(nomes))
