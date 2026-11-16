"""
Prova que migrar a `CasesManagerDialog` para a camada de idioma NÃO mudou
nada em português — o texto de tela sai byte a byte como antes.

A janela é construída na plataforma "offscreen" e cada texto é comparado
com o literal ORIGINAL, transcrito aqui à mão. Se a transcrição do catálogo
divergir em um acento, um espaço ou um emoji, este teste acusa.

As mensagens com dado embutido (molde + valor) são conferidas chamando
`traduzir` com valores de exemplo e comparando com o texto que o f-string
antigo produziria.
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
from ui.widgets.cases_manager_dialog import CasesManagerDialog  # noqa: E402

aplicacao = QApplication.instance() or QApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


# ---------------------------------------------------------------------------
print("\n[1] A janela constrói e o chrome sai idêntico ao português de hoje")
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    dlg = CasesManagerDialog(Path(td))

    igual("título da janela", dlg.windowTitle(),
          "Gerenciador de Casos e Cadeia de Custódia")

    igual("botão excluir caso", dlg.botao_excluir_caso.text(), "🗑 Excluir caso…")
    igual("tooltip excluir caso", dlg.botao_excluir_caso.toolTip(),
          "Envia o caso inteiro à Lixeira do Windows (restaurável), depois de confirmar "
          "digitando o nome dele. A exclusão fica no registro de acessos.")
    igual("botão retificar caso", dlg.botao_editar_caso.text(), "📁 Retificar Dados do Caso")
    igual("botão anexar autorização", dlg.botao_autorizacao.text(), "⚖ Anexar Autorização")
    igual("botão relatório de conteúdo", dlg.botao_relatorio.text(),
          "📊 Relatório de Conteúdo (CSV + PDF)")
    igual("botão relatório de extração", dlg.botao_relatorio_extracao.text(),
          "📑 Relatório de Extração (PDF)")
    igual("botão ficha", dlg.botao_ficha.text(), "🪪 Ficha do Aparelho (PDF)")
    igual("botão laudo", dlg.botao_laudo_pericial.text(), "⚖ Laudo Pericial (PDF)")
    igual("botão conversas", dlg.botao_conversas.text(), "💬 PDF de conversas selecionadas")
    igual("botão decifrar", dlg.botao_decifrar.text(), "🔑 Decifrar backup")

    igual("aba cadeia", dlg.abas.tabText(0), "Cadeia de custódia")
    igual("aba documentos", dlg.abas.tabText(1), "Documentos")
    igual("aba material", dlg.abas.tabText(2), "Material")

    igual("texto de pasta vazia", dlg.texto_ficha.toPlainText(),
          "Nenhum caso encontrado na pasta de extrações.")

    dlg.deleteLater()

# ---------------------------------------------------------------------------
print("\n[2] Mensagens com dado embutido reconstroem exatamente o texto antigo")
# ---------------------------------------------------------------------------
igual(
    "documento não gerado",
    traduzir("gc_doc_nao_gerado_corpo", erro="disco cheio"),
    "Não foi possível gerar o documento:\ndisco cheio",
)
igual(
    "corpo de exclusão (nome nos dois lugares)",
    traduzir("gc_excluir_corpo", nome="CASO_007"),
    "O caso CASO_007 inteiro — aquisições, documentos, relatórios e complementos — será "
    "enviado à Lixeira do Windows. Dá para restaurá-lo de lá; apagar de vez é esvaziar a "
    "Lixeira.\n\nPara confirmar, digite o nome do caso (CASO_007):",
)
igual(
    "rótulo da aquisição na lista",
    traduzir("gc_rotulo_aquisicao", rotulo="android_20260101", examinador="Fulano",
             selo="🔒 selada"),
    "android_20260101  ·  examinador: Fulano  ·  🔒 selada",
)
igual(
    "backup decifrado",
    traduzir("gc_backup_decifrado_corpo", resumo="3 conversas", pasta="C:/x/decifrados"),
    "3 conversas\n\nGravado em:\nC:/x/decifrados\n\nA aquisição selada não foi alterada.\n\n"
    "Em seguida será gerado o Relatório de Conteúdo, que é onde as mensagens aparecem. Um "
    "Laudo emitido antes desta decifragem não as traz: emita-o de novo.",
)
igual(
    "corpo 'já selada' (texto longo)",
    traduzir("gc_selada_corpo"),
    "Esta coleta já tem manifesto de integridade.\n\nReescrevê-la faria o caso divergir do "
    "próprio selo e apagaria o registro do que existia no momento do exame.\n\nA alteração "
    "pode ser juntada como COMPLEMENTO ao caso: o material coletado permanece intocado, e a "
    "retificação fica registrada com data própria.\n\nDeseja juntar como complemento?",
)
igual(
    "autorização anexada (lista juntada)",
    traduzir("gc_autorizacao_anexada_corpo", lista="mandado.pdf\n  termo.pdf"),
    "Anexado ao caso:\n  mandado.pdf\n  termo.pdf\n\nO caso foi reselado e a juntada ficou "
    "registrada como complemento, com o hash de cada documento.\n\nAs aquisições anteriores "
    "NÃO foram alteradas e não passam a contar com este documento: cada uma registra o que "
    "estava à vista no momento em que foi feita.",
)
igual(
    "caminho dos arquivos na cadeia",
    traduzir("gc_caminho_arquivos", conteudo="=== CADEIA ===", caminho="C:/casos/x"),
    "=== CADEIA ===\n\nCaminho dos arquivos:\nC:/casos/x",
)
igual(
    "ficha: campo não informado",
    traduzir("gc_ficha_nao_informado"),
    "<i>não informado</i>",
)
igual(
    "um VALOR com chaves não é reinterpretado (segurança da evidência)",
    traduzir("gc_doc_nao_gerado_corpo", erro="{gc_selada_corpo}"),
    "Não foi possível gerar o documento:\n{gc_selada_corpo}",
)

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
