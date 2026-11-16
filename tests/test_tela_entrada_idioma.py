"""
Prova que migrar a `TelaEntrada` para a camada de idioma NÃO mudou o
português — o texto de tela sai como antes.

A janela é construída na plataforma "offscreen", com um perfil de estação
isolado e vazio (cai na página de cadastro do primeiro examinador, mas os
widgets de todas as páginas já existem e podem ser conferidos).
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.idioma import traduzir  # noqa: E402
from services import perfil_service  # noqa: E402
from services.branding_service import carregar_branding  # noqa: E402
from ui.widgets.tela_entrada import TelaEntrada  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


def contem(nome, texto, trecho):
    if trecho not in texto:
        print(f" FALHA {nome}\n    não contém: {trecho!r}\n    em: {texto!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


# ---------------------------------------------------------------------------
print("\n[1] A tela de entrada constrói e o chrome sai idêntico ao PT de hoje")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    perfil_service.usar_perfil_em(Path(td) / "estacao")
    try:
        marca = carregar_branding()
        dlg = TelaEntrada(marca)

        igual("título sem bloqueio", dlg.windowTitle(), marca.nome_exibicao)
        igual("botão entrar", dlg.botao_entrar.text(), "Entrar  →")
        igual("botão novo examinador", dlg.botao_novo.text(), "＋  Novo examinador")
        igual("link esqueci", dlg.link_esqueci.text(), "Esqueci minha senha")
        igual("placeholder senha", dlg.campo_senha.placeholderText(), "Senha")
        igual("placeholder repetir", dlg.campo_repetir.placeholderText(), "Repita a senha")
        igual("botão sair", dlg.botao_sair.text(), "⏻  Sair do sistema")
        igual("botão cadastrar/entrar (voltar novo)", dlg.botao_voltar_novo.text(), "Voltar")
        contem("rodapé da marca cita a estação", dlg.rodape_marca.text(), "Estação:")
        contem("rodapé cita a norma", dlg.rodape_marca.text(), "ABNT NBR ISO/IEC 27037")

        dlg.deleteLater()
    finally:
        perfil_service.usar_perfil_em(None)

# ---------------------------------------------------------------------------
print("\n[2] Mensagens com dado embutido reconstroem o texto antigo")
# ---------------------------------------------------------------------------
igual(
    "primeiro acesso de alguém",
    traduzir("te_primeiro_acesso_de", nome="Ana", min=8),
    "Primeiro acesso de Ana: crie sua senha (mínimo 8 caracteres)",
)
igual("senha de alguém", traduzir("te_senha_de", nome="Ana"), "Senha de Ana")
igual(
    "cartão travado",
    traduzir("te_cartao_travado", ate="14:30"),
    "travado por senhas erradas até 14:30",
)
igual(
    "código impresso (molde HTML)",
    traduzir("te_codigo_impresso", marca="Hexis Forensics", examinador="Ana",
             estacao="PC-01", codigo="ABCD-1234-EFGH-5678"),
    "<h2>Hexis Forensics — código de recuperação</h2><p>Examinador: <b>Ana</b><br>"
    "Estação: PC-01</p><p style='font-size:22pt; font-family:Consolas'>ABCD-1234-EFGH-5678</p>"
    "<p>Guarde em local seguro. Usado, o código é substituído por outro.</p>",
)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
