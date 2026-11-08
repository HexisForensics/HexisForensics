"""
Testes do modulo de WhatsApp por substituicao temporaria do aplicativo.

E o modulo mais invasivo da suite: troca um aplicativo no aparelho
examinado. O que estes testes travam nao e o caminho feliz, e sim o que
acontece quando algo da errado no meio -- porque e ali que um aparelho
fica com a versao antiga instalada:

- NADA e tocado antes de os APKs originais estarem copiados e conferidos;
- a reinstalacao do original e tentada SEMPRE, qualquer que seja a falha;
- aparelho que nao voltou ao estado original e FALHA, mesmo com o banco
  em maos -- nunca "sucesso com ressalva".

O aparelho aqui e um duble. A execucao contra hardware real depende do APK
antigo, que o examinador fornece.
"""

import hashlib
import io
import sqlite3
import sys
import tarfile
import tempfile
import zlib
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core.android.adb_client import ResultadoComando, ResultadoStream  # noqa: E402
from core.android.extractors import whatsapp_downgrade  # noqa: E402
from core.android.extractors.whatsapp_downgrade import (  # noqa: E402
    PACOTE,
    WhatsAppDowngradeExtractor,
)
from services.extraction_service import CHAVES_RESSALVA, indica_ressalva  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar_ab(membros: dict) -> bytes:
    fluxo = io.BytesIO()
    with tarfile.open(fileobj=fluxo, mode="w") as tar:
        for nome, dado in membros.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dado)
            tar.addfile(info, io.BytesIO(dado))
    return b"ANDROID BACKUP\n5\n1\nnone\n" + zlib.compress(fluxo.getvalue())


APKS = {
    "/data/app/com.whatsapp-x/base.apk": b"APK-BASE-ORIGINAL",
    "/data/app/com.whatsapp-x/split_config.arm64_v8a.apk": b"APK-SPLIT-ORIGINAL",
}
VERSAO_ORIGINAL = ("263907900", "2.26.39.79")
VERSAO_LEGADA = ("450817", "2.11.431")


class AparelhoDeMentira:
    """Um ADB que mantem o estado do aplicativo e anota tudo o que lhe pedem."""

    serial = "SERIAL-TESTE"

    def __init__(self, sdk="28", recusa_o_antigo=False, backup_sem_banco=False,
                 restauracao_falha=False, sem_toque_na_tela=False, hash_adulterado=False,
                 banco=b"SQLite format 3\x00conteudo"):
        self.sdk = sdk
        self.instalado = "original"
        self.recusa_o_antigo = recusa_o_antigo
        self.backup_sem_banco = backup_sem_banco
        self.restauracao_falha = restauracao_falha
        self.sem_toque_na_tela = sem_toque_na_tela
        self.hash_adulterado = hash_adulterado
        self.banco = banco
        self.comandos = []

    def _versao(self):
        return {"original": VERSAO_ORIGINAL, "legado": VERSAO_LEGADA}.get(self.instalado)

    def pacote_instalado(self, pacote):
        return self.instalado != "nenhum"

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append(list(argumentos))
        if argumentos[:2] == ["shell", "getprop"]:
            return self.sdk
        if argumentos[:3] == ["shell", "dumpsys", "package"]:
            versao = self._versao()
            return f"versionCode={versao[0]} minSdk=23\n versionName={versao[1]}" if versao else ""
        if argumentos[:3] == ["shell", "pm", "path"]:
            return "\n".join("package:" + caminho for caminho in APKS)
        if argumentos[0] == "shell" and argumentos[1].startswith("sha256sum"):
            caminho = argumentos[1].split("'")[1]
            dado = APKS[caminho] + (b"x" if self.hash_adulterado else b"")
            return hashlib.sha256(dado).hexdigest() + "  " + caminho
        return ""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append(list(argumentos))
        if argumentos[:4] == ["shell", "pm", "uninstall", "-k"]:
            self.instalado = "nenhum"
            return ResultadoComando(0, "Success", "")
        if argumentos[0] == "install":
            if self.recusa_o_antigo:
                return ResultadoComando(1, "", "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")
            self.instalado = "legado"
            return ResultadoComando(0, "Success", "")
        if argumentos[0] == "install-multiple":
            if self.restauracao_falha:
                return ResultadoComando(1, "", "Failure [INSTALL_FAILED_INVALID_APK]")
            self.instalado = "original"
            return ResultadoComando(0, "Success", "")
        return ResultadoComando(0, "", "")

    def stream_binario(self, argumentos, ao_receber_bloco, **_):
        self.comandos.append(list(argumentos))
        caminho = argumentos[1].split("'")[1]
        ao_receber_bloco(APKS[caminho])
        return ResultadoStream(0, "", len(APKS[caminho]))

    def backup_pacote(self, pacote, caminho_saida, timeout=90, chave_valor=False):
        self.comandos.append(["backup", pacote])
        if self.sem_toque_na_tela or self.instalado != "legado":
            return False
        membros = {f"apps/{PACOTE}/_manifest": b"manifesto"}
        if not self.backup_sem_banco:
            membros[f"apps/{PACOTE}/db/msgstore.db"] = self.banco
            membros[f"apps/{PACOTE}/db/wa.db"] = b"SQLite format 3\x00agenda"
            membros[f"apps/{PACOTE}/f/key"] = b"chave"
        else:
            membros[f"apps/{PACOTE}/sp/preferencias.xml"] = b"<map/>"
        Path(caminho_saida).write_bytes(montar_ab(membros))
        return True

    def alterou_o_aparelho(self):
        return any(
            c[:3] == ["shell", "pm", "uninstall"] or c[0] in ("install", "install-multiple")
            for c in self.comandos
        )

    def posicao(self, predicado):
        return next((i for i, c in enumerate(self.comandos) if predicado(c)), -1)


