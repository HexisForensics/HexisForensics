"""
Janelas em tela pequena, visualizador modal e registro de erros.

Relato de 04/11/2026, primeira instalação em campo: ao gerar o laudo,
"todos os botões ficaram desabilitados" e só reiniciando se voltou a
trabalhar. Causas prováveis, todas corrigidas e conferidas aqui:

1. janelas mais altas que a tela (o formulário do laudo tinha 780 px, o
   visualizador 860 px): num monitor 1366x768 os botões de baixo ficavam
   fora da tela, e a janela modal bloqueava o resto;
2. o visualizador modal podia ser minimizado e, sem ícone na barra de
   tarefas, sumia bloqueando tudo;
3. nenhum erro ficava registrado na versão instalada.

Roda na plataforma "offscreen", cuja tela simulada (800x600) é menor que a
do local da instalação.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from services import perfil_service, registro_de_erros  # noqa: E402
from ui.widgets.ajuste_de_tela import caber_na_tela, centralizar_na_tela  # noqa: E402
from ui.widgets.visualizador_pdf import abrir_pdf  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


area = QGuiApplication.primaryScreen().availableGeometry()
print(f"\nTela simulada: {area.width()}x{area.height()}")

print("\n[1] Janela maior que a tela é reduzida ao que cabe")
janela = QWidget()
caber_na_tela(janela, 680, 780)
checar(f"altura {janela.height()} cabe em {area.height()}", janela.height() <= area.height())
checar(f"largura {janela.width()} cabe em {area.width()}", janela.width() <= area.width())
pequena = QWidget()
caber_na_tela(pequena, 300, 200)
checar("janela que já cabe mantém o tamanho pedido", pequena.size().toTuple() == (300, 200))
centralizar_na_tela(janela)
checar("centralizada, a barra de título fica dentro da tela",
       area.contains(janela.pos()) and janela.y() >= area.y())

print("\n[2] Visualizador aberto de janela modal: sem minimizar, dentro da tela")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporaria:
    pdf = Path(temporaria) / "laudo.pdf"
    from reportlab.pdfgen import canvas
    folha = canvas.Canvas(str(pdf))
    folha.drawString(72, 720, "Laudo de teste")
    folha.save()

    mae = QDialog()
    mae.setModal(True)
    mae.show()
    visualizador = abrir_pdf(pdf, mae)
    bandeiras = visualizador.windowFlags()
    checar("modal em relação à suíte", visualizador.windowModality() == Qt.ApplicationModal)
    checar("sem botão de minimizar", not bandeiras & Qt.WindowMinimizeButtonHint)
    checar("com botão de fechar", bool(bandeiras & Qt.WindowCloseButtonHint))
    checar("com botão de maximizar", bool(bandeiras & Qt.WindowMaximizeButtonHint))
    checar(f"altura {visualizador.height()} cabe na tela", visualizador.height() <= area.height())
    visualizador.close()
    mae.close()

    print("\n[3] Erro inesperado vai para erros.log e o examinador é avisado uma vez")
    perfil_service.usar_perfil_em(Path(temporaria) / "estacao")
    avisos = []

    def avisar(caminho, resumo):
        avisos.append((caminho, resumo))
        raise RuntimeError("erro dentro do próprio aviso")  # não pode virar cascata

    excepthook_original = sys.excepthook
    try:
        registro_de_erros.instalar(avisar=avisar)
        try:
            raise ValueError("falha simulada ao gerar o laudo")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        registro_de_erros.desinstalar()
        sys.excepthook = excepthook_original
        perfil_service.usar_perfil_em(None)

    arquivo = Path(temporaria) / "estacao" / registro_de_erros.NOME_ARQUIVO
    texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
    checar("erros.log criado na pasta da estação", arquivo.exists())
    checar("o registro traz o erro e o rastro",
           "falha simulada ao gerar o laudo" in texto and "Traceback" in texto)
    checar("o registro traz a versão da ferramenta", "Hexis Forensics" in texto)
    checar("o examinador foi avisado exatamente uma vez", len(avisos) == 1)
    checar("o aviso aponta o arquivo", avisos and avisos[0][0] == arquivo)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
