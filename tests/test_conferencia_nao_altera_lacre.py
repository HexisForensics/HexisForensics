"""
A conferência de integridade não pode alterar a aquisição que confere.

Até 02/11/2026 o serviço de conferência anotava o resultado no
`registro_procedimento.txt` da aquisição — arquivo que está dentro do lacre.
A primeira conferência dava ÍNTEGRO; a segunda acusava o próprio registro
como alterado. Achado na revisão do livro do treinamento, que descrevia uma
aquisição conferida três vezes.

Aqui a mesma aquisição é conferida três vezes seguidas pelo serviço que a
interface usa: as três têm de dar ÍNTEGRO, e nenhum arquivo selado pode
mudar de conteúdo.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import gerar_manifesto  # noqa: E402
from core.procedimento import RegistroProcedimento  # noqa: E402
from services.hash_service import ConferenciaService  # noqa: E402

aplicacao = QCoreApplication.instance() or QCoreApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def conteudo_selado(pasta: Path) -> dict:
    """Bytes de cada arquivo da aquisição, menos os relatórios de conferência."""
    return {
        str(arquivo.relative_to(pasta)): arquivo.read_bytes()
        for arquivo in sorted(pasta.rglob("*"))
        if arquivo.is_file() and not arquivo.name.startswith("conferencia_integridade")
    }


def conferir(pasta: Path) -> tuple:
    """Roda o serviço na própria thread, como a interface o roda numa QThread."""
    resultado = {}
    servico = ConferenciaService(pasta)
    servico.concluido.connect(lambda integro, resumo: resultado.update(integro=integro, resumo=resumo))
    servico.run()
    return resultado.get("integro"), resultado.get("resumo", "")


print("\n[1] Aquisição lacrada, com registro do procedimento, conferida três vezes")
with tempfile.TemporaryDirectory() as temporaria:
    pasta = criar_pasta_aquisicao(Path(temporaria), "CASO_TESTE", "android", datetime(2026, 11, 2, 10, 0, 0))
    registro = RegistroProcedimento(pasta)
    registro.registrar_observacao("Aquisição de teste.")
    (pasta / "sms").mkdir()
    (pasta / "sms" / "mensagens.txt").write_text("conteúdo adquirido", encoding="utf-8")
    gerar_manifesto(pasta)
    antes = conteudo_selado(pasta)

    for vez in (1, 2, 3):
        integro, resumo = conferir(pasta)
        checar(f"conferência {vez}: ÍNTEGRO ({resumo[:60]})", integro is True)

    checar("nenhum arquivo selado mudou de conteúdo", conteudo_selado(pasta) == antes)
    checar("o registro do procedimento não recebeu anotação da conferência",
           "Conferência de integridade" not in (pasta / "registro_procedimento.txt").read_text(encoding="utf-8"))
    relatorios = list(pasta.glob("conferencia_integridade*.txt"))
    checar(f"cada conferência deixou o seu relatório ({len(relatorios)} de 3)", len(relatorios) == 3)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
