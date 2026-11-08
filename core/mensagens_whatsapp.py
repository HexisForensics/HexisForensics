"""
Leitura do `msgstore.db` do WhatsApp — o banco de mensagens ativo.

Este arquivo é adquirido hoje, quando há privilégio elevado, pelo Dump do
Sistema de Arquivos e pela Extração Física. Chega à aquisição, é selado,
hasheado — e ninguém o lê. O caderno de conteúdo mostra SMS, chamadas e
agenda; o WhatsApp não aparece, mesmo quando o banco veio inteiro.

**Dois esquemas, e confundi-los produz relatório vazio.**

O WhatsApp trocou o modelo de dados por volta de 2021. Antes, uma tabela
`messages` guardava tudo, com o contato na própria linha (`key_remote_jid`).
Depois, o modelo virou relacional: `message` aponta para `chat`, que aponta
para `jid`. Um leitor que conheça só um dos dois e encontre o outro não
pode devolver zero mensagens — tem de dizer **qual esquema achou**. Zero
mensagens num aparelho com WhatsApp instalado é a conclusão negativa falsa
mais cara que esta ferramenta poderia produzir.

**Mensagem de mídia não é mensagem vazia.** Foto, áudio e vídeo têm o
`text_data` nulo, porque o conteúdo está num arquivo, não no banco. Tratar
isso como mensagem sem texto e descartar apagaria da linha do tempo
justamente o que costuma interessar. Aqui a mensagem entra com o tipo
declarado — "(imagem)", "(áudio)" — e o nome do arquivo quando o banco o
conhece.

**O que este módulo não alcança**, e declara: mensagem apagada pelo
usuário sai da tabela e pode restar em página livre do arquivo, fora do
alcance de qualquer consulta SQL; e mensagem cujo `-wal` não acompanhou a
aquisição não está aqui (ver `core.sqlite_forense`).
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Optional

from .normalizacao import Descarte, Registro, ResultadoNormalizacao, momento_de_epoch, nome_do_fuso
from .sqlite_forense import abrir

TIPO = "whatsapp"

# Sufixo do identificador de um grupo. Conversa individual termina em
# `@s.whatsapp.net`.
SUFIXO_GRUPO = "@g.us"

# `message_type` no esquema novo, `media_wa_type` no antigo. Os códigos
# coincidem no que interessa. O que não estiver aqui entra com o número,
# em vez de virar "desconhecido" — o número é verificável, o rótulo
# inventado não.
TIPOS_DE_MENSAGEM = {
    0: "texto",
    1: "imagem",
    2: "áudio",
    3: "vídeo",
    4: "contato",
    5: "localização",
    7: "mensagem de sistema",
    9: "documento",
    13: "GIF",
    15: "mensagem apagada",
    16: "localização em tempo real",
    20: "figurinha",
    42: "imagem de visualização única",
    43: "vídeo de visualização única",
}

TIPO_SISTEMA = 7

COLUNAS = ("momento", "direcao", "numero", "contato", "conversa", "tipo", "conteudo", "anexo")

# Sufixo do identificador OPACO que o WhatsApp atual usa no lugar do
# telefone. Achado na primeira leitura de um banco real (09/10/2026): a
# conversa vinha como `35614506377338@lid`, e o leitor apresentava esse
# número na coluna do telefone. Ele não é telefone de ninguém; a tabela
# `jid_map` do próprio banco é que diz a que número corresponde.
SUFIXO_LID = "@lid"

NOME_BANCO_DE_CONTATOS = "wa.db"

# Colunas da tabela de mídia que interessam, quando existirem: o esquema
# muda entre versões, e consultar coluna inexistente derrubaria a leitura
# inteira das mensagens por causa de um detalhe do anexo.
COLUNAS_DE_MIDIA = (
    "file_path", "media_caption", "mime_type", "media_name", "file_size", "file_hash",
)

CONSULTA_MODERNA = """
    SELECT
        m._id            AS id,
        m.chat_row_id    AS id_conversa,
        m.timestamp      AS momento,
        m.from_me        AS de_mim,
        m.text_data      AS texto,
        m.message_type   AS tipo,
        conversa.raw_string AS jid_conversa,
        remetente.raw_string AS jid_remetente,
        c.subject        AS assunto
        {colunas_extras}
    FROM message m
    LEFT JOIN chat c        ON c._id = m.chat_row_id
    LEFT JOIN jid conversa  ON conversa._id = c.jid_row_id
    LEFT JOIN jid remetente ON remetente._id = m.sender_jid_row_id
    {juncoes_extras}
    ORDER BY m.timestamp
