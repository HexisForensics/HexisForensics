"""
Excluir caso: só com o nome digitado, nunca com aquisição sem lacre, sempre
para a Lixeira (aqui simulada) e sempre registrado.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from services import sessao_service  # noqa: E402
from services.exclusao_service import ErroDeExclusao, excluir_caso  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def recusa(*args, **kwargs) -> str:
    try:
        excluir_caso(*args, **kwargs)
    except ErroDeExclusao as erro:
        return str(erro)
    return ""


with tempfile.TemporaryDirectory() as temporario:
    sessao_service.usar_pasta(Path(temporario) / "cadastro")
    sessao_service.cadastrar_e_entrar({"nome": "Fulana"}, "segredo1")
    raiz = Path(temporario) / "extracoes"
    aquisicao = criar_pasta_aquisicao(raiz, "CASO_Z", "Android", datetime(2026, 10, 24, 10, 0))
    (aquisicao / "dado.txt").write_text("x", encoding="utf-8")
    caso = raiz / "CASO_Z"
    enviados = []

    print("\n[1] As travas")
    checar("confirmação errada é recusada, e nada é enviado",
           "não confere" in recusa(caso, "caso_z", lixeira=enviados.append) and not enviados)
    checar("aquisição sem lacre impede a exclusão",
           "sem lacre" in recusa(caso, "CASO_Z", lixeira=enviados.append) and not enviados)

    print("\n[2] A exclusão")
    gerar_manifesto(aquisicao)
    checar("com o nome certo e tudo lacrado, vai para a lixeira",
           recusa(caso, "CASO_Z", lixeira=enviados.append) == "" and enviados == [caso])
    log = (Path(temporario) / "cadastro" / "acessos.log").read_text(encoding="utf-8")
    checar("e fica no registro de acessos, com quem excluiu",
           "CASO EXCLUÍDO" in log and "CASO_Z" in log and "Fulana" in log)
    sessao_service.encerrar()
    sessao_service.usar_pasta(None)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
