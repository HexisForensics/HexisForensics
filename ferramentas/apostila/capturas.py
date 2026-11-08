"""
Capturas das telas da ferramenta para a apostila.

Abre cada tela com dados FICTÍCIOS (examinadores, caso, aparelho e
mensagens inventados, numa pasta temporária) e grava a imagem em
`ferramentas/apostila/capturas/`. Nada toca nos casos nem no cadastro
reais da estação. Rodar de novo depois de mudar a interface mantém a
apostila igual à ferramenta.

Uso:  py ferramentas/apostila/capturas.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

DESTINO = Path(__file__).resolve().parent / "capturas"


def _foto(caminho: Path, rotulo: str, cor: str) -> None:
    """Uma 'fotografia' fictícia da peça: um celular desenhado."""
    imagem = QImage(480, 640, QImage.Format_RGB32)
    imagem.fill(QColor("#d9dee5"))
    p = QPainter(imagem)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(cor))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(140, 90, 200, 400), 26, 26)
    p.setBrush(QColor("#0f1b2d"))
    p.drawRoundedRect(QRectF(152, 112, 176, 340), 12, 12)
    p.setPen(QColor("#333a42"))
    fonte = QFont("Segoe UI")
    fonte.setPixelSize(26)
    p.setFont(fonte)
    p.drawText(QRectF(0, 520, 480, 60), Qt.AlignCenter, rotulo)
    p.end()
    imagem.save(str(caminho), quality=90)


def _montar_caso_ficticio(raiz: Path) -> Path:
    from core.case import criar_pasta_aquisicao
    from core.hashing import gerar_manifesto
    from services.case_service import CaseService
    from services import sessao_service

    servico = CaseService(raiz)
    aq = criar_pasta_aquisicao(raiz, "CASO_DEMO", "Android", datetime(2026, 10, 20, 14, 30))
    servico.abrir_registro_procedimento(aq, "CASO_DEMO", "Android", "ZY22DEMO01")
    servico.registrar_operador(aq, sessao_service.perfil_para_a_aquisicao())
    servico.gravar_dados_do_caso("CASO_DEMO", {
        "referencia": "Proc. 0001234-56.2026", "descricao": "Apuração de estelionato",
        "solicitante": "Laboratório Central"})
    fotos = raiz.parent / "_fotos"
    fotos.mkdir()
    _foto(fotos / "frente.jpg", "frente", "#2b3440")
    _foto(fotos / "verso.jpg", "verso", "#3a4554")
    servico.gravar_cadeia_custodia(aq, "CASO_DEMO", {
        "marca_modelo": "Motorola moto g (exemplo)", "cor": "preto",
        "estado": "tela íntegra, ligado", "lacre": "000123",
        "fotos": [fotos / "frente.jpg", fotos / "verso.jpg"]})
    (aq / "sms").mkdir()
    linhas = []
    for indice, (numero, tipo, texto) in enumerate((
        ("+5511999990001", 1, "Oi, consegue fazer o pix hoje?"),
        ("+5511999990001", 2, "Consigo à tarde."),
        ("+5511999990001", 1, "Manda o comprovante depois."),
        ("+5511988887777", 1, "Seu código de verificação é 482913"),
        ("+5511999990001", 2, "Enviado."),
    )):
        linhas.append(f"Row: {indice} _id={indice + 1}, address={numero}, "
                      f"date={1792429200000 + indice * 600000}, type={tipo}, read=1, body={texto}")
    (aq / "sms" / "sms_todas.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (aq / "contacts_calls").mkdir()
    (aq / "contacts_calls" / "agenda_contatos_bruta.txt").write_text(
        "Row: 0 display_name=Fulano de Tal, data1=+5511999990001\n"
        "Row: 1 display_name=Banco Exemplo, data1=+5511988887777\n", encoding="utf-8")
    (aq / "media" / "Camera").mkdir(parents=True)
    _foto(aq / "media" / "Camera" / "IMG_20261019_101500.jpg", "IMG_20261019", "#4a6a8a")
    servico.encerrar_registro_procedimento("Módulos executados com sucesso.")
    gerar_manifesto(aq)
    return aq


def main() -> None:
    DESTINO.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))

    from services import sessao_service
    from services.branding_service import carregar_branding
    from ui.style import aplicar_tema

    # A apostila é da versão DISTRIBUÍDA: sem a conta de testes e sem o nome
    # real da máquina de quem gera as capturas.
    import platform
    from core import acesso as _acesso

    _acesso.modo_desenvolvimento = lambda: False
    platform.node = lambda: "ESTACAO-01"

    marca = carregar_branding()
    aplicar_tema(app, marca)
    app.setFont(QFont("Segoe UI", 9))

    temporario = Path(tempfile.mkdtemp(prefix="apostila_"))
    sessao_service.usar_pasta(temporario / "cadastro")
    from core import acesso

    acesso.cadastrar({"nome": "Ana Souza", "registro_funcional": "654.321",
                      "unidade": "Laboratório Central"}, "senha-demo-1", temporario / "cadastro")
    import json

    cadastro = temporario / "cadastro" / "examinadores.json"
    dados = json.loads(cadastro.read_text(encoding="utf-8"))
    dados["perfis"].append({"nome": "João Pereira"})
    cadastro.write_text(json.dumps(dados), encoding="utf-8")
    codigo = sessao_service.cadastrar_e_entrar(
        {"nome": "Maria Examinadora", "registro_funcional": "123.456",
         "unidade": "Laboratório Central"}, "senha-demo-2")

    raiz = temporario / "extracoes"
    aquisicao = _montar_caso_ficticio(raiz)

    def salvar(widget, nome: str, largura: int = 0, altura: int = 0) -> None:
        if largura:
            widget.resize(largura, altura)
        widget.show()
        for _ in range(3):
            app.processEvents()
        widget.grab().save(str(DESTINO / f"{nome}.png"))
        print("captura:", nome)

    # --- tela de entrada
    from ui.widgets.tela_entrada import CODIGO, TelaEntrada

    import time

    tela = TelaEntrada(marca, preselecionar="Maria Examinadora")
    # A animação no meio da cena, nem esmaecendo nem entrando.
    tela.vitrine._inicio = time.monotonic() - 3.0
    salvar(tela, "01_entrada", 980, 620)
    tela._ir_para_novo()
    salvar(tela, "02_novo_examinador")
    tela._codigo_mostrado = codigo
    tela.rotulo_codigo.setText(codigo)
    tela.paginas.setCurrentIndex(CODIGO)
    salvar(tela, "03_codigo_recuperacao")
    tela.close()

    # --- janela principal
    from ui.main_window import MainWindow

    janela = MainWindow(marca)
    salvar(janela, "04_janela_android", 1200, 800)
    janela._ao_selecionar_item("iphone")
    salvar(janela, "05_janela_iphone")
    janela._ao_selecionar_item("computador")
    salvar(janela, "06_janela_armazenamento")
    janela._ao_selecionar_item("android")

    # --- diálogos do início da extração
    from services.case_service import CaseService
    from services.extraction_service import descrever_metodo, listar_extratores
    from ui.widgets.case_dialog import CaseDialog
    from ui.widgets.device_info_dialog import DeviceInfoDialog
    from ui.widgets.exame_sem_extracao_dialog import ExameSemExtracaoDialog
    from ui.widgets.fundamento_dialog import AutorizacaoDialog
    from ui.widgets.metodo_dialog import MetodoDialog

    selecionados = [c for c in listar_extratores("Android") if not c.selecao_expressa][:6]
    salvar(MetodoDialog(descrever_metodo(selecionados)), "07_metodo", 760, 620)
    salvar(CaseDialog(CaseService(raiz), "Android"), "08_caso", 720, 560)
    salvar(AutorizacaoDialog([]), "09_autorizacao", 720, 520)
    dispositivo = DeviceInfoDialog()
    dispositivo.campo_marca_modelo.setText("Motorola moto g (exemplo)")
    salvar(dispositivo, "10_dispositivo", 520, 600)
    sem_extracao = ExameSemExtracaoDialog()
    sem_extracao.campo_tentativas.setPlainText(
        "Aparelho ligado na presença do examinador; tela de bloqueio por PIN exibida; "
        "credencial não fornecida; nenhuma tentativa de desbloqueio.")
    salvar(sem_extracao, "11_exame_sem_extracao", 580, 620)

    # --- casos e documentos
    from services import laudo_service, relatorio_extracao_service
    from services.relatorio_service import RelatorioService

    relatorio_extracao_service.gerar(aquisicao)
    RelatorioService.gerar(aquisicao)
    laudo = laudo_service.gerar(aquisicao, {"numero": "15/2026", "objetivo":
                                            "Extração de mensagens e chamadas."},
                                examinador=sessao_service.dados())

    from ui.widgets.cases_manager_dialog import CasesManagerDialog

    casos = CasesManagerDialog(raiz)
    casos.lista_projetos.setCurrentRow(0)
    salvar(casos, "12_casos_ficha", 1250, 860)
    casos.abas.setCurrentIndex(1)
    salvar(casos, "13_casos_documentos")
    casos.abas.setCurrentIndex(2)
    material = casos.material
    material.arvore.expandAll()
    for _ in range(2):
        app.processEvents()
    material._relativo = "media/Camera/IMG_20261019_101500.jpg"
    material._conferir(forcar=False)
    material._mostrar_previa()
    salvar(casos, "14_casos_material")

    from ui.widgets.visualizador_pdf import VisualizadorPdf

    visualizador = VisualizadorPdf(laudo.caminho)
    visualizador.resize(980, 860)
    visualizador.show()
    # O QPdfView desenha as páginas aos poucos: espera antes de fotografar.
    for _ in range(40):
        app.processEvents()
        time.sleep(0.05)
    salvar(visualizador, "15_visualizador")

    from ui.widgets.entrega_dialog import EntregaDialog

    entrega = EntregaDialog(aquisicao, material=["media/Camera"])
    entrega.campo_destino.setText("E:\\")
    entrega.campo_finalidade.setText("Entregue ao Juízo da 1ª Vara Criminal — Proc. 0001234-56.2026")
    salvar(entrega, "16_entrega", 660, 300)

    from ui.widgets.conversas_dialog import ConversasDialog

    conversas = ConversasDialog(aquisicao)
    conversas.tabela.item(0, 0).setCheckState(Qt.Checked)
    salvar(conversas, "17_conversas", 1000, 560)

    from ui.widgets.chave_dialog import ChaveDialog

    salvar(ChaveDialog(), "18_chave_whatsapp")

    from ui.widgets.caderno_form_dialog import LAUDO, CadernoFormDialog

    salvar(CadernoFormDialog({}, {"fotos": []}, pasta_aquisicao=aquisicao, finalidade=LAUDO),
           "19_formulario_laudo", 820, 720)

    from ui.widgets.examinadores_dialog import ExaminadoresDialog

    salvar(ExaminadoresDialog(), "20_examinadores", 820, 460)

    from ui.widgets.hash_dialog import HashDialog

    salvar(HashDialog(raiz), "21_cadeia_custodia", 900, 600)

    # --- páginas dos documentos, para mostrar como saem
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    for nome, pdf in (("22_laudo_pagina", laudo.caminho),):
        documento = QPdfDocument()
        documento.load(str(pdf))
        documento.render(0, QSize(1240, 1754)).save(str(DESTINO / f"{nome}.png"))
        print("captura:", nome)

    janela._sair_sem_perguntar = True
    sessao_service.encerrar()
    sessao_service.usar_pasta(None)
    QTimer.singleShot(0, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
