"""
Gera o executável da suíte em `dist/HexisForensics/`.

Uso:
    py empacotar.py --instalador   (gera o Setup.exe a partir da pasta portátil)
    py empacotar.py --portatil     (recomendado: não exige assinatura digital)

    py -m pip install pyinstaller
    py empacotar.py                (executável único; exige assinatura digital)

DOIS MODOS, porque o primeiro não bastou. Em 09/10/2026 o executável foi
gerado e o Windows 11 se recusou a executá-lo: o Controle Inteligente de
Aplicativos bloqueia executável sem assinatura digital (WinError 4551), e
o mesmo aconteceria em qualquer estação com esse controle ligado.

O modo PORTÁTIL contorna isso sem tocar na segurança do sistema: leva o
próprio interpretador Python, que é assinado pelo fabricante, ao lado do
código da suíte, e abre por um atalho `.bat`. A estação de destino não
precisa ter nada instalado. O código vai legível, o que para ferramenta
pericial é qualidade: o que roda pode ser lido e conferido.

O resultado é uma PASTA, não um arquivo único: `HexisForensics.exe` com
`extracoes/`, `binario/`, `branding/` e `assets/` ao lado. Arquivo único
se descompacta numa pasta temporária a cada execução, e a suíte precisa de
um lugar fixo e visível para as extrações e para o ADB.

O build NÃO termina quando o empacotador termina. Termina quando o
executável pronto é EXECUTADO e responde o mesmo que o código-fonte: os
extratores são descobertos por import dinâmico, que o empacotador não vê,
e um executável montado sem eles abre normalmente com a lista de módulos
vazia. Só executar prova que eles estão lá.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NOME = "HexisForensics"
DESTINO = RAIZ / "dist" / NOME
EXECUTAVEL = DESTINO / f"{NOME}.exe"

# Pacotes cujos módulos são importados por descoberta, em tempo de execução.
PACOTES_DESCOBERTOS = (
    "core.android.extractors",
    "core.ios.extractors",
    "core.computador.extractors",
    # O pyiosbackup escolhe o leitor do Manifest.db por import dinâmico.
    "pyiosbackup",
)

# O que fica AO LADO do executável, legível e substituível pelo usuário.
PASTAS_AO_LADO = ("branding", "assets", "binario")

LANCADOR_ADMIN = """@echo off
REM Abre o HexisForensics como Administrador.
REM O modulo de Imagem do Volume le o dispositivo bruto e exige elevacao.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
start "" "%~dp0HexisForensics.exe"
"""


def falhar(mensagem: str) -> None:
    print(f"\n[FALHA] {mensagem}")
    sys.exit(1)


def autoteste(comando: list) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "autoteste.json"
        try:
            processo = subprocess.run(comando + ["--autoteste", str(saida)], timeout=180)
        except OSError as erro:
            # Medido em 09/10/2026: o Controle Inteligente de Aplicativos do
            # Windows 11 recusa executável sem assinatura digital (WinError
            # 4551). O executável FOI gerado, mas não pôde ser executado —
            # e executável não executado é executável não verificado.
            falhar(
                f"o Windows recusou a execução de {comando[0]}: {erro}\n"
                "        O executável foi gerado, mas NÃO FOI VERIFICADO. Sem assinatura "
                "digital, o Controle Inteligente de Aplicativos o bloqueia; a mesma recusa "
                "ocorrerá em qualquer estação com esse controle ligado."
            )
        if processo.returncode != 0 or not saida.is_file():
            falhar(f"o autoteste não respondeu (código {processo.returncode}): {comando[0]}")
        return json.loads(saida.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Modo portátil
# ---------------------------------------------------------------------------
DESTINO_PORTATIL = RAIZ / "dist" / f"{NOME}-portatil"

# Código e recursos da suíte, copiados para a raiz da pasta portátil.
ITENS_DA_SUITE = ("main.py", "core", "services", "ui", "branding", "assets", "binario",
                  "ferramentas", "agente_android", "requirements.txt", "README.md", "MANUAL.md",
                  "LICENSE")

# Do interpretador, o que a suíte não usa. Nada daqui é importado por
# `core`, `services` ou `ui` — e a prova é o passo de verificação, que
# executa a suíte de testes inteira com o interpretador já podado.
FORA_DO_INTERPRETADOR = (
    "Doc", "include", "libs", "tcl", "Scripts", "share",
    "Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo", "Lib/ensurepip",
    "Lib/site-packages/pip", "Lib/site-packages/setuptools",
    "Lib/site-packages/PyInstaller", "Lib/site-packages/_pyinstaller_hooks_contrib",
    "Lib/site-packages/PySide6/Qt6WebEngineCore.dll",
    "Lib/site-packages/PySide6/resources",
    "Lib/site-packages/PySide6/qml",
    "Lib/site-packages/PySide6/translations",
    "Lib/site-packages/PySide6/examples",
)

LANCADOR = """@echo off
REM Abre o HexisForensics.
cd /d "%~dp0"
start "" "%~dp0python\\pythonw.exe" -s -E "%~dp0main.py"
"""

LANCADOR_ADMIN_PORTATIL = """@echo off
REM Abre o HexisForensics como Administrador.
REM O modulo de Imagem do Volume le o dispositivo bruto e exige elevacao.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
start "" "%~dp0python\\pythonw.exe" -s -E "%~dp0main.py"
"""


def _ignorar_caches(_pasta, nomes):
    return [n for n in nomes if n == "__pycache__" or n.endswith(".pyc")]


def empacotar_portatil() -> None:
    interpretador_origem = Path(sys.base_prefix)
    print(f"[1/4] Montando a pasta portátil em {DESTINO_PORTATIL} ...")
    if DESTINO_PORTATIL.exists():
        shutil.rmtree(DESTINO_PORTATIL)
    DESTINO_PORTATIL.mkdir(parents=True)

    for nome in ITENS_DA_SUITE:
        origem = RAIZ / nome
        if origem.is_dir():
            shutil.copytree(origem, DESTINO_PORTATIL / nome, ignore=_ignorar_caches)
        elif origem.is_file():
            shutil.copy2(origem, DESTINO_PORTATIL / nome)
        else:
            print(f"      aviso: '{nome}' não existe no projeto e não foi copiado.")
    shutil.copytree(RAIZ / "tests", DESTINO_PORTATIL / "tests", ignore=_ignorar_caches)
    (DESTINO_PORTATIL / "extracoes").mkdir()

    print(f"[2/4] Copiando o interpretador de {interpretador_origem} ...")
    destino_python = DESTINO_PORTATIL / "python"
    shutil.copytree(interpretador_origem, destino_python, ignore=_ignorar_caches)
    for relativo in FORA_DO_INTERPRETADOR:
        alvo = destino_python / relativo
        if alvo.is_dir():
            shutil.rmtree(alvo)
        elif alvo.is_file():
            alvo.unlink()
    (DESTINO_PORTATIL / f"{NOME}.bat").write_text(LANCADOR, encoding="ascii")
    (DESTINO_PORTATIL / "Abrir como Administrador.bat").write_text(
        LANCADOR_ADMIN_PORTATIL, encoding="ascii"
    )

    print("[3/4] Executando a versão portátil e comparando com o código-fonte...")
    python_portatil = destino_python / "python.exe"
    comando = [str(python_portatil), "-s", "-E", str(DESTINO_PORTATIL / "main.py")]
    da_fonte = autoteste([sys.executable, str(RAIZ / "main.py")])
    da_portatil = autoteste(comando)

    if Path(da_portatil["raiz_da_instalacao"]) != DESTINO_PORTATIL.resolve():
        falhar(f"a versão portátil acha que está em {da_portatil['raiz_da_instalacao']}")
    # Fora do desenvolvimento (a portátil não leva o `.git`), os casos vão para
    # `<perfil>/HexisForensics-Casos` — e NÃO para dentro da pasta do programa,
    # senão uma atualização alcançaria a evidência (ver core.instalacao).
    perfil = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    esperadas = {(perfil / "HexisForensics-Casos").resolve(),
                 (perfil / "ForensicExtractor-Casos").resolve()}
    if Path(da_portatil["pasta_extracoes"]).resolve() not in esperadas:
        falhar(f"as extrações iriam para {da_portatil['pasta_extracoes']}, fora da pasta "
               "de usuário HexisForensics-Casos")
    for plataforma, modulos in da_fonte["modulos"].items():
        na_portatil = da_portatil["modulos"].get(plataforma, [])
        if na_portatil != modulos:
            falhar(f"{plataforma}: a versão portátil enxerga {len(na_portatil)} módulo(s) "
                   f"e o código-fonte {len(modulos)}.")
        print(f"      {plataforma}: {len(na_portatil)} módulo(s), igual ao código-fonte.")
    if da_portatil.get("forensic_admin_disponivel", True):
        falhar("a versão portátil oferece a conta de testes Forensic Admin — ela só pode "
               "existir na versão de desenvolvimento.")
    print("      Forensic Admin: ausente, como deve ser na versão distribuída.")
    if da_fonte["adb_encontrado"] and not da_portatil["adb_encontrado"]:
        falhar(f"a versão portátil não encontrou o ADB: {da_portatil['adb_mensagem']}")
    print(f"      ADB encontrado: {da_portatil['adb_encontrado']}")

    # A poda do interpretador só é segura se a suíte inteira continuar
    # passando COM ELE. É a diferença entre "removi o que parecia sobrar" e
    # "removi, executei tudo, e nada sentiu falta".
    print("      Rodando a suíte de testes com o interpretador portátil...")
    testes = subprocess.run(
        [str(python_portatil), "-s", "-E", str(DESTINO_PORTATIL / "tests" / "rodar_todos.py")],
        cwd=str(DESTINO_PORTATIL), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=1800,
    )
    ultima = [l for l in (testes.stdout or "").splitlines() if l.startswith("RESULTADO")]
    print(f"      {ultima[-1] if ultima else '(sem linha de resultado)'}")
    if testes.returncode != 0:
        falhar("a suíte de testes NÃO passa com o interpretador portátil.")

    # A suíte usa clientes falsos de iPhone: ela não carrega a biblioteca de
    # verdade. Foi assim que o instalador 0.4.0 saiu sem o `packaging` e não
    # achava o iPhone (31/10/2026).
    ios = subprocess.run(
        [str(python_portatil), "-s", "-E", "-c",
         "import pymobiledevice3.lockdown, pymobiledevice3.services.mobilebackup2, "
         "pyiosbackup; print('IOS_OK')"],
        cwd=str(DESTINO_PORTATIL), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )
    if "IOS_OK" not in (ios.stdout or ""):
        falhar("a biblioteca do iPhone não carrega na versão portátil:\n"
               + (ios.stderr or ios.stdout or "")[-800:])
    print("      Biblioteca do iPhone: carrega.")

    # A janela precisa de fato abrir: a suíte não instancia a interface.
    janela = subprocess.run(
        [str(python_portatil), "-s", "-E", "-c",
         "import sys; sys.path.insert(0, r'%s'); "
         "from PySide6.QtWidgets import QApplication; app = QApplication(sys.argv); "
         "from services.branding_service import carregar_branding; "
         "from ui.main_window import MainWindow; j = MainWindow(carregar_branding()); "
         "j.show(); app.processEvents(); print('JANELA_OK', j.isVisible())"
         % str(DESTINO_PORTATIL)],
        cwd=str(DESTINO_PORTATIL), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )
    if "JANELA_OK True" not in (janela.stdout or ""):
        falhar("a janela principal não abriu na versão portátil:\n"
               + (janela.stderr or janela.stdout or "")[-800:])
    print("      A janela principal abriu.")
    for sobra in list(DESTINO_PORTATIL.rglob("__pycache__")):
        shutil.rmtree(sobra, ignore_errors=True)

    print("[4/4] Registrando os hashes do código entregue...")
    linhas = []
    for arquivo in sorted(DESTINO_PORTATIL.rglob("*")):
        relativo = arquivo.relative_to(DESTINO_PORTATIL)
        if arquivo.is_file() and relativo.parts[0] in ("core", "services", "ui", "main.py"):
            linhas.append(f"{hashlib.sha256(arquivo.read_bytes()).hexdigest()} *{relativo.as_posix()}")
    (DESTINO_PORTATIL / "HASHES_DO_CODIGO.sha256").write_text(
        "\n".join(linhas) + "\n", encoding="utf-8"
    )

    tamanho = sum(a.stat().st_size for a in DESTINO_PORTATIL.rglob("*") if a.is_file())
    print(f"\n[CONCLUÍDO] {DESTINO_PORTATIL}  ({tamanho / 1024 / 1024:.0f} MB)")
    print(f"            {len(linhas)} arquivo(s) de código com hash registrado.")
    print(f"            Para abrir: {NOME}.bat")


# ---------------------------------------------------------------------------
# Instalador (Inno Setup)
# ---------------------------------------------------------------------------
SCRIPT_DO_INSTALADOR = RAIZ / "instalador" / "HexisForensics.iss"
LOCAIS_DO_INNO = (
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
)


def gerar_instalador() -> None:
    """
    Gera `dist/HexisForensics-Setup-<versão>.exe` a partir da pasta portátil.

    O instalador embrulha a pasta PORTÁTIL, e não o executável único: o que
    roda na máquina de destino é o interpretador Python assinado pelo
    fabricante, que o Controle Inteligente de Aplicativos do Windows 11
    aceita. O próprio Setup.exe sai SEM assinatura digital — numa máquina
    com esse controle ligado ele é bloqueado, e a saída é a pasta portátil
    ou um certificado de assinatura de código.
    """
    iscc = next((caminho for caminho in LOCAIS_DO_INNO if caminho.is_file()), None)
    if iscc is None:
        falhar("o Inno Setup 6 não foi encontrado (ISCC.exe). Instale-o e repita.")

    empacotar_portatil()

    sys.path.insert(0, str(RAIZ))
    from core.versao import VERSAO
    from core.termos import texto as texto_dos_termos

    # O instalador mostra os termos de uso e exige o aceite. O texto sai da
    # mesma fonte que a ferramenta usa (core/termos.py); o BOM é o que faz o
    # Inno Setup lê-lo como UTF-8.
    (SCRIPT_DO_INSTALADOR.parent / "TERMOS_DE_USO.txt").write_text(
        texto_dos_termos().replace("\n", "\r\n"), encoding="utf-8-sig", newline="")

    print(f"\n[instalador] Compilando com {iscc} ...")
    processo = subprocess.run(
        [str(iscc), f"/DVersao={VERSAO}", str(SCRIPT_DO_INSTALADOR)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if processo.returncode != 0:
        falhar("o Inno Setup não compilou o instalador:\n" + (processo.stdout or "")[-1500:]
               + (processo.stderr or "")[-500:])

    instalador = RAIZ / "dist" / f"{NOME}-Setup-{VERSAO}.exe"
    if not instalador.is_file():
        falhar(f"o Inno Setup terminou sem erro, mas {instalador.name} não foi gerado.")
    resumo = hashlib.sha256(instalador.read_bytes()).hexdigest()
    instalador.with_suffix(".exe.sha256").write_text(
        f"{resumo} *{instalador.name}\n", encoding="utf-8"
    )
    print(f"[CONCLUÍDO] {instalador}  ({instalador.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"            SHA-256: {resumo}")
    print("            O instalador NÃO tem assinatura digital.")


def main() -> None:
    if "--instalador" in sys.argv:
        gerar_instalador()
        return
    if "--portatil" in sys.argv:
        empacotar_portatil()
        return

    print("[1/4] Empacotando...")
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NOME,
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
    ]
    for pacote in PACOTES_DESCOBERTOS:
        comando += ["--collect-submodules", pacote]
    comando.append(str(RAIZ / "main.py"))
    if subprocess.run(comando, cwd=str(RAIZ)).returncode != 0:
        falhar("o empacotador terminou com erro.")
    if not EXECUTAVEL.is_file():
        falhar(f"o executável não foi gerado em {EXECUTAVEL}")

    print("[2/4] Copiando o que fica ao lado do executável...")
    for nome in PASTAS_AO_LADO:
        origem = RAIZ / nome
        if origem.is_dir():
            shutil.copytree(origem, DESTINO / nome, dirs_exist_ok=True)
        else:
            print(f"      aviso: '{nome}/' não existe no projeto e não foi copiada.")
    (DESTINO / "extracoes").mkdir(exist_ok=True)
    (DESTINO / "Abrir como Administrador.bat").write_text(LANCADOR_ADMIN, encoding="ascii")

    print("[3/4] Executando o executável e comparando com o código-fonte...")
    da_fonte = autoteste([sys.executable, str(RAIZ / "main.py")])
    do_exe = autoteste([str(EXECUTAVEL)])

    if not do_exe["empacotada"]:
        falhar("o executável não se reconhece como empacotado.")
    if do_exe.get("forensic_admin_disponivel", True):
        falhar("o executável oferece a conta de testes Forensic Admin — ela só pode existir "
               "na versão de desenvolvimento.")
    if Path(do_exe["raiz_da_instalacao"]) != DESTINO.resolve():
        falhar(f"o executável acha que está em {do_exe['raiz_da_instalacao']}, e não em {DESTINO}")
    if Path(do_exe["pasta_extracoes"]) != (DESTINO / "extracoes").resolve():
        falhar(f"as extrações iriam para {do_exe['pasta_extracoes']}")
    for plataforma, modulos in da_fonte["modulos"].items():
        no_exe = do_exe["modulos"].get(plataforma, [])
        if no_exe != modulos:
            faltam = sorted(set(modulos) - set(no_exe))
            falhar(f"{plataforma}: o executável enxerga {len(no_exe)} módulo(s) e o "
                   f"código-fonte {len(modulos)}. Faltam: {faltam}")
        print(f"      {plataforma}: {len(no_exe)} módulo(s), igual ao código-fonte.")
    if da_fonte["adb_encontrado"] and not do_exe["adb_encontrado"]:
        falhar(f"o executável não encontrou o ADB: {do_exe['adb_mensagem']}")
    print(f"      ADB encontrado pelo executável: {do_exe['adb_encontrado']}")

    print("[4/4] Registrando o hash do executável...")
    sha256 = hashlib.sha256(EXECUTAVEL.read_bytes()).hexdigest()
    (DESTINO / f"{NOME}.exe.sha256").write_text(f"{sha256} *{NOME}.exe\n", encoding="utf-8")

    tamanho = sum(a.stat().st_size for a in DESTINO.rglob("*") if a.is_file()) / 1024 / 1024
    print(f"\n[CONCLUÍDO] {DESTINO}  ({tamanho:.0f} MB)")
    print(f"            SHA-256 do executável: {sha256}")


if __name__ == "__main__":
    main()