def rodar(tmp: Path, nome: str, **cenario):
    pasta = tmp / nome
    pasta.mkdir()
    aparelho = AparelhoDeMentira(**cenario)
    extrator = WhatsAppDowngradeExtractor(adb_client=aparelho)
    return extrator.executar(pasta), aparelho, pasta


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    apk_legado = tmp / "whatsapp_legado.apk"
    apk_legado.write_bytes(b"APK-ANTIGO")
    whatsapp_downgrade.caminho_do_apk_legado = lambda: apk_legado

    # -----------------------------------------------------------------------
    print("\n[1] Caminho completo: banco obtido, aparelho de volta ao original")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "completo")
    checar("o modulo declara sucesso", resultado.sucesso)
    banco = pasta / "whatsapp_downgrade" / "extraido" / PACOTE / "databases" / "msgstore.db"
    checar("o msgstore.db esta na pasta, com o conteudo do backup",
           banco.is_file() and banco.read_bytes() == aparelho.banco)
    checar("os leitores de conteudo o encontram pelo caminho de sempre",
           len(list(pasta.glob("**/com.whatsapp/databases/msgstore.db"))) == 1
           and len(list(pasta.glob("**/com.whatsapp/databases/wa.db"))) == 1)
    checar("o .ab e preservado como veio",
           (pasta / "whatsapp_downgrade" / f"backup_{PACOTE}.ab").is_file())
    checar("o aparelho terminou com a versao ORIGINAL", aparelho.instalado == "original")
    copia = aparelho.posicao(lambda c: c[0] == "exec-out")
    desinstalacao = aparelho.posicao(lambda c: c[:3] == ["shell", "pm", "uninstall"])
    checar("os APKs originais sao copiados ANTES de qualquer alteracao",
           0 <= copia < desinstalacao)
    checar("e ficam na aquisicao, os dois",
           len(list((pasta / "whatsapp_downgrade" / "apk_original").glob("*.apk"))) == 2)
    metodo = (pasta / "whatsapp_downgrade" / "0_metodo.txt").read_text(encoding="utf-8")
    checar("o SHA-256 do APK antigo entra na aquisicao",
           hashlib.sha256(b"APK-ANTIGO").hexdigest() in metodo)
    checar("e a versao que estava instalada tambem", "2.26.39.79" in metodo)
    diario = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("a substituicao e registrada como ALTERACAO no dispositivo",
           diario.count("ALTERAÇÃO NO DISPOSITIVO EXAMINADO") >= 3
           and "pm uninstall -k" in diario)
    checar("e a reinstalacao do original tambem", "reinstalado na versão original" in diario)
    checar("a resposta do ADB a cada passo e preservada",
           all((pasta / "whatsapp_downgrade" / nome).is_file() for nome in (
               "1_desinstalacao_saida.txt", "2_instalacao_do_antigo_saida.txt",
               "4_reinstalacao_do_original_saida.txt")))

    # -----------------------------------------------------------------------
    print("\n[2] O aparelho recusa a versao antiga: nada obtido, original de volta")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "recusa", recusa_o_antigo=True)
    checar("e FALHA", not resultado.sucesso)
    checar("a mensagem traz o motivo dado pelo aparelho",
           "INSTALL_FAILED_VERSION_DOWNGRADE" in resultado.mensagem)
    checar("e diz que isso NAO e ausencia de mensagens",
           "NÃO significa ausência" in resultado.mensagem)
    checar("o original foi reinstalado mesmo assim", aparelho.instalado == "original")
    checar("nenhum backup foi sequer tentado",
           aparelho.posicao(lambda c: c[0] == "backup") == -1)

    # -----------------------------------------------------------------------
    print("\n[3] Backup sem o banco, ou sem toque na tela: FALHA, e original de volta")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "sem_banco", backup_sem_banco=True)
    checar("backup que nao traz o msgstore.db e FALHA, nunca sucesso",
           not resultado.sucesso and "SEM o banco de mensagens" in resultado.mensagem)
    checar("o original foi reinstalado", aparelho.instalado == "original")

    resultado, aparelho, pasta = rodar(tmp, "sem_toque", sem_toque_na_tela=True)
    checar("confirmacao nao feita na tela e FALHA", not resultado.sucesso)
    checar("e o original foi reinstalado", aparelho.instalado == "original")

    # -----------------------------------------------------------------------
    print("\n[4] A reinstalacao falha: e FALHA em voz alta, MESMO com o banco em maos")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "nao_restaurou", restauracao_falha=True)
    checar("o aparelho ficou com a versao antiga (o cenario do teste)",
           aparelho.instalado == "legado")
    checar("o banco foi obtido",
           (pasta / "whatsapp_downgrade" / "extraido" / PACOTE / "databases"
            / "msgstore.db").is_file())
    checar("e AINDA ASSIM o modulo nao declara sucesso", not resultado.sucesso)
    checar("a mensagem manda NAO ABRIR o WhatsApp",
           "NÃO ABRA O WHATSAPP" in resultado.mensagem)
    checar("e diz onde estao os APKs originais", "apk_original" in resultado.mensagem)
    checar("o desfecho carrega a pendencia como ressalva reconhecida",
           resultado.detalhes.get("restauracao_pendente") is True
           and "restauracao_pendente" in CHAVES_RESSALVA
           and indica_ressalva(resultado.detalhes))
    diario = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro do procedimento diz que a reinstalacao NAO foi confirmada",
           "NÃO foi confirmada" in diario)

    # -----------------------------------------------------------------------
    print("\n[5] Sem copia conferida do original, o aparelho NAO e tocado")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "hash", hash_adulterado=True)
    checar("copia que nao confere com o hash do aparelho impede a execucao",
           not resultado.sucesso and "NÃO confere" in resultado.mensagem)
    checar("e nenhum comando de alteracao foi emitido", not aparelho.alterou_o_aparelho())
    checar("a mensagem diz que o dispositivo nao foi alterado",
           "NÃO foi alterado" in resultado.mensagem)

    # -----------------------------------------------------------------------
    print("\n[6] Android 12 em diante: nao executa, e nao toca no aparelho")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "android12", sdk="31")
    checar("e FALHA, com o motivo", not resultado.sucesso and "Android 12" in resultado.mensagem)
    checar("sem nenhuma alteracao no aparelho", not aparelho.alterou_o_aparelho())

    # -----------------------------------------------------------------------
    print("\n[7] O modulo so roda por escolha expressa, e declara o que altera")
    # -----------------------------------------------------------------------
    checar("e de selecao expressa", WhatsAppDowngradeExtractor.selecao_expressa is True)
    checar("declara as alteracoes ANTES de rodar",
           len(WhatsAppDowngradeExtractor.alteracoes_no_dispositivo) >= 2)
    whatsapp_downgrade.caminho_do_apk_legado = lambda: tmp / "nao_existe.apk"
    extrator = WhatsAppDowngradeExtractor(adb_client=AparelhoDeMentira())
    extrator.device = type("D", (), {"verificar_conexao": lambda self: type(
        "S", (), {"conectado": True, "autorizado": True, "mensagem": "",
                  "seriais_detectados": ["SERIAL-TESTE"]})()})()
    aparelho_ok = extrator.adb
    aparelho_ok.verificar_binario = lambda: (True, "")
    disponivel, motivo = extrator.disponivel()
    checar("sem o APK antigo o modulo se declara indisponivel, dizendo onde po-lo",
           not disponivel and "whatsapp" in motivo.lower() and "nao_existe.apk" in motivo)

    # -----------------------------------------------------------------------
    print("\n[8] O banco extraido e lido pelo leitor de conteudo de sempre")
    # -----------------------------------------------------------------------
    whatsapp_downgrade.caminho_do_apk_legado = lambda: apk_legado
    caminho_banco = tmp / "msgstore_real.db"
    conexao = sqlite3.connect(caminho_banco)
    conexao.executescript(
        "CREATE TABLE jid (_id INTEGER PRIMARY KEY, raw_string TEXT);"
        "CREATE TABLE chat (_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT);"
        "CREATE TABLE message (_id INTEGER PRIMARY KEY, chat_row_id INTEGER, from_me INTEGER,"
        " sender_jid_row_id INTEGER, timestamp INTEGER, message_type INTEGER, text_data TEXT);"
        "INSERT INTO jid VALUES (1, '5511911112222@s.whatsapp.net');"
        "INSERT INTO chat VALUES (1, 1, NULL);"
        "INSERT INTO message VALUES (1, 1, 0, 0, 1756000000000, 0, 'mensagem do downgrade');"
    )
    conexao.commit()
    conexao.close()
    resultado, aparelho, pasta = rodar(tmp, "leitura", banco=caminho_banco.read_bytes())
    from services.relatorio_service import levantar_artefatos  # noqa: E402

    artefato = next(a for a in levantar_artefatos(pasta) if a.chave == "whatsapp")
    checar("o artefato WhatsApp e localizado na aquisicao", artefato.presente)
    checar("e a mensagem e lida",
           artefato.total == 1
           and "mensagem do downgrade" in str(artefato.resultado.registros[0].campos))

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
