"""
Conferência de ponta a ponta: TODO manifesto e TODO `.sha256` de uma aquisição
são aceitos por `sha256sum -c`, e a conferência de fato acusa adulteração.

Motivação (21/11/2026). Um defeito de CRLF fazia o `sha256sum -c` acusar
`FAILED` em arquivo íntegro — a ferramenta "afirmava" uma quebra de integridade
que não existia. `test_manifesto_lf.py` tranca os dois geradores compartilhados
(`gravar_hash_avulso`, `gerar_manifesto`). Este teste é a rede mais larga:

1. Monta uma aquisição realista pelos geradores REAIS do núcleo (arquivos em
   subpasta, nome com acento, binário, imagem) e gera o manifesto.
2. VARRE recursivamente a pasta e submete CADA arquivo de conferência
   (`manifesto_hashes*.txt` e `*.sha256`) ao `sha256sum -c` real, exigindo
   código 0 e nenhum `FAILED` — e nenhum `\r` nos bytes.
3. ADULTERA um byte de um arquivo coberto e exige que o `sha256sum -c` passe a
   acusar `FAILED`. Sem isso, "código 0" seria elogio vazio: prova-se que o
   verificador verifica.

Extra: se `HEXIS_AQUISICAO_REAL` apontar para a pasta de uma aquisição real
(feita em aparelho, pelos extratores completos), a mesma varredura roda sobre
ela — é assim que os `.sha256` gravados direto pelos extratores (rótulo Android,
bugreport) ficam cobertos sem depender de um aparelho no CI.

`sha256sum`: procurado no PATH e, se ausente, nos locais padrão do Git para
Windows — para valer mesmo quando a suíte roda pelo PowerShell.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import (  # noqa: E402
    NOME_MANIFESTO,
    PADRAO_MANIFESTO,
    calcular_sha256,
    gerar_manifesto,
    gravar_hash_avulso,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def achar_sha256sum():
    """`sha256sum` do PATH ou, se ausente, dos locais padrão do Git no Windows."""
    no_path = shutil.which("sha256sum")
    if no_path:
        return no_path
    candidatos = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "sha256sum.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "usr" / "bin" / "sha256sum.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "usr" / "bin" / "sha256sum.exe",
    ]
    for caminho in candidatos:
        if caminho.is_file():
            return str(caminho)
    return None


SHA256SUM = achar_sha256sum()


def arquivos_de_conferencia(pasta: Path):
    """Todo manifesto e todo `.sha256` sob a pasta (o que um terceiro confere)."""
    encontrados = list(pasta.glob(PADRAO_MANIFESTO))
    encontrados += sorted(pasta.rglob("*.sha256"))
    return encontrados


def conferir_um(arquivo: Path):
    """Roda `sha256sum -c` no arquivo, a partir da pasta dele. (codigo, saida)."""
    processo = subprocess.run(
        [SHA256SUM, "-c", arquivo.name], cwd=str(arquivo.parent),
        capture_output=True, text=True,
    )
    return processo.returncode, processo.stdout + processo.stderr


def varrer(pasta: Path, rotulo: str):
    """Varre e confere todos os arquivos de conferência. Devolve quantos achou."""
    arquivos = arquivos_de_conferencia(pasta)
    checar(f"[{rotulo}] há arquivos de conferência para checar", len(arquivos) > 0)
    for arquivo in arquivos:
        rel = arquivo.relative_to(pasta).as_posix()
        checar(f"[{rotulo}] {rel} não tem \\r (LF puro)", b"\r" not in arquivo.read_bytes())
        if SHA256SUM:
            codigo, saida = conferir_um(arquivo)
            checar(f"[{rotulo}] sha256sum -c aceita {rel} (código {codigo})",
                   codigo == 0 and "FAILED" not in saida)
    return len(arquivos)


print(f"\nsha256sum: {SHA256SUM or 'AUSENTE (conferência externa pulada; checagem de \\r mantida)'}")

print("\n[1] Aquisição sintética pelos geradores reais do núcleo")
with tempfile.TemporaryDirectory() as temporaria:
    pasta = criar_pasta_aquisicao(Path(temporaria), "CASO_PONTA_A_PONTA", "android",
                                  datetime(2026, 11, 21, 9, 30, 0))
    # arquivos variados: subpasta, acento no nome, binário completo, imagem
    (pasta / "sms").mkdir()
    (pasta / "sms" / "mensagens.txt").write_bytes("conteúdo adquirido — çãõ".encode("utf-8"))
    (pasta / "raiz.bin").write_bytes(bytes(range(256)))
    imagem = pasta / "coleta física.dd"
    imagem.write_bytes(b"\x00\x01\x02" * 2000)

    # `.sha256` avulsos pelo gerador real (cobre imagem física, SMS, estado…)
    gravar_hash_avulso(imagem, calcular_sha256(imagem))
    gravar_hash_avulso(pasta / "raiz.bin", calcular_sha256(pasta / "raiz.bin"))

    # manifesto consolidado real (varre tudo, inclusive os .sha256 acima)
    gerar_manifesto(pasta)

    achados = varrer(pasta, "sintética")
    checar("[sintética] cobriu manifesto + ao menos 2 .sha256", achados >= 3)

    print("\n[2] Adulteração: o verificador precisa acusar FAILED")
    if not SHA256SUM:
        print("  --   sha256sum ausente; prova de adulteração pulada")
    else:
        manifesto = (pasta / NOME_MANIFESTO)
        bytes_ok = imagem.read_bytes()
        imagem.write_bytes(bytes_ok[:-1] + bytes([bytes_ok[-1] ^ 0xFF]))  # vira 1 bit
        codigo, saida = conferir_um(manifesto)
        checar("sha256sum -c acusa FAILED no arquivo adulterado",
               codigo != 0 and "FAILED" in saida)
        imagem.write_bytes(bytes_ok)  # restaura

print("\n[3] Aquisição REAL (se HEXIS_AQUISICAO_REAL apontar para uma)")
real = os.environ.get("HEXIS_AQUISICAO_REAL", "").strip()
if not real:
    print("  --   HEXIS_AQUISICAO_REAL não definido; varredura de aquisição real pulada")
elif not Path(real).is_dir():
    checar(f"HEXIS_AQUISICAO_REAL é uma pasta existente ({real})", False)
else:
    varrer(Path(real), "real")

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
