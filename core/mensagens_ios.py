"""
Leitores dos bancos do iPhone: mensagens (iMessage e SMS), chamadas,
agenda e WhatsApp.

Cada um devolve o mesmo `ResultadoNormalizacao` dos leitores do Android —
daí em diante caderno, planilha, PDF de conversas e procedência funcionam
sem saber de que plataforma o dado veio.

Valem as regras de `core.sqlite_forense`: o banco é aberto sobre cópia,
com o `-wal` junto, e banco que não abre ou esquema desconhecido viram
recusa declarada, nunca "nenhum registro".

**Datas da Apple.** O iOS conta o tempo a partir de 01/01/2001, não de
1970. O `sms.db` grava em nanossegundos (iOS 11 em diante) ou segundos
(antes); os demais, em segundos com fração. A grandeza decide, como no
Android.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.normalizacao import (
    Descarte,
    Registro,
    ResultadoNormalizacao,
    nome_do_fuso,
)
from core.sqlite_forense import abrir

# 01/01/2001 00:00:00 UTC, em segundos desde 1970.
EPOCA_APPLE = 978307200

COLUNAS_SMS = ("momento", "direcao", "numero", "conversa", "servico", "conteudo", "anexo", "lida")
COLUNAS_CHAMADAS = ("momento", "direcao", "numero", "contato", "duracao_segundos", "servico")
COLUNAS_CONTATOS = ("contato", "numero", "email")
COLUNAS_WHATSAPP = ("momento", "direcao", "numero", "contato", "conversa", "tipo", "conteudo", "anexo")

SUFIXO_GRUPO_WHATSAPP = "@g.us"

# Tipos de mensagem do WhatsApp para iOS que se conhecem com segurança.
# Código fora desta lista é apresentado como código — não se adivinha.
TIPOS_WHATSAPP_IOS = {
    0: "texto",
    1: "imagem",
    2: "vídeo",
    3: "áudio",
    4: "contato",
    5: "localização",
    7: "link",
    8: "documento",
    11: "GIF",
    15: "figurinha",
}

# Propriedades da tabela `ABMultiValue` da agenda do iOS.
PROPRIEDADE_TELEFONE = 3
PROPRIEDADE_EMAIL = 4


def momento_apple(valor, fuso=None) -> Optional[datetime]:
    """Data da Apple (segundos ou nanossegundos desde 2001) em data e hora."""
    if valor in (None, "", 0, "0"):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if numero <= 0:
        return None
    if numero > 1e11:  # nanossegundos
        numero /= 1e9
    try:
        momento = datetime.fromtimestamp(numero + EPOCA_APPLE, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return momento.astimezone(fuso) if fuso is not None else momento


def texto_de_attributed_body(blob) -> str:
    """
    O texto guardado no `attributedBody` do `sms.db`.

    Do iOS 16 em diante a coluna `text` vem vazia em parte das mensagens, e
    o texto mora só no `attributedBody`, um `NSAttributedString` serializado
    (typedstream). O texto é a primeira cadeia depois do marcador
    `NSString`, precedida do comprimento.
    """
    if not blob:
        return ""
    try:
        conteudo = bytes(blob)
    except (TypeError, ValueError):
        return ""
    posicao = conteudo.find(b"NSString")
    if posicao < 0:
        return ""
    resto = conteudo[posicao + len(b"NSString"):]
    marcador = resto.find(b"+")
    if marcador < 0 or marcador + 1 >= len(resto):
        return ""
    resto = resto[marcador + 1:]
    tamanho, inicio = resto[0], 1
    if tamanho == 0x81:
        tamanho, inicio = int.from_bytes(resto[1:3], "little"), 3
    elif tamanho == 0x82:
        tamanho, inicio = int.from_bytes(resto[1:4], "little"), 4
    return resto[inicio:inicio + tamanho].decode("utf-8", errors="replace")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    return str(valor)


def _colunas(banco, tabela: str) -> set:
    try:
        return {linha[1] for linha in banco.consultar(f"PRAGMA table_info({tabela})")}
    except Exception:
        return set()


def _opcional(colunas: set, prefixo: str, coluna: str, apelido: str) -> str:
    """`prefixo.coluna AS apelido`, ou `NULL AS apelido` se a versão não a tem."""
    return f"{prefixo}.{coluna} AS {apelido}" if coluna in colunas else f"NULL AS {apelido}"


def resultado_vazio(tipo: str, arquivo: str, fuso) -> ResultadoNormalizacao:
    """Resultado sem leitura — quem chama diz, em `significado_do_vazio`, por quê."""
    return _resultado(tipo, Path(arquivo), arquivo, fuso)


def _resultado(tipo: str, caminho: Path, arquivo: str, fuso) -> ResultadoNormalizacao:
    return ResultadoNormalizacao(
        tipo=tipo,
        arquivo_de_origem=arquivo or Path(caminho).name,
        fuso_declarado=nome_do_fuso(fuso),
        significado_do_vazio=(
            "O banco do iPhone foi lido e não tem nenhum registro desta natureza. O backup "
            "não traz o que foi apagado, e isso não prova que nunca tenha existido."
        ),
    )


def _recusar(resultado: ResultadoNormalizacao, motivo: str) -> ResultadoNormalizacao:
    resultado.acesso_negado = True
    resultado.trecho_da_recusa = motivo
    return resultado


def _esquema_desconhecido(banco, esperadas) -> str:
    return (
        f"O banco abriu, mas não tem as tabelas esperadas ({', '.join(esperadas)}). Nada se "
        "pode afirmar a partir deste arquivo. Tabelas encontradas: "
        + (", ".join(banco.tabelas) or "nenhuma")
    )


# ---------------------------------------------------------------------------
# Mensagens: sms.db (iMessage e SMS)
# ---------------------------------------------------------------------------
def ler_sms(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "") -> ResultadoNormalizacao:
    resultado = _resultado("sms", caminho, arquivo, fuso)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("message", "handle"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("message", "handle")))

        colunas = _colunas(banco, "message")
        com_conversa = banco.tem_tabelas("chat", "chat_message_join")
        consulta = f"""
            SELECT m.ROWID AS id, m.date AS momento, m.is_from_me AS de_mim,
                   m.text AS texto,
                   {_opcional(colunas, 'm', 'attributedBody', 'corpo')},
                   {_opcional(colunas, 'm', 'service', 'servico')},
                   {_opcional(colunas, 'm', 'is_read', 'lida')},
                   h.id AS interlocutor,
                   {'c.chat_identifier' if com_conversa else 'NULL'} AS conversa,
                   {'c.display_name' if com_conversa else 'NULL'} AS nome_do_grupo
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            {'LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID '
             'LEFT JOIN chat c ON c.ROWID = cmj.chat_id' if com_conversa else ''}
            ORDER BY m.date
        """
        try:
            linhas = banco.consultar(consulta)
        except Exception as erro:
            return _recusar(resultado, f"A consulta às mensagens falhou: {erro}. Nada foi lido.")

        anexos: dict = {}
        if banco.tem_tabelas("attachment", "message_attachment_join"):
            try:
                for linha in banco.consultar(
                    "SELECT j.message_id AS id, a.filename AS arquivo, a.mime_type AS tipo, "
                    "a.transfer_name AS nome FROM message_attachment_join j "
                    "JOIN attachment a ON a.ROWID = j.attachment_id"
                ):
                    descricao = _texto(linha["nome"]) or _texto(linha["arquivo"]) or "(sem nome)"
                    if linha["tipo"]:
                        descricao += f" [{_texto(linha['tipo'])}]"
                    anexos.setdefault(linha["id"], []).append(descricao)
            except Exception:
                pass

        vistos = set()
        for linha in linhas:
            identificador = linha["id"]
            if identificador in vistos:
                continue
            vistos.add(identificador)
            conteudo = _texto(linha["texto"]) or texto_de_attributed_body(linha["corpo"])
            anexo = "; ".join(anexos.get(identificador, []))
            momento = momento_apple(linha["momento"], fuso)
            if momento is None and not conteudo and not anexo:
                resultado.descartes.append(Descarte(
                    identificador or 0, f"registro {identificador} da tabela message",
                    "sem data, sem texto e sem anexo — nada a apresentar",
                ))
                continue
            de_mim = str(linha["de_mim"]) == "1"
            conversa = _texto(linha["nome_do_grupo"]) or _texto(linha["conversa"])
            resultado.registros.append(Registro(
                tipo="sms",
                campos={
                    "direcao": "Enviada" if de_mim else "Recebida",
                    "numero": _texto(linha["interlocutor"]) or _texto(linha["conversa"])
                    or "(sem número)",
                    "conversa": conversa or _texto(linha["interlocutor"]) or "(sem identificação)",
                    "servico": _texto(linha["servico"]),
                    "conteudo": conteudo,
                    "anexo": anexo,
                    "lida": "" if de_mim else {"1": "Sim", "0": "Não"}.get(
                        _texto(linha["lida"]), "(não informado)"),
                },
                momento=momento,
                arquivo_de_origem=resultado.arquivo_de_origem,
                linha_de_origem=identificador or 0,
            ))
    return resultado


# ---------------------------------------------------------------------------
# Chamadas: CallHistory.storedata
# ---------------------------------------------------------------------------
def _servico_da_chamada(provedor: str, tipo) -> str:
    provedor = provedor or ""
    if "whatsapp" in provedor.lower():
        return "WhatsApp"
    if str(tipo) == "8":
        return "FaceTime vídeo"
    if str(tipo) == "16":
        return "FaceTime áudio"
    if "telephony" in provedor.lower() or str(tipo) == "1":
        return "Telefone"
    return provedor or "(não informado)"


def ler_chamadas(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "") -> ResultadoNormalizacao:
    resultado = _resultado("chamada", caminho, arquivo, fuso)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ZCALLRECORD"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("ZCALLRECORD",)))
        colunas = _colunas(banco, "ZCALLRECORD")
        consulta = f"""
            SELECT c.Z_PK AS id, c.ZADDRESS AS numero, c.ZDATE AS momento,
                   c.ZDURATION AS duracao,
                   {_opcional(colunas, 'c', 'ZORIGINATED', 'efetuada')},
                   {_opcional(colunas, 'c', 'ZANSWERED', 'atendida')},
                   {_opcional(colunas, 'c', 'ZCALLTYPE', 'tipo')},
                   {_opcional(colunas, 'c', 'ZSERVICE_PROVIDER', 'provedor')},
                   {_opcional(colunas, 'c', 'ZNAME', 'nome')}
            FROM ZCALLRECORD c ORDER BY c.ZDATE
        """
        try:
            linhas = banco.consultar(consulta)
        except Exception as erro:
            return _recusar(resultado, f"A consulta às chamadas falhou: {erro}. Nada foi lido.")
        for linha in linhas:
            if str(linha["efetuada"]) == "1":
                direcao = "Efetuada"
            elif str(linha["atendida"]) == "1":
                direcao = "Recebida"
            else:
                direcao = "Recebida, não atendida"
            try:
                duracao = str(int(round(float(linha["duracao"] or 0))))
            except (TypeError, ValueError):
                duracao = _texto(linha["duracao"])
            resultado.registros.append(Registro(
                tipo="chamada",
                campos={
                    "direcao": direcao,
                    "numero": _texto(linha["numero"]) or "(número não informado)",
                    "contato": _texto(linha["nome"]),
                    "duracao_segundos": duracao,
                    "servico": _servico_da_chamada(_texto(linha["provedor"]), linha["tipo"]),
                },
                momento=momento_apple(linha["momento"], fuso),
                arquivo_de_origem=resultado.arquivo_de_origem,
                linha_de_origem=linha["id"] or 0,
            ))
    return resultado


# ---------------------------------------------------------------------------
# Agenda: AddressBook.sqlitedb
# ---------------------------------------------------------------------------
def ler_contatos(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "") -> ResultadoNormalizacao:
    resultado = _resultado("contato", caminho, arquivo, fuso)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ABPerson", "ABMultiValue"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("ABPerson", "ABMultiValue")))
        try:
            pessoas = banco.consultar(
                "SELECT ROWID AS id, First AS nome, Last AS sobrenome, Organization AS empresa "
                "FROM ABPerson ORDER BY ROWID"
            )
            valores = banco.consultar(
                "SELECT record_id AS id, property AS propriedade, value AS valor "
                "FROM ABMultiValue WHERE property IN (?, ?)",
                (PROPRIEDADE_TELEFONE, PROPRIEDADE_EMAIL),
            )
        except Exception as erro:
            return _recusar(resultado, f"A consulta à agenda falhou: {erro}. Nada foi lido.")

        telefones, emails = {}, {}
        for linha in valores:
            destino = telefones if linha["propriedade"] == PROPRIEDADE_TELEFONE else emails
            if linha["valor"]:
                destino.setdefault(linha["id"], []).append(_texto(linha["valor"]))

        for pessoa in pessoas:
            nome = " ".join(p for p in (_texto(pessoa["nome"]), _texto(pessoa["sobrenome"])) if p)
            nome = nome or _texto(pessoa["empresa"]) or "(sem nome)"
            email = "; ".join(emails.get(pessoa["id"], []))
            for numero in telefones.get(pessoa["id"], []) or ["(sem número)"]:
                resultado.registros.append(Registro(
                    tipo="contato",
                    campos={"contato": nome, "numero": numero, "email": email},
                    momento=None,
                    arquivo_de_origem=resultado.arquivo_de_origem,
                    linha_de_origem=pessoa["id"] or 0,
                ))
    return resultado


# ---------------------------------------------------------------------------
# WhatsApp: ChatStorage.sqlite
# ---------------------------------------------------------------------------
def _numero_do_jid(jid: str) -> str:
    if not jid or "@" not in jid:
        return jid or ""
    usuario, dominio = jid.split("@", 1)
    return usuario if dominio == "s.whatsapp.net" else ""


def _coordenadas(latitude, longitude):
    """`(lat, lon)` válidas, ou `None`. 0,0 é campo vazio, não lugar."""
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if latitude == 0 and longitude == 0:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def ler_whatsapp(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "") -> ResultadoNormalizacao:
    resultado = _resultado("whatsapp", caminho, arquivo, fuso)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ZWAMESSAGE", "ZWACHATSESSION"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("ZWAMESSAGE", "ZWACHATSESSION")))
        colunas = _colunas(banco, "ZWAMESSAGE")
        com_membro = banco.tem_tabelas("ZWAGROUPMEMBER") and "ZGROUPMEMBER" in colunas
        com_midia = banco.tem_tabelas("ZWAMEDIAITEM") and "ZMEDIAITEM" in colunas
        colunas_midia = _colunas(banco, "ZWAMEDIAITEM") if com_midia else set()
        com_coordenadas = {"ZLATITUDE", "ZLONGITUDE"} <= set(colunas_midia)
        consulta = f"""
            SELECT m.Z_PK AS id, m.ZMESSAGEDATE AS momento, m.ZISFROMME AS de_mim,
                   m.ZTEXT AS texto, m.ZMESSAGETYPE AS tipo,
                   {_opcional(colunas, 'm', 'ZPUSHNAME', 'apelido')},
                   {_opcional(colunas, 'm', 'ZGROUPEVENTTYPE', 'evento')},
                   s.ZCONTACTJID AS jid_conversa, s.ZPARTNERNAME AS nome_da_conversa,
                   {'g.ZMEMBERJID' if com_membro else 'NULL'} AS jid_membro,
                   {'g.ZCONTACTNAME' if com_membro else 'NULL'} AS nome_do_membro,
                   {'mi.ZMEDIALOCALPATH' if com_midia else 'NULL'} AS midia,
                   {'mi.ZTITLE' if com_midia else 'NULL'} AS legenda,
                   {'mi.ZLATITUDE' if com_coordenadas else 'NULL'} AS latitude,
                   {'mi.ZLONGITUDE' if com_coordenadas else 'NULL'} AS longitude
            FROM ZWAMESSAGE m
            LEFT JOIN ZWACHATSESSION s ON s.Z_PK = m.ZCHATSESSION
            {'LEFT JOIN ZWAGROUPMEMBER g ON g.Z_PK = m.ZGROUPMEMBER' if com_membro else ''}
            {'LEFT JOIN ZWAMEDIAITEM mi ON mi.Z_PK = m.ZMEDIAITEM' if com_midia else ''}
            ORDER BY m.ZMESSAGEDATE
        """
        try:
            linhas = banco.consultar(consulta)
        except Exception as erro:
            return _recusar(resultado, f"A consulta às mensagens falhou: {erro}. Nada foi lido.")

        for linha in linhas:
            identificador = linha["id"]
            jid_conversa = _texto(linha["jid_conversa"])
            em_grupo = jid_conversa.endswith(SUFIXO_GRUPO_WHATSAPP)
            de_mim = str(linha["de_mim"]) == "1"
            try:
                codigo = int(linha["tipo"])
                tipo = TIPOS_WHATSAPP_IOS.get(codigo, f"(tipo {codigo} não reconhecido)")
            except (TypeError, ValueError):
                tipo = "(tipo não informado)"
            conteudo = _texto(linha["texto"]) or _texto(linha["legenda"])
            mapa = ""
            try:
                evento = int(linha["evento"] or 0)
            except (TypeError, ValueError):
                evento = 0
            if evento:
                # Registro que o próprio WhatsApp gera (aviso, criação de grupo):
                # o texto, quando há, é dado técnico (JSON), e o "apelido" não é
                # nome de ninguém. Visto no iPhone 11 real em 31/10/2026.
                tipo = "evento do WhatsApp"
                conteudo = (f"(registro gerado pelo próprio WhatsApp, código de evento "
                            f"{evento}; não é mensagem digitada)")
            elif tipo == "localização":
                lugar = _coordenadas(linha["latitude"], linha["longitude"])
                if lugar:
                    mapa = f"https://www.google.com/maps?q={lugar[0]:.6f},{lugar[1]:.6f}"
                    conteudo = " — ".join(p for p in (
                        f"(localização) {lugar[0]:.6f}, {lugar[1]:.6f}", conteudo) if p)
            if not conteudo and tipo.startswith("(tipo") and not _texto(linha["midia"]):
                conteudo = f"{tipo[:-1]}; sem texto nem mídia)"
            if not conteudo and tipo != "texto":
                conteudo = f"({tipo})"
            momento = momento_apple(linha["momento"], fuso)
            if momento is None and not conteudo:
                resultado.descartes.append(Descarte(
                    identificador or 0, f"registro {identificador} da tabela ZWAMESSAGE",
                    "sem data e sem conteúdo — nada a apresentar",
                ))
                continue

            # Em grupo, o interlocutor é quem enviou, não o grupo.
            if evento:
                jid_interlocutor, contato = "", ""
                conversa = (_texto(linha["nome_da_conversa"]) or jid_conversa) if em_grupo \
                    else jid_conversa
            elif em_grupo:
                jid_interlocutor = "" if de_mim else _texto(linha["jid_membro"])
                contato = "" if de_mim else (
                    _texto(linha["nome_do_membro"]) or _texto(linha["apelido"]))
                conversa = _texto(linha["nome_da_conversa"]) or jid_conversa
            else:
                jid_interlocutor = jid_conversa
                contato = _texto(linha["nome_da_conversa"])
                conversa = jid_conversa
            resultado.registros.append(Registro(
                tipo="whatsapp",
                campos={
                    "direcao": "Sistema" if evento else ("Enviada" if de_mim else "Recebida"),
                    "numero": _numero_do_jid(jid_interlocutor),
                    "contato": contato,
                    "conversa": conversa or "(sem identificação)",
                    "tipo": tipo,
                    "conteudo": conteudo,
                    "anexo": _texto(linha["midia"]),
                    **({"mapa": mapa} if mapa else {}),
                },
                momento=momento,
                arquivo_de_origem=resultado.arquivo_de_origem,
                linha_de_origem=identificador or 0,
            ))
    return resultado


LEITORES = {
    "sms": ler_sms,
    "chamadas": ler_chamadas,
    "contatos": ler_contatos,
    "whatsapp": ler_whatsapp,
}
