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

from core.idioma import traduzir
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
    0: "wa_tipo_texto",
    1: "wa_tipo_imagem",
    2: "wa_tipo_video",
    3: "wa_tipo_audio",
    4: "wa_tipo_contato",
    5: "wa_tipo_localizacao",
    7: "ios_wa_link",
    8: "wa_tipo_documento",
    11: "wa_tipo_gif",
    15: "wa_tipo_figurinha",
}
# Código do tipo cujo tratamento no código depende de constante, não do rótulo.
TIPO_WA_TEXTO = 0
TIPO_WA_LOCALIZACAO = 5

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


def _lida_ios(valor, idioma=None) -> str:
    chave = {"1": "nm_sim", "0": "nm_nao"}.get(_texto(valor), "nm_nao_informado")
    return traduzir(chave, idioma)


def _colunas(banco, tabela: str) -> set:
    try:
        return {linha[1] for linha in banco.consultar(f"PRAGMA table_info({tabela})")}
    except Exception:
        return set()


def _opcional(colunas: set, prefixo: str, coluna: str, apelido: str) -> str:
    """`prefixo.coluna AS apelido`, ou `NULL AS apelido` se a versão não a tem."""
    return f"{prefixo}.{coluna} AS {apelido}" if coluna in colunas else f"NULL AS {apelido}"


def resultado_vazio(tipo: str, arquivo: str, fuso, idioma=None) -> ResultadoNormalizacao:
    """Resultado sem leitura — quem chama diz, em `significado_do_vazio`, por quê."""
    return _resultado(tipo, Path(arquivo), arquivo, fuso, idioma)


def _resultado(tipo: str, caminho: Path, arquivo: str, fuso, idioma=None) -> ResultadoNormalizacao:
    return ResultadoNormalizacao(
        tipo=tipo,
        arquivo_de_origem=arquivo or Path(caminho).name,
        fuso_declarado=nome_do_fuso(fuso, idioma),
        significado_do_vazio=traduzir("ios_vazio", idioma),
        idioma=idioma,
    )


def _recusar(resultado: ResultadoNormalizacao, motivo: str) -> ResultadoNormalizacao:
    resultado.acesso_negado = True
    resultado.trecho_da_recusa = motivo
    return resultado


def _esquema_desconhecido(banco, esperadas, idioma=None) -> str:
    return traduzir(
        "ios_esquema", idioma,
        esperadas=", ".join(esperadas),
        tabelas=(", ".join(banco.tabelas) or traduzir("wa_nenhuma", idioma)),
    )


# ---------------------------------------------------------------------------
# Mensagens: sms.db (iMessage e SMS)
# ---------------------------------------------------------------------------
def ler_sms(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "",
            idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("sms", caminho, arquivo, fuso, idioma)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("message", "handle"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("message", "handle"), idioma))

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
            return _recusar(resultado, traduzir("ios_consulta_mensagens", idioma, erro=erro))

        anexos: dict = {}
        if banco.tem_tabelas("attachment", "message_attachment_join"):
            try:
                for linha in banco.consultar(
                    "SELECT j.message_id AS id, a.filename AS arquivo, a.mime_type AS tipo, "
                    "a.transfer_name AS nome FROM message_attachment_join j "
                    "JOIN attachment a ON a.ROWID = j.attachment_id"
                ):
                    descricao = (_texto(linha["nome"]) or _texto(linha["arquivo"])
                                 or traduzir("nm_sem_nome", idioma))
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
                    identificador or 0,
                    traduzir("ios_desc_registro_msg", idioma, id=identificador),
                    traduzir("ios_desc_sms", idioma),
                ))
                continue
            de_mim = str(linha["de_mim"]) == "1"
            conversa = _texto(linha["nome_do_grupo"]) or _texto(linha["conversa"])
            resultado.registros.append(Registro(
                tipo="sms",
                campos={
                    "direcao": traduzir("nm_dir_enviada" if de_mim else "nm_dir_recebida", idioma),
                    "numero": _texto(linha["interlocutor"]) or _texto(linha["conversa"])
                    or traduzir("nm_sem_numero", idioma),
                    "conversa": (conversa or _texto(linha["interlocutor"])
                                 or traduzir("ios_sem_identificacao", idioma)),
                    "servico": _texto(linha["servico"]),
                    "conteudo": conteudo,
                    "anexo": anexo,
                    "lida": "" if de_mim else _lida_ios(linha["lida"], idioma),
                },
                momento=momento,
                arquivo_de_origem=resultado.arquivo_de_origem,
                linha_de_origem=identificador or 0,
            ))
    return resultado


# ---------------------------------------------------------------------------
# Chamadas: CallHistory.storedata
# ---------------------------------------------------------------------------
def _servico_da_chamada(provedor: str, tipo, idioma=None) -> str:
    provedor = provedor or ""
    if "whatsapp" in provedor.lower():
        return "WhatsApp"
    if str(tipo) == "8":
        return traduzir("ios_svc_facetime_video", idioma)
    if str(tipo) == "16":
        return traduzir("ios_svc_facetime_audio", idioma)
    if "telephony" in provedor.lower() or str(tipo) == "1":
        return traduzir("ios_svc_telefone", idioma)
    return provedor or traduzir("nm_nao_informado", idioma)


