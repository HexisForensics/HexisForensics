"""
Compila o aplicativo agente e o grava em `assets/agente/`.

    py agente_android/compilar.py

Sem Gradle e sem Android Studio, de propósito: são cinco passos com as
ferramentas do próprio SDK, todos visíveis abaixo, e o resultado é um APK
de poucos kilobytes que qualquer um pode recompilar e comparar.

Precisa de:
  - JDK 17 ou superior (variável JAVA_HOME, ou a pasta de ferramentas da
    suíte em %LOCALAPPDATA%/ForensicExtractor-ferramentas/jdk17);
  - Android SDK com `build-tools` e uma `platforms/android-NN`
    (variável ANDROID_SDK_ROOT, ou %LOCALAPPDATA%/Android/Sdk).

O APK é assinado com uma chave gerada na hora, guardada FORA do
repositório. A assinatura só serve para o Android aceitar a instalação;
quem identifica o agente usado numa aquisição é o SHA-256 do APK, que a
suíte grava no registro de cada exame.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
DESTINO = RAIZ / "assets" / "agente" / "forensic_agente.apk"
TRABALHO = AQUI / "build"

API_MINIMA = "21"
API_ALVO = "36"
VERSAO = "1"

LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
FERRAMENTAS = LOCAL / "ForensicExtractor-ferramentas"
CHAVEIRO = FERRAMENTAS / "agente.keystore"
SENHA = "forensic-agente"  # chave descartável, só para o Android aceitar instalar


def falhar(mensagem: str) -> None:
    print(f"[FALHA] {mensagem}")
    sys.exit(1)


def localizar_jdk() -> Path:
    for candidato in (os.environ.get("JAVA_HOME"), FERRAMENTAS / "jdk17"):
        if candidato and (Path(candidato) / "bin" / "javac.exe").is_file():
            return Path(candidato)
    falhar("JDK 17+ não encontrado (defina JAVA_HOME).")


def localizar_sdk() -> tuple:
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT") or LOCAL / "Android" / "Sdk")
    ferramentas = sorted((sdk / "build-tools").glob("*")) if (sdk / "build-tools").is_dir() else []
    plataforma = sdk / "platforms" / f"android-{API_ALVO}" / "android.jar"
    if not ferramentas:
        falhar(f"build-tools não encontrado em {sdk}.")
    if not plataforma.is_file():
        falhar(f"android.jar da API {API_ALVO} não encontrado em {sdk}.")
    return ferramentas[-1], plataforma


def rodar(comando: list, ambiente: dict) -> None:
    processo = subprocess.run(
        [str(parte) for parte in comando], capture_output=True, text=True, env=ambiente,
        encoding="utf-8", errors="replace",
    )
    if processo.returncode != 0:
        falhar(f"{Path(str(comando[0])).name} falhou:\n{processo.stdout}\n{processo.stderr}")


def main() -> None:
    jdk = localizar_jdk()
    ferramentas, android_jar = localizar_sdk()
    ambiente = dict(os.environ, JAVA_HOME=str(jdk),
                    PATH=str(jdk / "bin") + os.pathsep + os.environ.get("PATH", ""))

    if TRABALHO.exists():
        shutil.rmtree(TRABALHO)
    (TRABALHO / "classes").mkdir(parents=True)
    (TRABALHO / "dex").mkdir()

    print("[1/5] Empacotando o manifesto (aapt2)...")
    base = TRABALHO / "base.apk"
    rodar([ferramentas / "aapt2.exe", "link", "-o", base, "--manifest", AQUI / "AndroidManifest.xml",
           "-I", android_jar, "--min-sdk-version", API_MINIMA, "--target-sdk-version", API_ALVO,
           "--version-code", VERSAO, "--version-name", VERSAO], ambiente)

    print("[2/5] Compilando o Java (javac)...")
    fontes = sorted((AQUI / "src").rglob("*.java"))
    rodar([jdk / "bin" / "javac.exe", "-source", "8", "-target", "8", "-nowarn", "-encoding", "UTF-8",
           "-classpath", android_jar, "-d", TRABALHO / "classes", *fontes], ambiente)

    print("[3/5] Convertendo para DEX (d8)...")
    classes = sorted((TRABALHO / "classes").rglob("*.class"))
    rodar([jdk / "bin" / "java.exe", "-cp", ferramentas / "lib" / "d8.jar", "com.android.tools.r8.D8",
           "--lib", android_jar, "--min-api", API_MINIMA, "--output", TRABALHO / "dex", *classes],
          ambiente)

    print("[4/5] Montando e alinhando o APK (zipalign)...")
    with zipfile.ZipFile(base, "a", zipfile.ZIP_DEFLATED) as pacote:
        pacote.write(TRABALHO / "dex" / "classes.dex", "classes.dex")
    alinhado = TRABALHO / "alinhado.apk"
    rodar([ferramentas / "zipalign.exe", "-f", "4", base, alinhado], ambiente)

    print("[5/5] Assinando (apksigner)...")
    if not CHAVEIRO.is_file():
        CHAVEIRO.parent.mkdir(parents=True, exist_ok=True)
        rodar([jdk / "bin" / "keytool.exe", "-genkeypair", "-keystore", CHAVEIRO, "-storepass", SENHA,
               "-keypass", SENHA, "-alias", "agente", "-keyalg", "RSA", "-keysize", "2048",
               "-validity", "10000", "-dname", "CN=Hexis Forensics Agente"], ambiente)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    rodar([jdk / "bin" / "java.exe", "-jar", ferramentas / "lib" / "apksigner.jar", "sign",
           "--ks", CHAVEIRO, "--ks-pass", f"pass:{SENHA}", "--key-pass", f"pass:{SENHA}",
           "--out", DESTINO, alinhado], ambiente)
    for sobra in DESTINO.parent.glob("*.idsig"):
        sobra.unlink()
    shutil.rmtree(TRABALHO)

    resumo = hashlib.sha256(DESTINO.read_bytes()).hexdigest()
    DESTINO.with_suffix(".apk.sha256").write_text(f"{resumo} *{DESTINO.name}\n", encoding="utf-8")
    print(f"\n[CONCLUÍDO] {DESTINO}  ({DESTINO.stat().st_size} bytes)")
    print(f"            SHA-256: {resumo}")


if __name__ == "__main__":
    main()