"""

CONSULTA_LEGADA = """
    SELECT
        _id             AS id,
        0               AS id_conversa,
        timestamp       AS momento,
        key_from_me     AS de_mim,
        data            AS texto,
        media_wa_type   AS tipo,
        key_remote_jid  AS jid_conversa,
        remote_resource AS jid_remetente,
        NULL            AS assunto
    FROM messages
    ORDER BY timestamp
"""


def _rotulo_do_tipo(valor) -> str:
    """
    Nome do tipo de mensagem, ou o próprio código quando desconhecido.

    Devolve o rótulo **sem parênteses**: quem os coloca é `_conteudo_de`,
    e duplicá-los aqui produzia "((tipo 77))" na coluna que vai ao laudo.
    Cada função faz uma coisa — esta nomeia, aquela formata.
    """
    try:
        codigo = int(valor)
    except (TypeError, ValueError):
        return "tipo não informado"
    return TIPOS_DE_MENSAGEM.get(codigo, f"tipo {codigo}")


def _numero_de(jid: Optional[str]) -> str:
    """
    Número a partir do identificador do WhatsApp.

    `5511988887777@s.whatsapp.net` vira `5511988887777`. O identificador
    inteiro é preservado no campo da conversa: é ele que distingue um
    grupo de um contato, e recortá-lo perderia essa informação.
    """
    if not jid:
        return ""
    return str(jid).split("@", 1)[0]


def _colunas(banco, tabela: str) -> set:
    try:
        return {linha["name"] for linha in banco.consultar(f'PRAGMA table_info("{tabela}")')}
    except Exception:
        return set()


def _montar_consulta_moderna(banco) -> str:
    """
    A consulta do esquema relacional, acrescida do que ESTE banco tiver:
    a tabela de mídia (com as colunas que existirem nela) e a de mensagens
    de sistema.
    """
    colunas, juncoes = [], []
    if banco.tem_tabelas("message_media"):
        presentes = _colunas(banco, "message_media")
        usadas = [c for c in COLUNAS_DE_MIDIA if c in presentes]
        if usadas and "message_row_id" in presentes:
            colunas += [f"mm.{c} AS midia_{c}" for c in usadas]
            juncoes.append("LEFT JOIN message_media mm ON mm.message_row_id = m._id")
    if banco.tem_tabelas("message_system"):
        if {"message_row_id", "action_type"} <= _colunas(banco, "message_system"):
            colunas.append("ms.action_type AS acao_de_sistema")
            juncoes.append("LEFT JOIN message_system ms ON ms.message_row_id = m._id")
    return CONSULTA_MODERNA.format(
        colunas_extras="".join(",\n        " + c for c in colunas),
        juncoes_extras="\n    ".join(juncoes),
    )


def _mapa_de_lids(banco) -> dict:
    """`identificador@lid` -> `telefone@s.whatsapp.net`, do próprio banco."""
    if not banco.tem_tabelas("jid_map", "jid"):
        return {}
    try:
        linhas = banco.consultar(
            "SELECT lid.raw_string AS lid, tel.raw_string AS tel FROM jid_map m "
            "JOIN jid lid ON lid._id = m.lid_row_id JOIN jid tel ON tel._id = m.jid_row_id"
        )
    except Exception:
        return {}
    return {linha["lid"]: linha["tel"] for linha in linhas if linha["lid"] and linha["tel"]}


def _nomes_da_agenda(caminho_banco: Path, pasta_trabalho: Path):
    """
    Nomes dos contatos, do `wa.db` que mora ao lado do `msgstore.db`.

    Devolve `(nomes, situacao)`: `situacao` vazia quando a agenda foi lida,
    ou o texto que vai para a coluna dizendo por que não há nome. Nome
    ausente porque o contato não está salvo e nome ausente porque a agenda
    não foi coletada são fatos diferentes.
    """
    caminho = Path(caminho_banco).with_name(NOME_BANCO_DE_CONTATOS)
    if not caminho.is_file():
        return {}, "(agenda do WhatsApp não coletada)"
    with abrir(caminho, pasta_trabalho) as agenda:
        if not agenda.legivel or not agenda.tem_tabelas("wa_contacts"):
            return {}, "(agenda do WhatsApp não pôde ser lida)"
        presentes = _colunas(agenda, "wa_contacts")
        campos = [c for c in ("display_name", "wa_name") if c in presentes]
        if "jid" not in presentes or not campos:
            return {}, "(agenda do WhatsApp em formato não reconhecido)"
        try:
            linhas = agenda.consultar(f"SELECT jid, {', '.join(campos)} FROM wa_contacts")
        except Exception:
            return {}, "(agenda do WhatsApp não pôde ser lida)"
        nomes = {}
        for linha in linhas:
            nome = next((linha[c] for c in campos if linha[c]), None)
            if linha["jid"] and nome:
                nomes[linha["jid"]] = str(nome)
        return nomes, ""


def _resolver(jid: Optional[str], lids: dict):
    """
    Devolve `(jid_com_telefone, numero_para_exibir)`.

    Identificador opaco sem correspondência no banco NÃO é exibido como
    número: a coluna diz que o telefone não consta, e o identificador
    continua íntegro na coluna da conversa.
    """
    if not jid:
        return "", ""
    jid = str(jid)
    if jid.endswith(SUFIXO_LID):
        telefone = lids.get(jid)
        if not telefone:
            return "", "(telefone não consta no banco — identificador interno do WhatsApp)"
        return telefone, _numero_de(telefone)
    return jid, _numero_de(jid)


def _hash_da_midia(valor) -> str:
    """
    O SHA-256 que o PRÓPRIO WhatsApp registra para cada mídia, em
    hexadecimal. O banco o guarda em base64.

    Conferido contra aparelho em 09/10/2026: o valor do banco é idêntico ao
    `sha256sum` do arquivo em `Media/`. É o elo entre a mensagem e o
    arquivo — permite afirmar que ESTE arquivo é o que trafegou NESTA
    mensagem, e acusa arquivo trocado ou alterado depois.

    Valor que não decodifica para 32 bytes é devolvido vazio: melhor não
    exibir hash do que exibir um que não é.
    """
    if not valor:
        return ""
    try:
        bruto = base64.b64decode(valor if isinstance(valor, bytes) else str(valor), validate=True)
    except (ValueError, binascii.Error):
        return ""
    return bruto.hex() if len(bruto) == 32 else ""


def _valor_opcional(linha, coluna: str):
    try:
        return linha[coluna]
    except (IndexError, KeyError):
        return None


def _conteudo_de(texto, tipo_legivel: str) -> str:
    """
    O que a mensagem carrega.

    Mídia tem texto nulo porque o conteúdo está num arquivo. Devolver
    string vazia ali apagaria a mensagem da linha do tempo; devolver o
    tipo entre parênteses preserva o fato de que a mensagem existiu e diz
    o que ela era.
    """
    if texto:
        return str(texto)
    if tipo_legivel == "texto":
        return ""
    return f"({tipo_legivel})"


def ler(caminho_banco: Path, pasta_trabalho: Path, fuso=None) -> ResultadoNormalizacao:
    """
    Lê o `msgstore.db` e devolve o mesmo `ResultadoNormalizacao` dos demais
    artefatos — daí para a frente, caderno, planilha e procedência já
    funcionam sem saber que a origem foi um banco.
    """
    caminho_banco = Path(caminho_banco)
    resultado = ResultadoNormalizacao(
        tipo=TIPO,
        arquivo_de_origem=caminho_banco.name,
        fuso_declarado=nome_do_fuso(fuso),
    )

    with abrir(caminho_banco, pasta_trabalho) as banco:
        if not banco.legivel:
            # Recusa de leitura não é ausência de mensagem. `acesso_negado`
            # faz o relatório dizer isso com todas as letras.
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = banco.motivo
            return resultado

        if banco.tem_tabelas("message", "chat", "jid"):
            consulta, esquema = _montar_consulta_moderna(banco), "message/chat/jid"
        elif banco.tem_tabelas("messages"):
            consulta, esquema = CONSULTA_LEGADA, "messages"
        else:
            # O banco abriu e não tem nenhum dos dois modelos conhecidos.
            # Dizer QUAIS tabelas existem é o que permite ao examinador
            # descobrir com que versão está lidando, em vez de concluir
            # que não havia mensagens.
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = (
                "O banco abriu, mas não tem nenhum dos esquemas de mensagem "
                "conhecidos. Nada se pode afirmar sobre as mensagens deste "
                "aparelho a partir deste arquivo. Tabelas encontradas: "
                + (", ".join(banco.tabelas) or "nenhuma")
            )
            return resultado

        try:
            linhas = banco.consultar(consulta)
        except Exception as erro:  # sqlite3.Error e derivados
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = (
                f"O esquema '{esquema}' foi reconhecido, mas a consulta falhou: {erro}. "
                "As mensagens NÃO foram lidas."
            )
            return resultado

        lids = _mapa_de_lids(banco)
        nomes, situacao_da_agenda = _nomes_da_agenda(caminho_banco, pasta_trabalho)

        for linha in linhas:
            identificador = linha["id"]

            # O WhatsApp mantém na tabela uma linha-marcador sem conversa,
            # sem data, sem tipo e sem texto. Contra banco real ela saía no
            # caderno como "mensagem recebida, sem data" — uma mensagem que
            # nunca existiu. É contada como descarte, com o motivo.
            if (
                linha["momento"] is None
                and linha["tipo"] is None
                and not linha["texto"]
                and not linha["jid_conversa"]
            ):
                resultado.descartes.append(
                    Descarte(
                        linha_de_origem=identificador or 0,
                        texto=f"registro {identificador} da tabela de mensagens",
                        motivo="marcador interno do WhatsApp: sem conversa, data, tipo e texto",
                    )
                )
                continue

            momento = momento_de_epoch(linha["momento"], fuso)
            tipo_legivel = _rotulo_do_tipo(linha["tipo"])
            legenda = _valor_opcional(linha, "midia_media_caption")
            conteudo = _conteudo_de(linha["texto"] or legenda, tipo_legivel)
            acao = _valor_opcional(linha, "acao_de_sistema")
            if str(linha["tipo"]) == str(TIPO_SISTEMA) and acao is not None:
                # O código da ação é verificável; o significado dele muda
                # entre versões e não é adivinhado aqui.
                conteudo = f"(mensagem de sistema, ação {acao})"

            caminho_midia = _valor_opcional(linha, "midia_file_path")
            tipo_mime = _valor_opcional(linha, "midia_mime_type")
            tamanho = _valor_opcional(linha, "midia_file_size")
            hash_midia = _hash_da_midia(_valor_opcional(linha, "midia_file_hash"))
            detalhes_do_anexo = [
                parte
                for parte in (
                    str(tipo_mime) if tipo_mime else "",
                    f"{tamanho} bytes" if tamanho else "",
                    f"SHA-256 registrado pelo WhatsApp: {hash_midia}" if hash_midia else "",
                )
                if parte
            ]
            sufixo = f" [{'; '.join(detalhes_do_anexo)}]" if detalhes_do_anexo else ""
            anexo = ""
            if caminho_midia:
                anexo = str(caminho_midia) + sufixo
            elif detalhes_do_anexo:
                anexo = "(arquivo não baixado no aparelho)" + sufixo

            jid_conversa = linha["jid_conversa"] or ""
            em_grupo = str(jid_conversa).endswith(SUFIXO_GRUPO)
            de_mim = str(linha["de_mim"]) == "1"

            # Em grupo, o interlocutor não é a conversa: é quem enviou.
            # Confundir os dois atribuiria toda mensagem de grupo ao
            # próprio grupo, e ninguém saberia quem falou.
            jid_interlocutor = (linha["jid_remetente"] or jid_conversa) if em_grupo else jid_conversa
            jid_telefone, numero = _resolver(jid_interlocutor, lids)
            if de_mim and em_grupo:
                jid_telefone, numero = "", ""
            if situacao_da_agenda:
                contato = situacao_da_agenda
            else:
                contato = nomes.get(jid_telefone, "") if jid_telefone else ""

            if momento is None and not conteudo:
                resultado.descartes.append(
                    Descarte(
                        linha_de_origem=identificador or 0,
                        texto=f"registro {identificador} da tabela de mensagens",
                        motivo="sem data e sem conteúdo — nada a apresentar",
                    )
                )
                continue

            resultado.registros.append(
                Registro(
                    tipo=TIPO,
                    campos={
                        "direcao": "Enviada" if de_mim else "Recebida",
                        "numero": numero,
                        "contato": contato,
                        "conversa": (linha["assunto"] or jid_conversa or ""),
                        "tipo": tipo_legivel,
                        "conteudo": conteudo,
                        "anexo": anexo,
                    },
                    momento=momento,
                    arquivo_de_origem=caminho_banco.name,
                    # Num banco não há número de linha: o identificador da
                    # própria tabela é o que permite reencontrar o registro.
                    linha_de_origem=identificador or 0,
                )
            )

    return resultado