def ler_chamadas(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "",
                 idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("chamada", caminho, arquivo, fuso, idioma)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ZCALLRECORD"):
            return _recusar(resultado, _esquema_desconhecido(banco, ("ZCALLRECORD",), idioma))
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
            return _recusar(resultado, traduzir("ios_consulta_chamadas", idioma, erro=erro))
        for linha in linhas:
            if str(linha["efetuada"]) == "1":
                direcao = traduzir("nm_call_efetuada", idioma)
            elif str(linha["atendida"]) == "1":
                direcao = traduzir("nm_dir_recebida", idioma)
            else:
                direcao = traduzir("ios_call_nao_atendida", idioma)
            try:
                duracao = str(int(round(float(linha["duracao"] or 0))))
            except (TypeError, ValueError):
                duracao = _texto(linha["duracao"])
            resultado.registros.append(Registro(
                tipo="chamada",
                campos={
                    "direcao": direcao,
                    "numero": _texto(linha["numero"]) or traduzir("ios_num_nao_informado", idioma),
                    "contato": _texto(linha["nome"]),
                    "duracao_segundos": duracao,
                    "servico": _servico_da_chamada(_texto(linha["provedor"]), linha["tipo"], idioma),
                },
                momento=momento_apple(linha["momento"], fuso),
                arquivo_de_origem=resultado.arquivo_de_origem,
                linha_de_origem=linha["id"] or 0,
            ))
    return resultado


# ---------------------------------------------------------------------------
# Agenda: AddressBook.sqlitedb
# ---------------------------------------------------------------------------
def ler_contatos(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "",
                 idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("contato", caminho, arquivo, fuso, idioma)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ABPerson", "ABMultiValue"):
            return _recusar(resultado,
                            _esquema_desconhecido(banco, ("ABPerson", "ABMultiValue"), idioma))
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
            return _recusar(resultado, traduzir("ios_consulta_agenda", idioma, erro=erro))

        telefones, emails = {}, {}
        for linha in valores:
            destino = telefones if linha["propriedade"] == PROPRIEDADE_TELEFONE else emails
            if linha["valor"]:
                destino.setdefault(linha["id"], []).append(_texto(linha["valor"]))

        for pessoa in pessoas:
            nome = " ".join(p for p in (_texto(pessoa["nome"]), _texto(pessoa["sobrenome"])) if p)
            nome = nome or _texto(pessoa["empresa"]) or traduzir("nm_sem_nome", idioma)
            email = "; ".join(emails.get(pessoa["id"], []))
            for numero in telefones.get(pessoa["id"], []) or [traduzir("nm_sem_numero", idioma)]:
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


def ler_whatsapp(caminho: Path, pasta_trabalho: Path, fuso=None, arquivo: str = "",
                 idioma=None) -> ResultadoNormalizacao:
    resultado = _resultado("whatsapp", caminho, arquivo, fuso, idioma)
    with abrir(caminho, pasta_trabalho) as banco:
        if not banco.legivel:
            return _recusar(resultado, banco.motivo)
        if not banco.tem_tabelas("ZWAMESSAGE", "ZWACHATSESSION"):
            return _recusar(resultado,
                            _esquema_desconhecido(banco, ("ZWAMESSAGE", "ZWACHATSESSION"), idioma))
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
            return _recusar(resultado, traduzir("ios_consulta_mensagens", idioma, erro=erro))

        for linha in linhas:
            identificador = linha["id"]
            jid_conversa = _texto(linha["jid_conversa"])
            em_grupo = jid_conversa.endswith(SUFIXO_GRUPO_WHATSAPP)
            de_mim = str(linha["de_mim"]) == "1"
            # O código é a identidade do tipo (usado na lógica); o rótulo é a
            # tradução exibida. Nunca se decide pelo rótulo — ele muda de idioma.
            try:
                codigo = int(linha["tipo"])
            except (TypeError, ValueError):
                codigo = None
            tipo_desconhecido = codigo is None or codigo not in TIPOS_WHATSAPP_IOS
            if codigo is None:
                tipo = traduzir("ios_wa_tipo_nao_informado", idioma)
            elif tipo_desconhecido:
                tipo = traduzir("ios_wa_tipo_codigo", idioma, codigo=codigo)
            else:
                tipo = traduzir(TIPOS_WHATSAPP_IOS[codigo], idioma)
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
                tipo = traduzir("ios_wa_evento", idioma)
                conteudo = traduzir("ios_wa_evento_corpo", idioma, evento=evento)
            elif codigo == TIPO_WA_LOCALIZACAO:
                lugar = _coordenadas(linha["latitude"], linha["longitude"])
                if lugar:
                    mapa = f"https://www.google.com/maps?q={lugar[0]:.6f},{lugar[1]:.6f}"
                    conteudo = " — ".join(p for p in (
                        traduzir("ios_wa_loc_coord", idioma,
                                 lat=f"{lugar[0]:.6f}", lon=f"{lugar[1]:.6f}"), conteudo) if p)
            if not conteudo and tipo_desconhecido and not _texto(linha["midia"]):
                conteudo = tipo[:-1] + traduzir("ios_wa_suf_sem_midia", idioma)
            if not conteudo and codigo != TIPO_WA_TEXTO:
                conteudo = f"({tipo})"
            momento = momento_apple(linha["momento"], fuso)
            if momento is None and not conteudo:
                resultado.descartes.append(Descarte(
                    identificador or 0,
                    traduzir("ios_desc_registro_wa", idioma, id=identificador),
                    traduzir("wa_desc_sem_dados", idioma),
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
                    "direcao": (traduzir("ios_wa_sistema", idioma) if evento
                                else traduzir("nm_dir_enviada" if de_mim else "nm_dir_recebida",
                                              idioma)),
                    "numero": _numero_do_jid(jid_interlocutor),
                    "contato": contato,
                    "conversa": conversa or traduzir("ios_sem_identificacao", idioma),
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
