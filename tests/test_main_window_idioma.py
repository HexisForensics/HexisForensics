"""
Prova que migrar a `main_window` para a camada de idioma NÃO mudou o
português. A janela em si é pesada de construir (sessão, timers, painéis),
então aqui provamos duas coisas:

1. o módulo importa (sem erro de sintaxe/fiação após a migração);
2. cada texto em português sai idêntico ao de hoje — chrome e moldes com
   dado embutido —, conferido contra o literal original transcrito à mão.

Os argumentos de `registrar_decisao`/`registrar_alteracao` (texto SELADO)
não foram migrados de propósito: são Fase 3.
"""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.idioma import traduzir  # noqa: E402
from ui import main_window  # noqa: E402,F401  (smoke: o módulo importa migrado)

falhas = []


def igual(nome, obtido, esperado):
    if obtido != esperado:
        print(f" FALHA {nome}\n    esperado: {esperado!r}\n    obtido:   {obtido!r}")
        falhas.append(nome)
    else:
        print("  OK   " + nome)


print("\n[1] O módulo main_window importa após a migração")
igual("TITULOS_SECAO virou chaves", main_window.TITULOS_SECAO["android"],
      ("mw_secao_extracao", "mw_bc_android"))

print("\n[2] Chrome e breadcrumbs em português idênticos")
igual("título da janela", traduzir("mw_titulo_janela", marca="Hexis Forensics"),
      "Hexis Forensics — Suíte de Extração Forense")
igual("botão iniciar", traduzir("mw_btn_iniciar"), "▶ Iniciar Extração")
igual("botão exame sem extração", traduzir("mw_btn_sem_extracao"), "📝 Exame sem extração")
igual("breadcrumb android", traduzir("mw_bc_android"), "Início › Extração › Android")
igual("breadcrumb armazenamento", traduzir("mw_bc_computador"),
      "Início › Extração › Armazenamento")
igual("console título", traduzir("mw_console_titulo"), "Console de Execução:")

print("\n[3] Mensagens com dado embutido reconstroem o texto antigo")
igual("confirmar extração", traduzir("mw_confirmar_extracao", nome="Ana"),
      "Esta extração será registrada como feita por <b>Ana</b>.<br>"
      "Se não é você, troque de examinador antes.")
igual("confirmar sem extração", traduzir("mw_confirmar_sem_extracao", nome="Ana"),
      "Este exame sem extração será registrado como feito por <b>Ana</b>.<br>"
      "Se não é você, troque de examinador antes.")
igual("pergunta sair", traduzir("mw_sair_pergunta", marca="Hexis Forensics"),
      "Deseja sair do Hexis Forensics?")
igual("log operador", traduzir("mw_log_operador", valor="Ana · PC-01"),
      "[*] Operador: Ana · PC-01")
igual("log unidades", traduzir("mw_log_unidades", n=3),
      "[Computador] 3 unidade(s) de disco detectada(s).")
igual("fechar com extração (texto longo)", traduzir("mw_fechar_extracao"),
      "Há uma extração em andamento. Sair agora deixaria a aquisição sem o lacre "
      "(manifesto) e sem o registro de encerramento.\n\nClique em 'Cancelar', aguarde a "
      "mensagem de extração finalizada e então saia.")
igual("sobre (bloco inteiro)", traduzir("mw_sobre_corpo", ferramenta="Hexis Forensics 1.0.0"),
      "<b>Hexis Forensics 1.0.0</b><br><br>"
      "Suíte de aquisição e preservação de evidência digital para "
      "Android, iPhone e mídias de armazenamento, orientada pela "
      "ABNT NBR ISO/IEC 27037.<br><br>"
      "A ferramenta nunca afirma o que não verificou: ausência de dado "
      "no material adquirido não autoriza concluir ausência do dado no "
      "dispositivo.<br><br>"
      "Copyright © 2026 Hexis Forensics. Software livre, distribuído nos "
      "termos da GNU General Public License, versão 3 (GPL-3.0), <b>sem "
      "nenhuma garantia</b>. O texto da licença está no arquivo LICENSE.")

print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
