"""
Os arquivos de hash saem com LF, conferíveis por `sha256sum -c` no Windows.

Até 20/11/2026 o manifesto (`manifesto_hashes.txt`) e os `.sha256` avulsos
eram gravados em modo texto sem `newline`. No Windows, cada `\\n` virava
`\\r\\n`, e o `sha256sum -c` (GNU coreutils) lia o `\\r` como parte do nome:
"'mensagens.txt'$'\\r': No such file or directory" num arquivo íntegro.
Quem mais precisa do `sha256sum -c` é o terceiro que confere a aquisição.

Aqui se confere:
1. que nenhum arquivo de hash gerado tem `\\r`;
2. que o `sha256sum -c` (quando existe na estação) aceita cada linha;
3. que manifestos antigos, já selados com CRLF, continuam legíveis pela
   conferência da própria ferramenta (eles não podem ser regravados).
"""

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
    calcular_sha256,
    gerar_manifesto,
    gravar_hash_avulso,
    ler_manifesto,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def conferir_com_sha256sum(arquivo_hash: Path, pasta: Path):
    """Roda `sha256sum -c` na pasta. Devolve None se a estação não o tiver."""
    executavel = shutil.which("sha256sum")
    if not executavel:
        return None
    processo = subprocess.run(
        [executavel, "-c", arquivo_hash.name], cwd=str(pasta),
        capture_output=True, text=True,
    )
    return processo.returncode, processo.stdout + processo.stderr


print("\n[1] Manifesto da aquisição")
with tempfile.TemporaryDirectory() as temporaria:
    pasta = criar_pasta_aquisicao(Path(temporaria), "CASO_TESTE", "android", datetime(2026, 11, 20, 10, 0, 0))
    (pasta / "sms").mkdir()
    (pasta / "sms" / "mensagens.txt").write_bytes("conteúdo adquirido".encode("utf-8"))
    (pasta / "raiz.bin").write_bytes(bytes(range(256)))

    manifesto = gerar_manifesto(pasta)
    bruto = manifesto.read_bytes()
    checar("o manifesto não tem nenhum \\r", b"\r" not in bruto)

    lidos = ler_manifesto(manifesto)
    checar("o caminho em subpasta usa barra normal", "sms/mensagens.txt" in lidos)
    checar("o hash lido confere com o arquivo",
           lidos.get("sms/mensagens.txt") == calcular_sha256(pasta / "sms" / "mensagens.txt"))

    conferencia = conferir_com_sha256sum(manifesto, pasta)
    if conferencia is None:
        print("  --   sha256sum ausente nesta estação; conferência externa pulada")
    else:
        codigo, saida = conferencia
        checar(f"sha256sum -c aceita o manifesto (código {codigo})", codigo == 0)
        checar("sha256sum -c não acusa arquivo ilegível", "FAILED" not in saida)

print("\n[2] Hash avulso (<arquivo>.sha256)")
with tempfile.TemporaryDirectory() as temporaria:
    pasta = Path(temporaria)
    imagem = pasta / "imagem.dd"
    imagem.write_bytes(b"\x00" * 4096)

    avulso = gravar_hash_avulso(imagem, calcular_sha256(imagem))
    checar("o .sha256 avulso não tem nenhum \\r", b"\r" not in avulso.read_bytes())

    conferencia = conferir_com_sha256sum(avulso, pasta)
    if conferencia is None:
        print("  --   sha256sum ausente nesta estação; conferência externa pulada")
    else:
        codigo, saida = conferencia
        checar(f"sha256sum -c aceita o .sha256 avulso (código {codigo})", codigo == 0 and "FAILED" not in saida)

print("\n[3] Manifesto antigo, selado com CRLF, continua legível")
with tempfile.TemporaryDirectory() as temporaria:
    antigo = Path(temporaria) / "manifesto_hashes.txt"
    valor = "a" * 64
    antigo.write_bytes(f"{'=' * 58}\r\ncabeçalho\r\n\r\n{valor} *sms/mensagens.txt\r\n".encode("utf-8"))
    checar("ler_manifesto aceita CRLF sem levar o \\r no nome",
           ler_manifesto(antigo) == {"sms/mensagens.txt": valor})

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
