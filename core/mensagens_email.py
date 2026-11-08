"""
Leitura do acervo local de correio eletrônico do Android.

O Gmail guarda as mensagens num SQLite dentro de
`/data/data/com.google.android.gm/databases/`, um por conta configurada.
É o banco que **dá procedência ao anexo**: sem ele, o PDF que está em
`/sdcard/Download` é arquivo órfão — ninguém sabe de qual mensagem veio,
de quem, nem quando.

**A detecção é por coluna, e não por nome de tabela.** O esquema do Gmail
para Android muda bastante entre versões, e há uma colisão concreta: a
tabela de mensagens costuma chamar-se `messages`, exatamente como no
`msgstore.db` do WhatsApp. Escolher pelo nome faria o leitor de e-mail
tentar ler um banco de WhatsApp e devolver lixo, ou nada. Aqui cada tabela
é inspecionada, e só é aceita a que tiver **endereço de remetente** e
**assunto ou corpo** — a assinatura do que é correio, e não de como a
versão resolveu nomear as coisas.

**Sem direção presumida.** No WhatsApp existe `from_me`, um fato gravado
pelo aplicativo. No Gmail não há equivalente confiável: deduzir "enviada"
comparando o remetente com a conta exigiria saber qual é a conta, e errar
inverteria o sentido de uma conversa inteira num laudo. Por isso este
módulo apresenta **quem enviou** e **para quem**, e deixa a leitura com
quem sabe de qual conta o banco veio.

**Anexo: presença, não nome.** A coluna de anexos do Gmail guarda uma
estrutura serializada própria. Extrair nome de arquivo dali por
aproximação produziria nomes plausíveis e possivelmente errados, o que é
pior que não ter nome nenhum. O módulo afirma o que é verificável — que a
mensagem tinha anexo — e declara que os nomes não foram interpretados.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .normalizacao import (
    Descarte,
    Registro,
    ResultadoNormalizacao,
    momento_de_epoch,
    nome_do_fuso,
)
from .sqlite_forense import abrir

TIPO = "email"

COLUNAS = ("momento", "de", "para", "assunto", "anexo", "conteudo")

# Nomes que cada campo já teve nas versões do Gmail para Android. A ordem
# é de preferência: o primeiro que existir na tabela é o usado.
NOMES_REMETENTE = ("fromAddress", "from_address", "sender", "fromaddress")
NOMES_DESTINATARIO = ("toAddresses", "to_addresses", "toaddresses", "recipients")
NOMES_ASSUNTO = ("subject",)
NOMES_CORPO = ("snippet", "body", "bodyText", "bodytext")
NOMES_CORPO_COMPRIMIDO = ("bodyCompressed", "bodycompressed")
NOMES_MOMENTO = (
    "dateReceivedMs",
    "datereceivedms",
    "dateSentMs",
    "datesentms",
    "date",
    "received_timestamp",
    "timestamp",
)
NOMES_ANEXO = ("joinedAttachmentInfos", "joinedattachmentinfos", "attachments")

AVISO_CORPO_COMPRIMIDO = "(corpo armazenado comprimido — não interpretado)"


def _primeira_presente(colunas, candidatos) -> Optional[str]:
    """Primeiro nome candidato que exista entre as colunas da tabela."""
    disponiveis = {c.lower(): c for c in colunas}
    for candidato in candidatos:
        if candidato.lower() in disponiveis:
            return disponiveis[candidato.lower()]
    return None


def _colunas_da_tabela(banco, tabela: str) -> list:
    """Nomes das colunas, ou lista vazia se a tabela não puder ser inspecionada."""
    try:
        return [linha[1] for linha in banco.consultar(f'PRAGMA table_info("{tabela}")')]
    except Exception:
        return []


def localizar_tabela_de_mensagens(banco):
    """
    Encontra a tabela de correio e o mapa de colunas dela.

    Devolve `(tabela, mapa)` ou `(None, {})`. A assinatura exigida é
    remetente **mais** assunto ou corpo: é o que distingue uma tabela de
    correio de uma tabela de mensagens de mensageiro, que tem identificador
    de conversa e não endereço.
    """
    for tabela in banco.tabelas:
        colunas = _colunas_da_tabela(banco, tabela)
        if not colunas:
            continue
        remetente = _primeira_presente(colunas, NOMES_REMETENTE)
        assunto = _primeira_presente(colunas, NOMES_ASSUNTO)
        corpo = _primeira_presente(colunas, NOMES_CORPO)
        comprimido = _primeira_presente(colunas, NOMES_CORPO_COMPRIMIDO)
        if not remetente or not (assunto or corpo or comprimido):
            continue
        return tabela, {
            "remetente": remetente,
            "destinatario": _primeira_presente(colunas, NOMES_DESTINATARIO),
            "assunto": assunto,
            "corpo": corpo,
            "corpo_comprimido": comprimido,
            "momento": _primeira_presente(colunas, NOMES_MOMENTO),
            "anexo": _primeira_presente(colunas, NOMES_ANEXO),
        }
    return None, {}


def _valor(linha, coluna: Optional[str]) -> str:
    """Conteúdo de uma coluna que pode não existir naquela versão."""
    if not coluna:
        return ""
    try:
        valor = linha[coluna]
    except (IndexError, KeyError):
        return ""
    return "" if valor is None else str(valor)


def ler(caminho_banco: Path, pasta_trabalho: Path, fuso=None) -> ResultadoNormalizacao:
    """
    Lê o acervo local de correio e devolve o mesmo `ResultadoNormalizacao`
    dos demais artefatos.
    """
    caminho_banco = Path(caminho_banco)
    resultado = ResultadoNormalizacao(
        tipo=TIPO,
        arquivo_de_origem=caminho_banco.name,
        fuso_declarado=nome_do_fuso(fuso),
    )

    with abrir(caminho_banco, pasta_trabalho) as banco:
        if not banco.legivel:
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = banco.motivo
            return resultado

        tabela, mapa = localizar_tabela_de_mensagens(banco)
        if tabela is None:
            # Nomear as tabelas encontradas é o que permite ao examinador
            # descobrir com que versão está lidando. "Nenhuma mensagem"
            # sobre um aparelho com Gmail configurado seria conclusão
            # negativa falsa.
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = (
                "O banco abriu, mas nenhuma tabela tem a assinatura de correio "
                "(endereço de remetente com assunto ou corpo). Nada se pode afirmar "
                "sobre as mensagens deste acervo. Tabelas encontradas: "
                + (", ".join(banco.tabelas) or "nenhuma")
            )
            return resultado

        selecionadas = [nome for nome in mapa.values() if nome]
        colunas_sql = ", ".join(f'"{nome}"' for nome in selecionadas)
        try:
            linhas = banco.consultar(f'SELECT rowid AS _linha, {colunas_sql} FROM "{tabela}"')
        except Exception as erro:
            resultado.acesso_negado = True
            resultado.trecho_da_recusa = (
                f"A tabela de correio '{tabela}' foi reconhecida, mas a consulta "
                f"falhou: {erro}. As mensagens NÃO foram lidas."
            )
            return resultado

        for linha in linhas:
            identificador = linha["_linha"]
            momento = momento_de_epoch(_valor(linha, mapa["momento"]), fuso)
            assunto = _valor(linha, mapa["assunto"])
            corpo = _valor(linha, mapa["corpo"])
            if not corpo and _valor(linha, mapa["corpo_comprimido"]):
                # O corpo existe e está comprimido. Devolver vazio faria a
                # mensagem parecer sem conteúdo, que é fato diferente.
                corpo = AVISO_CORPO_COMPRIMIDO
            tem_anexo = bool(_valor(linha, mapa["anexo"]).strip())

            if momento is None and not assunto and not corpo:
                resultado.descartes.append(
                    Descarte(
                        linha_de_origem=identificador or 0,
                        texto=f"registro {identificador} da tabela '{tabela}'",
                        motivo="sem data, sem assunto e sem corpo — nada a apresentar",
                    )
                )
                continue

            resultado.registros.append(
                Registro(
                    tipo=TIPO,
                    campos={
                        "de": _valor(linha, mapa["remetente"]),
                        "para": _valor(linha, mapa["destinatario"]),
                        "assunto": assunto,
                        # Fato verificável: a mensagem tinha anexo. O NOME
                        # do arquivo mora numa estrutura serializada
                        # própria, e aproximá-lo produziria nomes
                        # plausíveis e possivelmente errados.
                        "anexo": "Sim" if tem_anexo else "Não",
                        "conteudo": corpo,
                    },
                    momento=momento,
                    arquivo_de_origem=caminho_banco.name,
                    linha_de_origem=identificador or 0,
                )
            )

    return resultado
