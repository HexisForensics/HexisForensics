"""
De QUANDO é o conteúdo do WhatsApp lido de um backup.

Visto no moto x4 em 24/10/2026: o backup copiado era de 12/10. Sem dizer
isso, o documento parecia retratar o aparelho no dia do exame, e uma
conversa posterior ao backup, ausente, parecia não existir.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando  # noqa: E402
from core.android.extractors.whatsapp import NOME_DATAS_DOS_BACKUPS, WhatsAppExtractor  # noqa: E402
from core.hashing import calcular_sha256  # noqa: E402
from core.normalizacao import Registro, ResultadoNormalizacao  # noqa: E402
from services.relatorio_service import nota_do_backup  # noqa: E402

falhas = []
FUSO = timezone(timedelta(hours=-3))
GRAVADO = datetime(2026, 10, 12, 15, 48, tzinfo=FUSO)


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


class ADBComStat:
    def __init__(self):
        self.comandos = []

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append(argumentos)
        return ResultadoComando(0, str(int(GRAVADO.timestamp())), "")


resultado = ResultadoNormalizacao(tipo="whatsapp", registros=[
    Registro(tipo="whatsapp", momento=datetime(2026, 10, 12, 15, 40, tzinfo=FUSO)),
    Registro(tipo="whatsapp", momento=datetime(2026, 10, 11, 9, 0, tzinfo=FUSO)),
])

with tempfile.TemporaryDirectory() as temporario:
    aquisicao = Path(temporario) / "android_20261024_170156"
    databases = aquisicao / "whatsapp" / "WhatsApp_Databases_legado" / "Databases"
    databases.mkdir(parents=True)
    backup = databases / "msgstore.db.crypt15"
    backup.write_bytes(b"\x00crypt15")

    print("\n[1] Na aquisição, o aparelho informa a data de cada backup")
    extrator = WhatsAppExtractor()
    extrator.adb = ADBComStat()
    extrator.log = lambda _texto: None
    extrator._registrar_datas_dos_backups(aquisicao, aquisicao / "whatsapp")
    registro = json.loads((aquisicao / "whatsapp" / NOME_DATAS_DOS_BACKUPS).read_text(encoding="utf-8"))
    checar("perguntou ao aparelho pelo caminho EXATO no aparelho",
           extrator.adb.comandos[0][1].endswith("'/sdcard/WhatsApp/Databases/msgstore.db.crypt15'")
           and registro[0]["caminho_no_aparelho"] == "/sdcard/WhatsApp/Databases/msgstore.db.crypt15")
    checar("gravou a data e o hash da cópia",
           registro[0]["gravado_no_aparelho_epoch"] == int(GRAVADO.timestamp())
           and registro[0]["sha256"] == calcular_sha256(backup))
    checar("a resposta crua do aparelho vai junto",
           (aquisicao / "whatsapp" / "datas_dos_backups_saida.txt").is_file())

    print("\n[2] O documento diz de quando é o conteúdo")
    nota = nota_do_backup(aquisicao, backup, calcular_sha256(backup), resultado, FUSO)
    checar("data do backup, com a fonte selada", "12/10/2026 15:48" in nota and "sob o lacre" in nota)
    checar("e não o dia do exame", "não o aparelho no dia do exame" in nota)
    checar("a mensagem mais recente contida nele", "mais recente nele é de 12/10/2026 15:40" in nota)
    checar("e que a ausência posterior não é inexistência", "não significa que não existam" in nota)

    print("\n[3] Aquisição antiga, sem o registro: usa a data preservada e diz isso")
    (aquisicao / "whatsapp" / NOME_DATAS_DOS_BACKUPS).unlink()
    os.utime(backup, (GRAVADO.timestamp(), GRAVADO.timestamp()))
    nota = nota_do_backup(aquisicao, backup, calcular_sha256(backup), resultado, FUSO)
    checar("usa a data da cópia", "12/10/2026 15:48" in nota)
    checar("e declara que ela não foi registrada no lacre", "não registrou a data no lacre" in nota)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
