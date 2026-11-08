"""
Testes da coleta por aplicativo agente.

O agente e a via de SMS e chamadas no Android 12 em diante, e instala um
aplicativo no aparelho examinado. O que estes testes travam:

- o agente e desinstalado SEMPRE, inclusive quando a coleta falha no meio;
- agente que ficou instalado e FALHA, mesmo com os dados em maos;
- fonte que o sistema RECUSOU ao agente nunca vira "nenhum registro";
- o APK empregado entra na aquisicao com o SHA-256.

O aparelho aqui e um duble. A execucao real foi feita contra um moto x4
(Android 9) e contra o emulador com Android 13.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from core import agente_android  # noqa: E402
from core.android.adb_client import ResultadoComando, ResultadoStream  # noqa: E402
from core.android.extractors import agente as modulo  # noqa: E402
from core.android.extractors.agente import AgenteExtractor  # noqa: E402
from core.hashing import calcular_sha256  # noqa: E402
from services.extraction_service import indica_ressalva  # noqa: E402
from services.relatorio_service import levantar_artefatos  # noqa: E402

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def linhas(*objetos) -> bytes:
    return ("\n".join(json.dumps(o, ensure_ascii=False) for o in objetos) + "\n").encode("utf-8")


ARQUIVOS_DO_APARELHO = {
    "contatos.jsonl": linhas({"_id": 7, "display_name": "Fulano", "data1": "+55 11 91111-2222"}),
    "chamadas.jsonl": linhas(
        {"_id": 1, "number": "11911112222", "type": 2, "date": 1756000000000, "duration": 65,
         "name": None},
        {"_id": 2, "number": "11933334444", "type": 3, "date": 1756000100000, "duration": 0,
         "name": "Beltrano"},
    ),
    "sms.jsonl": linhas(
        {"_id": 1, "address": "11911112222", "type": 1, "read": 1, "date": 1756000200000,
         "body": "mensagem lida pelo agente"},
    ) + b"isto nao e json\n",
    "mms.jsonl": linhas({"_id": 5, "msg_box": 1, "read": 0, "date": 1756000300, "sub": "Foto"}),
    "mms_partes.jsonl": linhas(
        {"mid": 5, "ct": "text/plain", "text": "olha isso"},
        {"mid": 5, "ct": "image/jpeg", "name": "foto.jpg"},
    ),
    "mms_enderecos.jsonl": linhas(
        {"_mms_id": "5", "type": 137, "address": "+5511955556666"},
        {"_mms_id": "5", "type": 151, "address": "insert-address-token"},
    ),
}


def estado(recusadas=()):
    fontes = []
    for nome in ("contatos", "chamadas", "sms", "mms", "mms_partes", "mms_enderecos"):
        recusada = nome in recusadas
        conteudo = ARQUIVOS_DO_APARELHO[nome + ".jsonl"]
        fontes.append({
            "nome": nome, "uri": "content://" + nome,
            "registros": 0 if recusada else conteudo.count(b"\n{") + conteudo.startswith(b"{"),
            "provedor_respondeu": not recusada,
            "erro": "java.lang.SecurityException: Permission Denial" if recusada else None,
        })
    return json.dumps({"agente": agente_android.PACOTE, "fontes": fontes}).encode("utf-8")


class AparelhoDeMentira:
    serial = "SERIAL-TESTE"

    def __init__(self, recusa_instalacao=False, nunca_conclui=False, nao_desinstala=False,
                 recusadas=(), tudo_vazio=False):
        self.instalado = False
        self.recusa_instalacao = recusa_instalacao
        self.nunca_conclui = nunca_conclui
        self.nao_desinstala = nao_desinstala
        self.recusadas = recusadas
        self.tudo_vazio = tudo_vazio
        self.executou = False
        self.comandos = []

    def _arquivo(self, nome: str) -> bytes:
        if nome == "estado.json":
            if self.nunca_conclui or not self.executou:
                return b""
            if self.tudo_vazio:
                dados = json.loads(estado())
                for fonte in dados["fontes"]:
                    fonte["registros"] = 0
                return json.dumps(dados).encode("utf-8")
            return estado(self.recusadas)
        if self.tudo_vazio or nome[: -len(".jsonl")] in self.recusadas:
            return b""
        return ARQUIVOS_DO_APARELHO[nome]

    def pacote_instalado(self, pacote):
        return self.instalado

    def executar(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append(list(argumentos))
        if argumentos[0] == "exec-out" and "run-as" in argumentos[1]:
            return self._arquivo(argumentos[1].split("files/")[1]).decode("utf-8")
        return ""

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append(list(argumentos))
        if argumentos[0] == "install":
            if self.recusa_instalacao:
                return ResultadoComando(1, "", "Failure [INSTALL_FAILED_VERIFICATION_FAILURE]")
            self.instalado = True
            return ResultadoComando(0, "Success", "")
        if argumentos[0] == "uninstall":
            if not self.nao_desinstala:
                self.instalado = False
            return ResultadoComando(0, "Success" if not self.nao_desinstala else "Failure", "")
        if argumentos[:3] == ["shell", "am", "start"]:
            self.executou = True
        return ResultadoComando(0, "", "")

    def stream_binario(self, argumentos, ao_receber_bloco, **_):
        self.comandos.append(list(argumentos))
        dado = self._arquivo(argumentos[1].split("files/")[1])
        ao_receber_bloco(dado)
        return ResultadoStream(0, "", len(dado))

    def desinstalou(self):
        return any(c[0] == "uninstall" for c in self.comandos)


def rodar(tmp: Path, nome: str, **cenario):
    pasta = tmp / nome
    pasta.mkdir()
    aparelho = AparelhoDeMentira(**cenario)
    return AgenteExtractor(adb_client=aparelho).executar(pasta), aparelho, pasta


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    apk = tmp / "forensic_agente.apk"
    apk.write_bytes(b"APK-DO-AGENTE")
    modulo.caminho_do_apk = lambda: apk
    modulo.TEMPO_DA_COLETA = 3  # o cenario "nunca conclui" nao pode custar tres minutos

    # -----------------------------------------------------------------------
    print("\n[1] Caminho completo: dados obtidos, agente removido")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "completo")
    checar("o modulo declara sucesso", resultado.sucesso)
    checar("a mensagem conta o que veio de cada fonte",
           "1 número(s) de agenda" in resultado.mensagem and "2 chamadas" in resultado.mensagem
           and "1 SMS" in resultado.mensagem)
    checar("o agente foi desinstalado, e isso foi conferido",
           not aparelho.instalado and "remoção foi conferida" in resultado.mensagem)
    checar("os arquivos do agente estao na aquisicao",
           all((pasta / "agente" / nome).is_file() for nome in agente_android.ARQUIVOS))
    registro = (pasta / "agente" / "0_agente.txt").read_text(encoding="utf-8")
    checar("o SHA-256 do APK empregado entra na aquisicao",
           hashlib.sha256(b"APK-DO-AGENTE").hexdigest() in registro)
    hashes = (pasta / "agente" / "hashes_na_aquisicao.txt").read_text(encoding="utf-8")
    checar("o hash de cada arquivo e calculado NA gravacao e confere",
           calcular_sha256(pasta / "agente" / "sms.jsonl") in hashes)
    diario = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("instalar e desinstalar sao registrados como ALTERACAO no dispositivo",
           diario.count("ALTERAÇÃO NO DISPOSITIVO EXAMINADO") == 2
           and "desinstalado" in diario)
    checar("a resposta do ADB a cada passo e preservada",
           all((pasta / "agente" / nome).is_file() for nome in (
               "1_instalacao_saida.txt", "2_execucao_saida.txt", "3_desinstalacao_saida.txt")))

    # -----------------------------------------------------------------------
    print("\n[2] Os leitores entregam o mesmo formato das outras vias")
    # -----------------------------------------------------------------------
    artefatos = {a.chave: a for a in levantar_artefatos(pasta)}
    chamadas = artefatos["chamada_agente"].resultado.registros
    checar("chamadas: sentido e duracao interpretados",
           [c.campos["direcao"] for c in chamadas] == ["Efetuada", "Perdida"]
           and chamadas[0].campos["duracao_segundos"] == "65")
    checar("chamada sem nome diz que o nome nao consta, sem inventar",
           "não consta" in chamadas[0].campos["contato"]
           and chamadas[1].campos["contato"] == "Beltrano")
    sms = artefatos["sms_agente"].resultado
    checar("SMS lido, com data e a linha de origem",
           sms.total == 1 and sms.registros[0].momento is not None
           and sms.registros[0].linha_de_origem == 1)
    checar("linha que nao e JSON vira descarte CONTADO, nao some",
           len(sms.descartes) == 1 and "JSON" in sms.descartes[0].motivo)
    mms = artefatos["mms_agente"].resultado.registros[0]
    checar("MMS: texto das partes, anexo nomeado e remetente dos enderecos",
           mms.campos["conteudo"] == "olha isso" and "foto.jpg" in mms.campos["anexo"]
           and mms.campos["numero"] == "+5511955556666")
    checar("contato lido", artefatos["contato_agente"].resultado.registros[0].campos["contato"]
           == "Fulano")

    # A consulta direta recusada, ao lado dos mesmos dados vindos pelo agente:
    # o documento nao pode dizer "nao se obteve dado algum" e mostrar o dado.
    (pasta / "sms").mkdir()
    (pasta / "sms" / "sms_todas.txt").write_text(
        "Error while accessing provider:sms\njava.lang.SecurityException: Permission Denial",
        encoding="utf-8")
    direto = {a.chave: a for a in levantar_artefatos(pasta)}["sms"]
    checar("a consulta direta recusada continua sendo dita como RECUSADA",
           direto.resultado.acesso_negado and "recusada" in direto.explicacao)
    checar("mas aponta a via por onde os registros vieram",
           "via aplicativo agente" in direto.explicacao
           and "Não se obteve dado algum" not in direto.explicacao)
    (pasta / "sms" / "sms_todas.txt").unlink()

    # -----------------------------------------------------------------------
    print("\n[3] Fonte RECUSADA ao agente nunca vira 'nenhum registro'")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "recusa_sms", recusadas=("sms",))
    checar("o modulo ainda obtem as demais fontes", resultado.sucesso)
    checar("a mensagem diz que o SMS foi RECUSADO",
           "RECUSADO" in resultado.mensagem and "SMS" in resultado.mensagem)
    checar("e o desfecho carrega a ressalva",
           resultado.detalhes.get("acesso_negado") is True and indica_ressalva(resultado.detalhes))
    sms = {a.chave: a for a in levantar_artefatos(pasta)}["sms_agente"].resultado
    checar("o leitor reporta ACESSO NEGADO, com o erro do sistema",
           sms.acesso_negado and "SecurityException" in sms.trecho_da_recusa)
    checar("e a explicacao do vazio fala em recusa, nao em ausencia",
           "RECUSOU" in sms.explicacao_do_vazio)

    resultado, aparelho, pasta = rodar(tmp, "tudo_recusado",
                                      recusadas=("contatos", "chamadas", "sms", "mms"))
    checar("tudo recusado e FALHA, nunca sucesso", not resultado.sucesso)
    checar("e o agente foi removido mesmo assim", not aparelho.instalado)

    resultado, aparelho, pasta = rodar(tmp, "vazio", tudo_vazio=True)
    checar("provedores respondendo vazio: FALHA, dizendo que responderam sem registro",
           not resultado.sucesso and "respondeu sem registro" in resultado.mensagem)

    # -----------------------------------------------------------------------
    print("\n[4] Falha no meio: o agente e removido de qualquer jeito")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "nao_conclui", nunca_conclui=True)
    checar("coleta que nao termina e FALHA", not resultado.sucesso)
    checar("com a ressalva de que isso nao e ausencia de dados",
           "NÃO significa ausência" in resultado.mensagem)
    checar("e o agente foi desinstalado", aparelho.desinstalou() and not aparelho.instalado)

    resultado, aparelho, pasta = rodar(tmp, "recusa_instalacao", recusa_instalacao=True)
    checar("instalacao recusada e FALHA, com o motivo do aparelho",
           not resultado.sucesso and "INSTALL_FAILED" in resultado.mensagem)
    checar("e nada ficou instalado", not aparelho.instalado)

    # -----------------------------------------------------------------------
    print("\n[5] Agente que FICOU no aparelho e falha em voz alta")
    # -----------------------------------------------------------------------
    resultado, aparelho, pasta = rodar(tmp, "nao_desinstala", nao_desinstala=True)
    checar("os dados vieram", (pasta / "agente" / "sms.jsonl").stat().st_size > 0)
    checar("e AINDA ASSIM o modulo nao declara sucesso", not resultado.sucesso)
    checar("a mensagem diz que o agente continua instalado",
           "CONTINUA INSTALADO" in resultado.mensagem)
    checar("o desfecho carrega a pendencia", resultado.detalhes.get("restauracao_pendente") is True)
    diario = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro diz que a desinstalacao NAO foi confirmada",
           "NÃO foi confirmada" in diario)

    # -----------------------------------------------------------------------
    print("\n[6] O modulo so roda por escolha expressa, e o APK de verdade acompanha a suite")
    # -----------------------------------------------------------------------
    checar("e de selecao expressa", AgenteExtractor.selecao_expressa is True)
    checar("declara a alteracao ANTES de rodar",
           len(AgenteExtractor.alteracoes_no_dispositivo) >= 1)
    apk_real = RAIZ_PROJETO / "assets" / "agente" / "forensic_agente.apk"
    checar("o APK do agente esta no repositorio", apk_real.is_file())
    registrado = (apk_real.parent / "forensic_agente.apk.sha256").read_text(encoding="utf-8")
    checar("e confere com o SHA-256 publicado ao lado dele",
           calcular_sha256(apk_real) in registrado)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
