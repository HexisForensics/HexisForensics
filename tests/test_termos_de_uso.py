"""
Termos de uso: aceite pessoal de cada examinador, guardado e registrado.

O aceite do instalador é de quem instala; o que vale para o exame é o de
quem examina — no cadastro, ou na primeira entrada de quem foi cadastrado
antes dos termos existirem.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import acesso, termos  # noqa: E402
from services import sessao_service  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


DADOS = {"nome": "Fulano de Tal", "registro_funcional": "123", "unidade": "Lab"}

print("\n[1] O texto")
texto = termos.texto()
checar("versão e data no cabeçalho", f"versão {termos.VERSAO_DOS_TERMOS}" in texto)
checar("as três cláusulas: uso autorizado, responsabilidade, sem garantia",
       all(t in texto for t in ("Uso autorizado", "Responsabilidade do usuário", "Sem garantia")))
SCRIPT_DO_INSTALADOR = RAIZ_PROJETO / "instalador" / "HexisForensics.iss"
if SCRIPT_DO_INSTALADOR.is_file():  # na pasta portátil o script do instalador não vai
    checar("o instalador exige o aceite com o mesmo texto",
           "LicenseFile=TERMOS_DE_USO.txt" in SCRIPT_DO_INSTALADOR.read_text(encoding="utf-8")
           and "core.termos" in (RAIZ_PROJETO / "empacotar.py").read_text(encoding="utf-8"))

print("\n[2] O aceite fica no cadastro e no registro")
with tempfile.TemporaryDirectory() as temporario:
    pasta = Path(temporario)
    sessao_service.usar_pasta(pasta)
    sessao_service.cadastrar_e_entrar(DADOS, "senha123")
    checar("cadastrado sem aceitar: termos ainda não aceitos", not sessao_service.termos_aceitos())
    sessao_service.aceitar_termos()
    checar("aceito: vale para a sessão", sessao_service.termos_aceitos())
    registro = (pasta / acesso.NOME_REGISTRO).read_text(encoding="utf-8")
    checar("o registro de acessos anota o aceite, com a versão",
           "TERMOS DE USO ACEITOS" in registro and f"versão {termos.VERSAO_DOS_TERMOS}" in registro
           and "Fulano de Tal" in registro)

    sessao_service.encerrar()
    sessao_service.entrar("Fulano de Tal", "senha123")
    checar("entrar de novo (o cadastro é regravado) não apaga o aceite",
           sessao_service.termos_aceitos())
    sessao_service.atualizar_dados(dict(DADOS, unidade="Outro lab"), "Fulano de Tal")
    checar("corrigir os próprios dados não apaga o aceite", sessao_service.termos_aceitos())

    versao = termos.VERSAO_DOS_TERMOS
    termos.VERSAO_DOS_TERMOS = versao + 1
    try:
        checar("texto novo (versão maior): cada um aceita de novo",
               not sessao_service.termos_aceitos())
    finally:
        termos.VERSAO_DOS_TERMOS = versao

    sessao_service.cadastrar_e_entrar(dict(DADOS, nome="Beltrano"), "senha456")
    checar("o aceite é pessoal: o de um examinador não vale para outro",
           not sessao_service.termos_aceitos())
    sessao_service.encerrar()

print("\n[3] Na tela de entrada")
with tempfile.TemporaryDirectory() as temporario:
    sessao_service.usar_pasta(Path(temporario))
    from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
    app = QApplication.instance() or QApplication([])
    from services.branding_service import carregar_branding  # noqa: E402
    from ui.widgets import tela_entrada  # noqa: E402

    tela = tela_entrada.TelaEntrada(carregar_branding())
    for chave, valor in DADOS.items():
        tela.campos_novo[chave].setText(valor)
    tela.novo_senha.setText("senha123")
    tela.novo_repetir.setText("senha123")
    tela._cadastrar()
    checar("cadastro sem marcar o aceite é recusado, e ninguém é cadastrado",
           not sessao_service.ativa() and not sessao_service.examinadores())
    tela.aceite_termos.setChecked(True)
    tela._cadastrar()
    checar("com o aceite marcado: cadastrado, e o aceite registrado",
           sessao_service.ativa() and sessao_service.termos_aceitos())
    sessao_service.encerrar()

    # Examinador antigo, sem aceite, entrando: recusar não deixa entrar.
    acesso.cadastrar(dict(DADOS, nome="Antigo"), "senha789", Path(temporario))
    sessao_service.entrar("Antigo", "senha789")

    class Recusa:
        def __init__(self, *a, **k): ...
        def exec(self): return QDialog.Rejected

    original = tela_entrada.TermosDialog
    tela_entrada.TermosDialog = Recusa
    try:
        tela2 = tela_entrada.TelaEntrada(carregar_branding())
        tela2.accept()
        checar("quem recusa os termos não entra: a sessão é encerrada",
               not sessao_service.ativa() and tela2.result() != QDialog.Accepted)
    finally:
        tela_entrada.TermosDialog = original
    sessao_service.usar_pasta(None)

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("Todos os testes passaram.")
