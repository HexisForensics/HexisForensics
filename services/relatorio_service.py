"""
Relatório de conteúdo: o que a investigação lê.

A suíte faz aquisição com cadeia de custódia impecável e entrega um dump de
máquina. Este serviço fecha essa distância: localiza os arquivos brutos
dentro de uma aquisição, normaliza (`core.normalizacao`) e produz o que o
analista consegue trabalhar — CSV por artefato — e o que se junta aos autos
— um PDF consolidado.

Três decisões estruturais, todas com a mesma raiz:

**Fica FORA do selo.** O relatório é documento derivado, produzido depois da
coleta, como o laudo e o relatório de conferência. Vai para
`<caso>/relatorios/<aquisicao>_<carimbo>/`, nunca dentro da aquisição — que
é selada e não pode receber arquivo novo. E precisa poder ser **regerado**
quando o normalizador melhorar, sem que isso toque na evidência.

**Confere a origem contra o selo.** Antes de apresentar qualquer conteúdo,
recalcula o hash de cada arquivo bruto e confronta com o manifesto da
aquisição. Um relatório construído sobre arquivo que não confere mais com o
selo não pode circular sem dizer isso — em letras grandes, no topo.

**Declara a procedência de cada linha.** Cada registro carrega o arquivo e a
linha de onde veio, e o relatório declara o fuso horário usado na conversão
das datas. O relatório apresenta a evidência; não a substitui.
"""

from __future__ import annotations

import json
import csv
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.idioma import traduzir
from core.agente_android import PASTA as PASTA_DO_AGENTE
from core.agente_android import ler_chamadas as ler_chamadas_do_agente
from core.agente_android import ler_contatos as ler_contatos_do_agente
from core.agente_android import ler_mms as ler_mms_do_agente
from core.agente_android import ler_sms as ler_sms_do_agente
from core.case import idioma_do_caso, pasta_dos_decifrados
from core.hashing import calcular_sha256, ler_manifesto, localizar_manifesto
from core.mensagens_email import COLUNAS as COLUNAS_EMAIL
from core.mensagens_email import ler as ler_email
from core.backup_android import PACOTE_CHAMADAS, PACOTE_TELEFONIA
from core.backup_android import ler_chamadas as ler_chamadas_do_backup
from core.backup_android import ler_mms as ler_mms_do_backup
from core.backup_android import ler_sms as ler_sms_do_backup
from core.companheiros import SUFIXOS_ANEXADOS
from core import backup_ios, mensagens_ios, sqlite_forense
from core.geolocalizacao import EXTENSOES_DE_IMAGEM, ler_dados_da_foto
from core.normalizacao import Descarte, Registro, ResultadoNormalizacao
from core.relogio import alerta as alerta_do_relogio, desvio_da_aquisicao
from core.mensagens_whatsapp import COLUNAS as COLUNAS_WHATSAPP
from core.mensagens_whatsapp import ler as ler_whatsapp
from core.normalizacao import (
    normalizar_chamadas,
    normalizar_contatos,
    normalizar_mms,
    normalizar_sms,
)

PASTA_RELATORIOS = "relatorios"
NOME_PROCEDENCIA = "PROCEDENCIA.txt"
NOME_DESCARTES = "NAO_INTERPRETADO.txt"
NOME_PDF = "Relatorio_de_Conteudo.pdf"
NOME_CADERNO = "Caderno_de_Conteudo.html"

# Versão do normalizador, registrada em cada relatório. Dois relatórios do
# mesmo material com versões diferentes podem divergir legitimamente — e sem
# esse número ninguém saberia por quê.
VERSAO_NORMALIZADOR = "1.0"

# Acima disto, uma conversa (WhatsApp, SMS, MMS, e-mail) vai para o PDF de
# conteúdo como índice; a íntegra fica no CSV e no caderno HTML.
LIMITE_INTEGRA_NO_PDF = 300

LARGURA = 70

# Onde cada artefato mora dentro da aquisição, e como normalizá-lo.
# `sms_todas` cobre `sms_recebidas`/`enviadas`/`rascunhos`, que são recortes
# da mesma tabela: incluir os quatro faria o relatório contar cada mensagem
# duas vezes e sugerir o dobro do volume real.
FONTES = (
    ("sms", "rs_art_sms", "sms/sms_todas.txt", normalizar_sms,
     ("momento", "direcao", "numero", "conteudo", "lida")),
    ("mms", "rs_art_mms", "sms/mms_cabecalhos.txt", normalizar_mms,
     ("momento", "direcao", "numero", "assunto", "conteudo", "anexo", "lida")),
    ("chamada", "rs_art_chamada", "contacts_calls/registro_chamadas_bruto.txt",
     normalizar_chamadas,
     ("momento", "direcao", "numero", "contato", "duracao_segundos")),
    ("contato", "rs_art_contato", "contacts_calls/agenda_contatos_bruta.txt",
     normalizar_contatos, ("contato", "numero")),
)

# Artefatos obtidos pela via de backup do sistema (`adb backup`), quando o
# provider recusou a consulta direta. Só entram no caderno se o `.ab`
# existir: é via alternativa, e a recusa do provider já está dita no
# artefato correspondente logo acima.
FONTES_BACKUP = (
    ("sms_backup", "rs_art_sms_backup",
     f"sms/backup_{PACOTE_TELEFONIA}.ab", ler_sms_do_backup,
     ("momento", "direcao", "numero", "conteudo", "lida")),
    ("mms_backup", "rs_art_mms_backup",
     f"sms/backup_{PACOTE_TELEFONIA}.ab", ler_mms_do_backup,
     ("momento", "direcao", "numero", "assunto", "conteudo", "anexo", "lida")),
    ("chamada_backup", "rs_art_chamada_backup",
     f"contacts_calls/backup_{PACOTE_CHAMADAS}.ab", ler_chamadas_do_backup,
     ("momento", "direcao", "numero", "duracao_segundos", "apresentacao", "linha_utilizada")),
)

# Artefatos lidos pelo aplicativo agente (`core/android/extractors/agente.py`),
# a via do Android 12 em diante. Como os de backup, só entram quando o
# arquivo existe: é via alternativa à consulta direta, cuja recusa já está
# dita no artefato correspondente.
FONTES_AGENTE = (
    ("contato_agente", "rs_art_contato_agente",
     f"{PASTA_DO_AGENTE}/contatos.jsonl", ler_contatos_do_agente, ("contato", "numero")),
    ("chamada_agente", "rs_art_chamada_agente",
     f"{PASTA_DO_AGENTE}/chamadas.jsonl", ler_chamadas_do_agente,
     ("momento", "direcao", "numero", "contato", "duracao_segundos")),
    ("sms_agente", "rs_art_sms_agente",
     f"{PASTA_DO_AGENTE}/sms.jsonl", ler_sms_do_agente,
     ("momento", "direcao", "numero", "conteudo", "lida")),
    ("mms_agente", "rs_art_mms_agente",
     f"{PASTA_DO_AGENTE}/mms.jsonl", ler_mms_do_agente,
     ("momento", "direcao", "numero", "assunto", "conteudo", "anexo", "lida")),
)

# Artefatos que moram em banco SQLite, e nao em saida de texto. Sao
# localizados por BUSCA, e nao por caminho fixo: o nome do `mailstore`
# carrega o endereco da conta, o WhatsApp tem pacote comum e Business, e a
# profundidade muda conforme o modulo que fez a aquisicao.
FONTES_BANCO = (
    (
        "whatsapp",
        "rs_art_whatsapp",
        (
            "**/com.whatsapp/databases/msgstore.db",
            "**/com.whatsapp.w4b/databases/msgstore.db",
        ),
        ler_whatsapp,
        COLUNAS_WHATSAPP,
    ),
    (
        "email",
        "rs_art_email",
        (
            "**/com.google.android.gm/databases/mailstore*.db",
            "**/databases/mailstore*.db",
            # O Gmail atual grava em `bigTopDataDB.<conta>`, sem extensao.
            # O leitor ainda NAO interpreta esse formato -- mas o banco
            # precisa ser ENCONTRADO: sem este padrao, um acervo que esta
            # na pasta era reportado como "NAO COLETADO". Encontrado, o
            # leitor o recusa nomeando as tabelas, que e a verdade.
            "**/com.google.android.gm/databases/bigTopDataDB*",
        ),
        ler_email,
        COLUNAS_EMAIL,
    ),
)

# Artefatos do backup do iPhone: (chave, título, fonte em
# `core.backup_ios.ARQUIVOS_DE_INTERESSE`, colunas). Numa aquisição de
# iPhone substituem os do Android, que lá não teriam onde estar.
FONTES_IOS = (
    ("sms_ios", "rs_art_sms_ios", "sms",
     mensagens_ios.COLUNAS_SMS),
    ("chamada_ios", "rs_art_chamada_ios", "chamadas",
     mensagens_ios.COLUNAS_CHAMADAS),
    ("contato_ios", "rs_art_contato_ios", "contatos",
     mensagens_ios.COLUNAS_CONTATOS),
    ("whatsapp_ios", "rs_art_whatsapp_ios", "whatsapp",
     mensagens_ios.COLUNAS_WHATSAPP),
)

# Coluna -> chave de tradução do rótulo. O dado da célula nunca é
# traduzido; só o cabeçalho da coluna, que é cromo do documento.
ROTULOS = {
    "momento": "rs_col_momento",
    # "Tipo" ficava ao lado de "Tipo de mensagem" na planilha do WhatsApp,
    # duas colunas quase homonimas dizendo coisas diferentes. O que esta
    # coluna informa e o sentido: recebida, enviada, perdida.
    "direcao": "rs_col_direcao",
    "numero": "rs_col_numero",
    "contato": "rs_col_contato",
    "conteudo": "rs_col_conteudo",
    "lida": "rs_col_lida",
    "duracao_segundos": "rs_col_duracao",
    "apresentacao": "rs_col_apresentacao",
    "linha_utilizada": "rs_col_linha",
    "conversa": "rs_col_conversa",
    "tipo": "rs_col_tipo",
    "de": "rs_col_de",
    "para": "rs_col_para",
    "assunto": "rs_col_assunto",
    "anexo": "rs_col_anexo",
    "servico": "rs_col_servico",
    "email": "rs_col_email",
    "hora_gps_utc": "rs_col_hora_gps",
    "latitude": "rs_col_latitude",
    "longitude": "rs_col_longitude",
    "altitude": "rs_col_altitude",
    "camera": "rs_col_camera",
    "foto": "rs_col_foto",
    "mapa": "rs_col_mapa",
}


def rotulo_da_coluna(coluna: str) -> str:
    """Cabeçalho da coluna no idioma ativo; a própria chave se não houver rótulo."""
    chave = ROTULOS.get(coluna)
    return traduzir(chave) if chave else coluna

COLUNAS_LOCAIS = ("momento", "foto", "hora_gps_utc", "latitude", "longitude", "altitude", "camera",
                  "mapa")

# Pastas da aquisição que não são conteúdo do aparelho: as fotos que o
# EXAMINADOR tirou da peça não podem virar "local onde o aparelho esteve".
PASTAS_FORA_DOS_LOCAIS = {"evidencias_fotos", "estado_inicial", "apks", "bugreport",
                          "desfecho", "metodo", "fundamento_legal", "erros"}


@dataclass
class Artefato:
    """Um artefato normalizado, com a conferência da origem junto."""

    chave: str
    titulo: str
    caminho_relativo: str
    presente: bool = False
    resultado: object = None
    sha256: str = ""
    sha256_no_manifesto: str = ""
    colunas: tuple = ()
    # Títulos dos artefatos que trazem o MESMO dado por outra via, e com
    # registros (ver `explicacao`). Preenchido ao fim do levantamento.
    vias_com_dados: list = field(default_factory=list)
    # De QUANDO é o que se lê, quando não é do dia do exame: um backup do
    # WhatsApp retrata o aparelho na data em que foi gravado.
    nota_da_fonte: str = ""

    @property
    def confere_com_o_selo(self) -> Optional[bool]:
        """`None` quando não há selo a comparar — não é o mesmo que conferir."""
        if not self.sha256 or not self.sha256_no_manifesto:
            return None
        return self.sha256.lower() == self.sha256_no_manifesto.lower()

    @property
    def total(self) -> int:
        return self.resultado.total if self.resultado else 0

    @property
    def explicacao(self) -> str:
        """
        Por que este artefato não tem registros — levando em conta as OUTRAS
        vias do mesmo dado.

        A consulta direta ao sistema costuma ser recusada, e os registros
        vêm pelo backup do sistema ou pelo aplicativo agente. Impresso
        sozinho, "o sistema RECUSOU a consulta, não se obteve dado algum"
        ficava ao lado dos mesmos dados obtidos por outra via, e o
        documento parecia se contradizer. A recusa continua dita, porque
        aconteceu; o que muda é dizer que o dado veio, e por onde.
        """
        basica = self.resultado.explicacao_do_vazio if self.resultado else ""
        if not self.vias_com_dados:
            return basica
        inicio = (
            "A consulta DIRETA ao sistema do aparelho foi recusada"
            if self.resultado is not None and self.resultado.acesso_negado
            else "A consulta direta ao sistema do aparelho não retornou registro"
        )
        return (
            f"{inicio}. Os registros foram obtidos por outra via e constam deste "
            f"documento em: {'; '.join(self.vias_com_dados)}."
        )


def linhas_de_resumo(artefatos) -> list:
    """
    Uma linha por artefato, dizendo o que saiu — ou por que não saiu.

    Existe porque um total zero, sozinho, manda o examinador procurar
    planilha que não foi gerada. O motivo estava gravado na procedência,
    num arquivo que ele teria de abrir para descobrir que não havia nada a
    abrir. A explicação precisa chegar junto do resultado.

    Mora no módulo, e não só na propriedade do resultado, porque o caderno
    de conteúdo precisa da mesma lista. Duas redações do mesmo resumo
    divergiriam na primeira correção feita de um lado só.
    """
    linhas = []
    for artefato in artefatos:
        if not artefato.presente:
            linhas.append(traduzir("lr_nao_coletado", titulo=artefato.titulo))
        elif artefato.total:
            linhas.append(
                traduzir("lr_com_registros", titulo=artefato.titulo, n=artefato.total,
                         planilha=artefato.chave)
                + (traduzir("lr_atencao", nota=artefato.nota_da_fonte)
                   if artefato.nota_da_fonte else "")
            )
        else:
            linhas.append(
                traduzir("lr_sem_registros", titulo=artefato.titulo,
                         explicacao=artefato.explicacao)
            )
    return linhas


@dataclass
class ResultadoRelatorio:
    """Desfecho da geração, para a interface relatar sem adivinhar."""

    pasta: Optional[Path] = None
    artefatos: list = field(default_factory=list)
    erro: str = ""
    arquivos_gerados: list = field(default_factory=list)

    @property
    def total_registros(self) -> int:
        return sum(artefato.total for artefato in self.artefatos)

    @property
    def total_descartes(self) -> int:
        return sum(
            len(artefato.resultado.descartes) for artefato in self.artefatos if artefato.resultado
        )

    @property
    def origens_divergentes(self) -> list:
        return [a.caminho_relativo for a in self.artefatos if a.confere_com_o_selo is False]

    @property
    def resumo_por_artefato(self) -> list:
        """Uma linha por artefato — ver `linhas_de_resumo`."""
        return linhas_de_resumo(self.artefatos)


class RelatorioService:
    """Gera o relatório de conteúdo de uma aquisição."""

    @staticmethod
    def gerar(
        pasta_aquisicao: Path,
        fuso=None,
        pasta_destino: Optional[Path] = None,
    ) -> ResultadoRelatorio:
        """
        Normaliza os artefatos da aquisição e grava CSV, PDF e procedência.

        `fuso` é o fuso horário usado para converter as datas do aparelho.
        Quando omitido, as datas ficam em UTC e o relatório declara isso —
        melhor do que aplicar em silêncio o fuso da estação, que pode não ser
        o do aparelho.
        """
        pasta_aquisicao = Path(pasta_aquisicao)
        resultado = ResultadoRelatorio()

        artefatos = RelatorioService._levantar(pasta_aquisicao, fuso)
        resultado.artefatos = artefatos

        if not any(artefato.presente for artefato in artefatos):
            resultado.erro = (
                "Nenhum arquivo bruto de SMS, chamadas, agenda, WhatsApp ou correio "
                "foi encontrado nesta aquisição. Os módulos correspondentes podem não "
                "ter sido executados — o que é diferente de o aparelho não ter esses "
                "dados."
            )
            return resultado

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = Path(pasta_destino) if pasta_destino else (
            pasta_aquisicao.parent / PASTA_RELATORIOS / f"{pasta_aquisicao.name}_{carimbo}"
        )
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            resultado.erro = f"Não foi possível criar a pasta do relatório: {exc}"
            return resultado

        resultado.pasta = destino

        for artefato in artefatos:
            if artefato.presente and artefato.total:
                caminho = RelatorioService._gravar_csv(destino, artefato)
                resultado.arquivos_gerados.append(caminho)

        procedencia = destino / NOME_PROCEDENCIA
        procedencia.write_text(
            "\n".join(RelatorioService._linhas_procedencia(pasta_aquisicao, artefatos, fuso)) + "\n",
            encoding="utf-8",
        )
        resultado.arquivos_gerados.append(procedencia)

        if resultado.total_descartes:
            caminho = RelatorioService._gravar_descartes(destino, artefatos)
            resultado.arquivos_gerados.append(caminho)

        caminho_pdf = RelatorioService._gravar_pdf(destino, pasta_aquisicao, artefatos, fuso)
        if caminho_pdf is not None:
            resultado.arquivos_gerados.append(caminho_pdf)

        # O caderno HTML entra ao lado do PDF, e não no lugar dele, enquanto
        # o formato novo não for usado num trabalho de verdade. Trocar antes
        # disso é como se perdem os dois.
        caminho_caderno = RelatorioService._gravar_caderno(
            destino, pasta_aquisicao, artefatos, fuso
        )
        if caminho_caderno is not None:
            resultado.arquivos_gerados.append(caminho_caderno)

        return resultado

    # ------------------------------------------------------------------
    @staticmethod
    def _levantar(pasta_aquisicao: Path, fuso) -> list:
        """Localiza, normaliza e confere cada artefato contra o selo."""
        hashes_selados = RelatorioService._hashes_do_manifesto(pasta_aquisicao)
        # Os rótulos de interpretação (direção, lida, "não consta na agenda"...)
        # saem no idioma do caso. Não são selo: são leitura feita na hora do
        # relatório sobre o bruto selado, que continua intacto.
        idioma = idioma_do_caso(pasta_aquisicao)
        if e_aquisicao_ios(pasta_aquisicao):
            return RelatorioService._levantar_ios(pasta_aquisicao, hashes_selados, fuso, idioma) + [
                RelatorioService._levantar_locais(pasta_aquisicao, hashes_selados)]

        artefatos = []
        for chave, titulo, relativo, normalizar, colunas in FONTES:
            artefato = Artefato(
                chave=chave, titulo=traduzir(titulo), caminho_relativo=relativo, colunas=colunas
            )
            caminho = pasta_aquisicao / relativo
            if caminho.is_file():
                artefato.presente = True
                artefato.sha256 = calcular_sha256(caminho)
                artefato.sha256_no_manifesto = hashes_selados.get(relativo, "")
                texto = caminho.read_text(encoding="utf-8", errors="replace")
                if normalizar is normalizar_mms:
                    # O MMS é o único artefato de texto espalhado em mais de
                    # um arquivo: texto e números moram nos brutos irmãos.
                    artefato.resultado = normalizar(texto, relativo, fuso, caminho.parent,
                                                    idioma=idioma)
                else:
                    artefato.resultado = normalizar(texto, relativo, fuso, idioma=idioma)
            artefatos.append(artefato)

        for chave, titulo, relativo, ler_backup, colunas in FONTES_BACKUP + FONTES_AGENTE:
            caminho = pasta_aquisicao / relativo
            if not caminho.is_file():
                continue
            artefato = Artefato(
                chave=chave, titulo=traduzir(titulo), caminho_relativo=relativo, colunas=colunas
            )
            artefato.presente = True
            artefato.sha256 = calcular_sha256(caminho)
            artefato.sha256_no_manifesto = hashes_selados.get(relativo, "")
            artefato.resultado = ler_backup(caminho, relativo, fuso, idioma)
            artefatos.append(artefato)

        artefatos.extend(
            RelatorioService._levantar_bancos(pasta_aquisicao, hashes_selados, fuso, idioma)
        )
        artefatos.append(RelatorioService._levantar_locais(pasta_aquisicao, hashes_selados))

        # Liga a consulta direta às vias alternativas do mesmo dado:
        # `sms` a `sms_backup` e `sms_agente`, e assim por diante.
        for artefato in artefatos:
            if artefato.total or not artefato.presente:
                continue
            artefato.vias_com_dados = [
                outro.titulo for outro in artefatos
                if outro.total and outro.chave.startswith(artefato.chave + "_")
            ]
        return artefatos

    @staticmethod
    def _levantar_ios(pasta_aquisicao: Path, hashes_selados: dict, fuso, idioma=None) -> list:
        """
        Os artefatos de uma aquisição de iPhone, lidos do backup local.

        Três desfechos por arquivo, e nenhum é "nenhum registro" sem motivo:
        lido; o backup não o contém (o iOS decide o que entra); ou o backup
        está cifrado e não foi decifrado — então nada se afirma.
        """
        backups = backup_ios.backups_da_aquisicao(pasta_aquisicao)
        artefatos = []
        if not backups:
            for chave, titulo, fonte, colunas in FONTES_IOS:
                artefatos.append(Artefato(
                    chave=chave, titulo=traduzir(titulo), colunas=colunas,
                    caminho_relativo=f"{backup_ios.PASTA}/<UDID>/ — "
                    + backup_ios.ARQUIVOS_DE_INTERESSE[fonte][0].rotulo,
                ))
            return artefatos

        decifrados = pasta_dos_decifrados(pasta_aquisicao)
        with tempfile.TemporaryDirectory(prefix="forense_ios_") as trabalho:
            trabalho = Path(trabalho)
            for numero, backup in enumerate(backups, 1):
                try:
                    cifrado = backup_ios.esta_cifrado(backup)
                except backup_ios.ErroBackupIOS:
                    cifrado = None
                rotulo_do_backup = backup.relative_to(pasta_aquisicao).as_posix()
                for chave, titulo, fonte, colunas in FONTES_IOS:
                    leitor = mensagens_ios.LEITORES[fonte]
                    candidatos = backup_ios.ARQUIVOS_DE_INTERESSE[fonte]
                    for indice, arquivo in enumerate(candidatos):
                        original = backup_ios.caminho_no_backup(backup, arquivo)
                        relativo = original.relative_to(pasta_aquisicao).as_posix()
                        decifrado = (decifrados / rotulo_do_backup / arquivo.dominio
                                     / arquivo.caminho)
                        existe = original.is_file()
                        # Origem alternativa (o WhatsApp Business) só entra
                        # quando o backup a contém.
                        if indice and not existe:
                            continue
                        sufixo = (f"_{indice + 1}" if indice else "") + (
                            f"_b{numero}" if len(backups) > 1 else "")
                        artefato = Artefato(
                            chave=chave + sufixo,
                            titulo=traduzir(titulo) + (f" ({arquivo.dominio})" if indice else ""),
                            caminho_relativo=f"{relativo} [{arquivo.rotulo}]",
                            colunas=colunas,
                        )
                        artefato.presente = True
                        artefatos.append(artefato)
                        if len(backups) > 1:
                            # Com o comum e o cifrado na mesma aquisição, os
                            # dois blocos saíam com o mesmo título.
                            estado = {False: "comum", True: "cifrado"}.get(cifrado)
                            if estado:
                                artefato.titulo = artefato.titulo.replace(
                                    "backup do iPhone", f"backup {estado} do iPhone")
                        vazio = mensagens_ios.resultado_vazio(chave, relativo, fuso, idioma)
                        if existe:
                            artefato.sha256 = calcular_sha256(original)
                            artefato.sha256_no_manifesto = hashes_selados.get(relativo, "")
                        if cifrado is None:
                            vazio.significado_do_vazio = traduzir("ios_lev_manifest", idioma)
                            artefato.resultado = vazio
                        elif cifrado and decifrado.is_file():
                            for forma in ("backup cifrado do iPhone", "backup do iPhone"):
                                if forma in artefato.titulo:
                                    artefato.titulo = artefato.titulo.replace(
                                        forma, f"{forma}, decifrado")
                                    break
                            else:
                                artefato.titulo += " (backup decifrado)"
                            artefato.resultado = leitor(
                                decifrado, trabalho / "leitura", fuso, relativo, idioma)
                        elif cifrado:
                            vazio.significado_do_vazio = traduzir("ios_lev_cifrado", idioma)
                            artefato.resultado = vazio
                        elif not existe:
                            vazio.significado_do_vazio = traduzir(
                                "ios_lev_sem_arquivo", idioma, rotulo=arquivo.rotulo)
                            artefato.resultado = vazio
                        else:
                            copia = backup_ios.materializar(
                                backup, arquivo, trabalho / f"b{numero}" / fonte)
                            artefato.resultado = leitor(
                                copia, trabalho / "leitura", fuso, relativo, idioma)
        return artefatos

    @staticmethod
    def _imagens_da_aquisicao(pasta_aquisicao: Path, trabalho: Path, idioma=None):
        """
        `(caminho no disco, rótulo de origem, caminho sob o selo)` de cada imagem.

        Android: as imagens copiadas do aparelho, em qualquer pasta da
        aquisição que seja conteúdo. iPhone: o rolo da câmera, pelo índice do
        backup (`Manifest.db`) — os arquivos do backup não têm nome nem
        extensão. Backup cifrado não é lido aqui, e isso é dito.
        """
        avisos = []
        imagens = []
        backups = backup_ios.backups_da_aquisicao(pasta_aquisicao)
        if not backups:
            for caminho in sorted(pasta_aquisicao.rglob("*")):
                relativo = caminho.relative_to(pasta_aquisicao)
                if (caminho.suffix.lower() in EXTENSOES_DE_IMAGEM and caminho.is_file()
                        and relativo.parts[0] not in PASTAS_FORA_DOS_LOCAIS):
                    imagens.append((caminho, relativo.as_posix(), relativo.as_posix()))
            return imagens, avisos

        for numero, backup in enumerate(backups, 1):
            try:
                cifrado = backup_ios.esta_cifrado(backup)
            except backup_ios.ErroBackupIOS:
                cifrado = None
            if cifrado is not False:
                avisos.append(
                    traduzir("rs_img_cifrado", idioma, nome=backup.name))
                continue
            with sqlite_forense.abrir(backup / "Manifest.db",
                                      trabalho / f"manifesto_{numero}") as banco:
                if not banco.legivel:
                    avisos.append(traduzir("rs_img_indice_ilegivel", idioma,
                                           nome=backup.name, motivo=banco.motivo))
                    continue
                linhas = banco.conexao.execute(
                    "SELECT fileID, relativePath FROM Files "
                    "WHERE domain = 'CameraRollDomain' AND flags = 1").fetchall()
            for identificador, caminho_no_iphone in linhas:
                if Path(caminho_no_iphone or "").suffix.lower() not in EXTENSOES_DE_IMAGEM:
                    continue
                caminho = backup / identificador[:2] / identificador
                relativo = caminho.relative_to(pasta_aquisicao).as_posix()
                imagens.append((caminho, f"{relativo} [{caminho_no_iphone}]", relativo))
        return imagens, avisos

    @staticmethod
    def _levantar_locais(pasta_aquisicao: Path, hashes_selados: dict) -> "Artefato":
        """
        Locais das fotos: as coordenadas de GPS gravadas no EXIF das imagens.

        Só entram imagens que conferem com o selo; cópias idênticas (a mesma
        foto no backup lógico e no dump) contam uma vez. Imagem com GPS
        inaproveitável vira descarte, com o motivo — nunca some.
        """
        idi = idioma_do_caso(pasta_aquisicao)
        fonte_imagens = traduzir("rs_loc_fonte", idi)
        artefato = Artefato(chave="locais_fotos",
                            titulo=traduzir("rs_art_locais"),
                            caminho_relativo=fonte_imagens,
                            colunas=COLUNAS_LOCAIS)
        resultado = ResultadoNormalizacao(tipo="locais_fotos",
                                          arquivo_de_origem=fonte_imagens, idioma=idi)
        artefato.resultado = resultado
        with tempfile.TemporaryDirectory(prefix="forense_locais_") as trabalho:
            imagens, avisos = RelatorioService._imagens_da_aquisicao(
                pasta_aquisicao, Path(trabalho), idi)
        artefato.presente = bool(imagens) or bool(avisos)

        vistas, sem_gps, repetidas = set(), 0, 0
        for caminho, origem, selado in imagens:
            dados = ler_dados_da_foto(caminho, idi)
            if dados.problema:
                resultado.descartes.append(Descarte(0, origem, dados.problema))
                continue
            if dados.latitude is None:
                sem_gps += 1
                continue
            resumo = calcular_sha256(caminho)
            if hashes_selados.get(selado, "").lower() != resumo.lower():
                resultado.descartes.append(Descarte(
                    0, origem, traduzir("rs_loc_descarte_fora_lacre", idi)))
                continue
            if resumo in vistas:
                repetidas += 1
                continue
            vistas.add(resumo)
            resultado.registros.append(Registro(
                tipo="locais_fotos",
                momento=dados.momento,
                arquivo_de_origem=origem,
                campos={
                    "foto": origem.split("[")[-1].rstrip("]").replace("\\", "/").split("/")[-1],
                    "hora_gps_utc": (dados.hora_gps_utc.strftime("%d/%m/%Y %H:%M:%S UTC")
                                     if dados.hora_gps_utc else ""),
                    "latitude": f"{dados.latitude:.6f}",
                    "longitude": f"{dados.longitude:.6f}",
                    "altitude": f"{dados.altitude:.1f}" if dados.altitude is not None else "",
                    "camera": dados.camera,
                    "mapa": dados.link_do_mapa,
                },
            ))
        resultado.registros.sort(key=lambda r: (r.momento is None, str(r.momento or "")))

        partes = []
        if imagens:
            partes.append(
                traduzir("rs_loc_nota_base", idi, n=len(imagens),
                         com=len(resultado.registros), sem=sem_gps)
                + (traduzir("rs_loc_nota_copias", idi, n=repetidas) if repetidas else "")
                + (traduzir("rs_loc_nota_descartes", idi, n=len(resultado.descartes))
                   if resultado.descartes else "") + ".")
            partes.append(traduzir("rs_loc_nota_exif", idi))
        partes += avisos
        desvio = alerta_do_relogio(desvio_da_aquisicao(pasta_aquisicao))
        if desvio:
            partes.append(desvio)
        artefato.nota_da_fonte = " ".join(partes)

        if not imagens and not avisos and backup_ios.backups_da_aquisicao(
                pasta_aquisicao):
            resultado.significado_do_vazio = traduzir("rs_loc_vazio_ios", idi)
        elif not imagens and not avisos:
            resultado.significado_do_vazio = traduzir("rs_loc_vazio_sem_imagens", idi)
        elif not imagens:
            # Nenhuma imagem foi LIDA (backup cifrado, índice ilegível): dizer
            # "nenhuma traz GPS" seria afirmar sobre o que não se viu.
            resultado.significado_do_vazio = " ".join(avisos)
        elif not resultado.registros:
            resultado.significado_do_vazio = traduzir("rs_loc_vazio_sem_gps", idi)
        return artefato

    @staticmethod
    def _levantar_bancos(pasta_aquisicao: Path, hashes_selados: dict, fuso, idioma=None) -> list:
        """
        Localiza e le os artefatos que moram em banco SQLite.

        A leitura acontece numa pasta temporaria do sistema, e nao dentro da
        aquisicao: abrir um banco faz o SQLite incorporar o WAL ao arquivo, e
        o proprio `core.sqlite_forense` recusa trabalhar dentro do selo.

        Banco NAO localizado tambem vira artefato, com `presente` falso: e o
        que faz o relatorio dizer "NAO COLETADO" em vez de simplesmente omitir
        o WhatsApp da lista. Omissao silenciosa deixaria o leitor concluir que
        nao havia mensagens, quando o modulo que traz o banco pode nem ter
        sido executado.
        """
        artefatos = []
        with tempfile.TemporaryDirectory(prefix="forense_leitura_") as trabalho:
            for chave, titulo, padroes, ler_banco, colunas in FONTES_BANCO:
                encontrados = []
                vistos = set()
                # Procura na aquisição e no que foi DECIFRADO dela (o backup
                # do WhatsApp com chave conhecida), que mora fora do selo.
                raizes = [pasta_aquisicao, pasta_dos_decifrados(pasta_aquisicao)]
                for padrao, raiz in ((p, r) for p in padroes for r in raizes):
                    try:
                        candidatos = sorted(raiz.glob(padrao)) if raiz.is_dir() else []
                    except OSError:
                        continue
                    for caminho in candidatos:
                        if not caminho.is_file():
                            continue
                        # `-wal`, `-shm` e `-journal` completam um banco;
                        # nao sao um banco. Padrao sem extensao os alcanca.
                        if caminho.name.endswith(SUFIXOS_ANEXADOS):
                            continue
                        chave_unica = str(caminho).lower()
                        if chave_unica in vistos:
                            continue
                        vistos.add(chave_unica)
                        encontrados.append(caminho)

                if not encontrados:
                    # O padrao de busca vai no lugar do caminho: diz ao
                    # examinador ONDE se procurou, que e o que permite
                    # verificar se a busca fazia sentido.
                    artefatos.append(
                        Artefato(
                            chave=chave,
                            titulo=traduzir(titulo),
                            caminho_relativo=padroes[0],
                            colunas=colunas,
                        )
                    )
                    continue

                for indice, caminho in enumerate(encontrados, 1):
                    procedencia = ler_procedencia_do_decifrado(caminho)
                    if procedencia:
                        # Banco decifrado: a origem que se confere contra o
                        # selo é o arquivo CIFRADO de onde ele saiu.
                        origem = procedencia.get("origem", "")
                        arquivo_de_origem = pasta_aquisicao / origem
                        artefato = Artefato(
                            chave=chave if len(encontrados) == 1 else f"{chave}_{indice}",
                            titulo=traduzir("rs_art_backup_decifrado", titulo=traduzir(titulo)),
                            caminho_relativo=f"{origem} [decifrado]",
                            colunas=colunas,
                        )
                        artefato.presente = True
                        artefato.sha256 = (
                            calcular_sha256(arquivo_de_origem) if arquivo_de_origem.is_file() else ""
                        )
                        artefato.sha256_no_manifesto = hashes_selados.get(origem, "")
                        artefato.resultado = ler_banco(caminho, Path(trabalho), fuso, idioma)
                        if chave == "whatsapp":
                            artefato.nota_da_fonte = nota_do_backup(
                                pasta_aquisicao, arquivo_de_origem, artefato.sha256,
                                artefato.resultado, fuso, idioma)
                        artefatos.append(artefato)
                        continue
                    relativo = caminho.relative_to(pasta_aquisicao).as_posix()
                    # Um aparelho pode ter mais de uma conta de correio, e
                    # cada `mailstore` e um acervo distinto. Juntar tudo numa
                    # planilha so misturaria caixas de titulares diferentes.
                    sufixo = "" if len(encontrados) == 1 else f"_{indice}"
                    rotulo = (traduzir(titulo) if len(encontrados) == 1
                              else traduzir("rs_art_com_arquivo", titulo=traduzir(titulo),
                                            arquivo=caminho.name))
                    artefato = Artefato(
                        chave=f"{chave}{sufixo}",
                        titulo=rotulo,
                        caminho_relativo=relativo,
                        colunas=colunas,
                    )
                    artefato.presente = True
                    artefato.sha256 = calcular_sha256(caminho)
                    artefato.sha256_no_manifesto = hashes_selados.get(relativo, "")
                    artefato.resultado = ler_banco(caminho, Path(trabalho), fuso, idioma)
                    artefatos.append(artefato)
        return artefatos

    @staticmethod
    def _hashes_do_manifesto(pasta_aquisicao: Path) -> dict:
        """Hashes selados no dia da coleta, por caminho relativo."""
        caminho = localizar_manifesto(pasta_aquisicao)
        if caminho is None:
            return {}
        try:
            return {
                nome.replace("\\", "/"): valor for nome, valor in ler_manifesto(caminho).items()
            }
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------
    @staticmethod
    def _gravar_csv(destino: Path, artefato: Artefato) -> Path:
        """
        Uma planilha por artefato — é onde o analista cruza e filtra.

        `utf-8-sig` porque o Excel em português abre UTF-8 sem BOM como
        Latin-1 e transforma todo acento em caractere estranho. Um relatório
        ilegível na ferramenta que o destinatário usa não cumpriu seu papel.
        """
        caminho = destino / f"{artefato.chave}.csv"
        with open(caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(
                [rotulo_da_coluna(coluna) for coluna in artefato.colunas]
                + [traduzir("rs_csv_h_arquivo_origem"), traduzir("rs_csv_h_linha_origem")]
            )
            for registro in artefato.resultado.registros:
                linha = []
                for coluna in artefato.colunas:
                    if coluna == "momento":
                        linha.append(registro.momento_legivel)
                    else:
                        linha.append(registro.campos.get(coluna, ""))
                linha += [registro.arquivo_de_origem, registro.linha_de_origem]
                escritor.writerow(linha)
        return caminho

    @staticmethod
    def _gravar_descartes(destino: Path, artefatos: list) -> Path:
        """O que o normalizador não compreendeu, por extenso."""
        linhas = [
            "=" * LARGURA,
            traduzir("pr_desc_titulo").center(LARGURA),
            "=" * LARGURA,
            "",
            traduzir("pr_desc_intro"),
            "",
        ]
        for artefato in artefatos:
            if not artefato.resultado or not artefato.resultado.descartes:
                continue
            linhas += ["-" * LARGURA, f"{artefato.titulo} — {artefato.caminho_relativo}", ""]
            for descarte in artefato.resultado.descartes:
                linhas += [
                    traduzir("pr_desc_linha", n=descarte.linha_de_origem, motivo=descarte.motivo),
                    f"    {descarte.texto}",
                    "",
                ]

        caminho = destino / NOME_DESCARTES
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        return caminho

    # ------------------------------------------------------------------
    @staticmethod
    def _linhas_procedencia(pasta_aquisicao: Path, artefatos: list, fuso) -> list:
        linhas = [
            "=" * LARGURA,
            traduzir("pr_titulo").center(LARGURA),
            "=" * LARGURA,
            traduzir("pr_l_aquisicao", valor=pasta_aquisicao.name),
            traduzir("pr_l_gerado",
                     valor=datetime.now().astimezone().isoformat(timespec='seconds')),
            traduzir("pr_l_normalizador", v=VERSAO_NORMALIZADOR),
            traduzir("pr_l_fuso", valor=RelatorioService._nome_do_fuso(artefatos, fuso)),
            "=" * LARGURA,
            "",
        ]

        divergentes = [a for a in artefatos if a.confere_com_o_selo is False]
        if divergentes:
            linhas += [
                "!" * LARGURA,
                traduzir("pr_div_titulo").center(LARGURA),
                "!" * LARGURA,
                "",
                traduzir("pr_div_intro"),
                "",
            ]
            linhas += [f"  - {a.caminho_relativo}" for a in divergentes]
            linhas += ["", "!" * LARGURA, ""]

        for artefato in artefatos:
            linhas.append(f"[{artefato.titulo}]")
            linhas.append(traduzir("pr_l_arquivo_origem", valor=artefato.caminho_relativo))

            if not artefato.presente:
                linhas += [traduzir("pr_nao_encontrado"), ""]
                continue

            linhas.append(traduzir("pr_l_sha_agora", valor=artefato.sha256))
            if artefato.sha256_no_manifesto:
                confere = artefato.confere_com_o_selo
                linhas.append(traduzir("pr_l_sha_selo", valor=artefato.sha256_no_manifesto))
                linhas.append(traduzir(
                    "pr_l_conferencia",
                    valor=traduzir("pr_conf_confere") if confere else traduzir("pr_conf_diverge"),
                ))
            else:
                linhas.append(traduzir("pr_sem_manifesto"))

            linhas.append(traduzir("pr_l_registros", n=artefato.total))
            if artefato.nota_da_fonte:
                linhas.append(traduzir("pr_l_nota_fonte", valor=artefato.nota_da_fonte))
            if not artefato.total:
                linhas.append(traduzir("pr_l_por_que_zero", valor=artefato.explicacao))
            if artefato.resultado.descartes:
                linhas.append(traduzir("pr_l_nao_interpretado",
                                       n=len(artefato.resultado.descartes), arquivo=NOME_DESCARTES))
            linhas.append("")

        linhas += [
            "-" * LARGURA,
            traduzir("pr_alcance_titulo"),
            "",
            traduzir("pr_alcance"),
            "-" * LARGURA,
            "=" * LARGURA,
        ]
        return linhas

    @staticmethod
    def _nome_do_fuso(artefatos: list, fuso) -> str:
        for artefato in artefatos:
            if artefato.resultado is not None:
                return artefato.resultado.fuso_declarado
        return "UTC (nenhum fuso informado)"

    # ------------------------------------------------------------------
    @staticmethod
    def _gravar_caderno(destino: Path, pasta_aquisicao: Path, artefatos: list, fuso):
        """
        Caderno de conteúdo em HTML — a apresentação que se lê e se cola.

        Mesmo esqueleto do caderno da aquisição, pelo mesmo motivo: o
        analista copia o bloco que interessa para o documento que ele
        escreve, ou imprime aquele bloco isolado em PDF. As planilhas
        continuam intactas ao lado — elas é que são o dado para cruzar e
        filtrar, e nenhuma delas é substituída por isto.

        HTML aguenta o volume que o PDF não aguenta: cinco mil mensagens
        viram um arquivo que abre e rola, e não centenas de páginas.

        **O aviso de divergência viaja dentro do bloco.** Ele já existia no
        topo do documento, o que bastava enquanto o documento era lido
        inteiro. Aqui cada bloco é copiado sozinho: uma tabela de SMS
        colada num relatório, sem o alerta que ficou lá atrás, apresentaria
        como íntegro um conteúdo cuja origem não confere mais com o selo.
        Por isso o alerta é repetido em cada artefato divergente.
        """
        try:
            from services.caderno_service import escapar, montar_documento, tabela
        except ImportError:
            return None

        nome_fuso = RelatorioService._nome_do_fuso(artefatos, fuso)
        manifesto = localizar_manifesto(pasta_aquisicao)
        hash_manifesto = calcular_sha256(manifesto) if manifesto else ""
        if hash_manifesto:
            rastreio = traduzir(
                "cc_rastreio_com", nome=escapar(pasta_aquisicao.name),
                hash=escapar(hash_manifesto), v=escapar(VERSAO_NORMALIZADOR))
        else:
            rastreio = traduzir("cc_rastreio_sem", nome=escapar(pasta_aquisicao.name))

        divergentes = [a for a in artefatos if a.confere_com_o_selo is False]
        alerta_divergencia = traduzir("cc_alerta_divergencia")

        secoes = []

        # --- identificação -------------------------------------------------
        secoes.append((
            traduzir("cc_sec_identificacao"),
            tabela(
                [traduzir("cc_h_parametro"), traduzir("cc_h_valor")],
                [
                    [traduzir("cc_l_aquisicao_origem"), escapar(pasta_aquisicao.name)],
                    [traduzir("cc_l_fuso"), escapar(nome_fuso)],
                    [traduzir("cc_l_versao_norm"), escapar(VERSAO_NORMALIZADOR)],
                    [traduzir("cc_l_planilhas"),
                     escapar(traduzir("cc_planilhas_valor", n=len(artefatos)))],
                ],
                ["35%", "65%"],
            )
            + traduzir("cc_nota_identificacao"),
        ))

        # --- conferência da origem -----------------------------------------
        linhas = []
        for artefato in artefatos:
            if not artefato.presente:
                situacao = traduzir("cc_sit_nao_coletado")
            elif artefato.confere_com_o_selo is True:
                situacao = traduzir("cc_sit_confere")
            elif artefato.confere_com_o_selo is False:
                situacao = traduzir("cc_sit_nao_confere")
            else:
                situacao = traduzir("cc_sit_sem_selo")
            linhas.append([
                escapar(artefato.titulo),
                escapar(artefato.caminho_relativo),
                situacao,
                f"<span class='mono'>{escapar(artefato.sha256[:32] or '—')}</span>",
            ])
        corpo = tabela(
            [traduzir("cc_conf_h_artefato"), traduzir("cc_conf_h_arquivo"),
             traduzir("cc_conf_h_conferencia"), traduzir("cc_conf_h_sha")],
            linhas,
            ["22%", "33%", "20%", "25%"],
        )
        if divergentes:
            corpo = alerta_divergencia + corpo
        corpo += traduzir("cc_nota_sem_selo")
        secoes.append((traduzir("cc_sec_conferencia"), corpo))

        # --- resumo ----------------------------------------------------------
        itens = "".join(
            f"<li>{escapar(linha)}</li>"
            for linha in linhas_de_resumo(artefatos)
        )
        secoes.append((
            traduzir("cc_sec_resumo"),
            f"<ul>{itens}</ul>" + traduzir("cc_nota_resumo"),
        ))

        # --- um bloco por artefato -------------------------------------------
        for artefato in artefatos:
            if not artefato.presente or not artefato.resultado:
                continue
            cabecalho = [rotulo_da_coluna(c) for c in artefato.colunas] + [traduzir("cc_h_origem")]
            linhas = []
            for registro in artefato.resultado.registros:
                celulas = []
                for coluna in artefato.colunas:
                    if coluna == "momento":
                        celulas.append(escapar(registro.momento_legivel))
                    else:
                        celulas.append(escapar(registro.campos.get(coluna, "")))
                celulas.append(
                    escapar(f"{registro.arquivo_de_origem}:{registro.linha_de_origem}")
                )
                linhas.append(celulas)

            if linhas:
                corpo = tabela(cabecalho, linhas)
            else:
                corpo = traduzir("cc_nenhum_registro", explicacao=escapar(artefato.explicacao))

            if artefato.nota_da_fonte:
                corpo = traduzir("cc_nota_fonte",
                                 valor=escapar(artefato.nota_da_fonte)) + corpo
            if artefato.confere_com_o_selo is False:
                corpo = alerta_divergencia + corpo

            corpo += traduzir("cc_nota_planilha", planilha=escapar(artefato.chave))
            secoes.append((
                traduzir("cc_sec_artefato", titulo=artefato.titulo, total=artefato.total),
                corpo,
            ))

        # --- não interpretado -------------------------------------------------
        com_descarte = [
            a for a in artefatos if a.resultado and a.resultado.descartes
        ]
        if com_descarte:
            partes = [traduzir("cc_descarte_alerta")]
            for artefato in com_descarte:
                linhas = [
                    [
                        escapar(d.linha_de_origem),
                        escapar(d.motivo),
                        f"<span class='mono'>{escapar(d.texto[:200])}</span>",
                    ]
                    for d in artefato.resultado.descartes
                ]
                partes.append(f"<h3>{escapar(artefato.titulo)}</h3>")
                partes.append(
                    tabela([traduzir("cc_descarte_h_linha"), traduzir("cc_descarte_h_motivo"),
                            traduzir("cc_descarte_h_trecho")], linhas, ["10%", "30%", "60%"])
                )
            corpo = "".join(partes)
        else:
            corpo = traduzir("cc_descarte_nenhum")
        secoes.append((traduzir("cc_sec_descartes"), corpo))

        caminho = destino / NOME_CADERNO
        documento = montar_documento(
            titulo=traduzir("cc_titulo_doc", nome=pasta_aquisicao.name),
            capa=traduzir("cc_capa", nome=escapar(pasta_aquisicao.name)),
            secoes=secoes,
            rastreio=rastreio,
        )
        try:
            caminho.write_text(documento, encoding="utf-8")
        except OSError:
            return None
        return caminho

    @staticmethod
    def _gravar_pdf(destino: Path, pasta_aquisicao: Path, artefatos: list, fuso):
        """
        PDF consolidado do conteúdo, com a identidade da suíte.

        Falha na geração do PDF não invalida o relatório: as planilhas e a
        procedência já estão gravadas, e são elas que sustentam o trabalho.
        Por isso o erro é devolvido como ausência, e não propagado.
        """
        try:
            from reportlab.platypus import Paragraph, Spacer

            from core.case import pasta_do_caso
            from services import identidade_pdf as identidade
        except ImportError:
            return None

        caminho = destino / NOME_PDF
        e = identidade.estilos()
        largura_util = identidade.largura_util(paisagem=True)  # mensagem não cabe em retrato

        manifesto = localizar_manifesto(pasta_aquisicao)
        selo = calcular_sha256(manifesto) if manifesto else ""

        historia = [
            Paragraph(traduzir("rs_pdf_titulo"), e["titulo"]),
            Paragraph(
                traduzir("rs_pdf_subtitulo",
                         aquisicao=RelatorioService._escapar(pasta_aquisicao.name)),
                e["subtitulo"],
            ),
            identidade.tabela_de_pares([
                (traduzir("rs_pdf_l_aquisicao"), identidade.escapar(pasta_aquisicao.name)),
                (traduzir("rs_pdf_l_gerado"),
                 datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S %z")),
                (traduzir("rs_pdf_l_fuso"), identidade.escapar(
                    RelatorioService._nome_do_fuso(artefatos, fuso))),
                (traduzir("rs_pdf_l_normalizador"),
                 traduzir("rs_pdf_versao", v=VERSAO_NORMALIZADOR)),
            ], largura_util, proporcao=0.2),
            Spacer(1, 8),
        ]

        divergentes = [a for a in artefatos if a.confere_com_o_selo is False]
        if divergentes:
            historia.append(Paragraph(
                traduzir("rs_pdf_divergencia", lista=RelatorioService._escapar(
                    ", ".join(a.caminho_relativo for a in divergentes))),
                e["alerta"],
            ))
            historia.append(Spacer(1, 8))

        for artefato in artefatos:
            historia.append(Paragraph(RelatorioService._escapar(artefato.titulo), e["secao"]))

            if not artefato.presente:
                historia.append(Paragraph(traduzir("rs_pdf_nao_encontrado"), e["corpo"]))
                continue

            if not artefato.total:
                historia.append(Paragraph(
                    traduzir("rs_pdf_nenhum_registro",
                             explicacao=RelatorioService._escapar(artefato.explicacao)),
                    e["corpo"],
                ))
                continue

            origem = RelatorioService._escapar(artefato.caminho_relativo)
            historia.append(Paragraph(
                traduzir("rs_pdf_origem_sha", n=artefato.total, origem=origem,
                         sha=artefato.sha256) if artefato.sha256
                else traduzir("rs_pdf_origem_selo", n=artefato.total, origem=origem),
                e["esquerda"],
            ))
            if artefato.nota_da_fonte:
                historia.append(Paragraph(
                    traduzir("rs_pdf_nota_fonte",
                             valor=RelatorioService._escapar(artefato.nota_da_fonte)),
                    e["alerta"]))
            historia.append(Spacer(1, 4))

            if RelatorioService._vai_como_indice(artefato):
                historia += RelatorioService._indice_do_artefato(artefato, largura_util, e)
            else:
                linhas = []
                for registro in artefato.resultado.registros:
                    linhas.append([
                        RelatorioService._celula_do_pdf(registro, coluna)
                        for coluna in artefato.colunas
                    ])
                historia.append(identidade.tabela(
                    [rotulo_da_coluna(c) for c in artefato.colunas],
                    linhas,
                    RelatorioService._larguras(artefato.colunas, largura_util),
                ))

            if artefato.resultado.descartes:
                historia.append(Spacer(1, 4))
                historia.append(Paragraph(
                    traduzir("rs_pdf_descartes", n=len(artefato.resultado.descartes),
                             arquivo=NOME_DESCARTES),
                    e["corpo"],
                ))

        historia.append(Spacer(1, 12))
        historia.append(Paragraph(
            traduzir("rs_pdf_rodape_nota", procedencia=NOME_PROCEDENCIA),
            e["nota"],
        ))

        try:
            identidade.montar_documento(
                caminho,
                traduzir("rs_pdf_titulo_doc"),
                historia,
                rastreio=f"{pasta_do_caso(pasta_aquisicao).name}  ·  {pasta_aquisicao.name}",
                selo=selo,
                paisagem=True,
                teste=_aquisicao_de_teste(pasta_aquisicao),
            )
        except Exception:
            return None
        return caminho

    @staticmethod
    def _vai_como_indice(artefato) -> bool:
        """
        Conversas volumosas vão para o PDF como ÍNDICE, não na íntegra.

        Um WhatsApp de uso real tem dezenas de milhares de mensagens: na
        íntegra, o PDF passava de mil páginas. A íntegra continua na planilha
        e no caderno HTML desta mesma pasta, e o examinador gera o PDF
        completo das conversas que escolher ("PDF de conversas selecionadas").
        """
        from services.conversas_service import e_artefato_de_conversa

        return e_artefato_de_conversa(artefato.chave) and artefato.total > LIMITE_INTEGRA_NO_PDF

    @staticmethod
    def _indice_do_artefato(artefato, largura_util: float, e) -> list:
        from reportlab.platypus import Paragraph, Spacer

        from services import identidade_pdf as identidade
        from services.conversas_service import agrupar

        conversas = agrupar(artefato)
        linhas = [
            [
                RelatorioService._escapar(conversa.rotulo),
                RelatorioService._escapar(conversa.nome),
                str(conversa.quantidade),
                RelatorioService._escapar(conversa.periodo),
            ]
            for conversa in conversas
        ]
        return [
            Paragraph(
                traduzir("rs_idx_resumo", total=artefato.total, n=len(conversas),
                         limite=LIMITE_INTEGRA_NO_PDF, planilha=artefato.chave,
                         caderno=NOME_CADERNO),
                e["esquerda"],
            ),
            Spacer(1, 4),
            identidade.tabela(
                [traduzir("rs_idx_h_conversa"), traduzir("rs_idx_h_nome"),
                 traduzir("rs_idx_h_mensagens"), traduzir("rs_idx_h_periodo")],
                linhas,
                [largura_util * 0.38, largura_util * 0.3, largura_util * 0.1,
                 largura_util * 0.22],
            ),
        ]

    @staticmethod
    def _escapar(texto: str) -> str:
        """Conteúdo de mensagem pode trazer `<` e `&`, que quebram o PDF."""
        return (
            str(texto)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _celula_do_pdf(registro, coluna: str) -> str:
        if coluna == "momento":
            return RelatorioService._escapar(registro.momento_legivel)
        valor = str(registro.campos.get(coluna, ""))
        if coluna == "mapa" and valor:
            # O endereço inteiro quebrava em três linhas na coluna; o link
            # continua lá, clicável, e as coordenadas estão nas colunas ao lado.
            return f'<link href="{RelatorioService._escapar(valor)}" color="blue">abrir no mapa</link>'
        if coluna == "anexo" and valor:
            # O caminho inteiro quebrava em até oito linhas e cada foto ocupava
            # um terço da página. Fica o nome; o caminho completo está na
            # planilha e no caderno, ao lado do arquivo de origem.
            return RelatorioService._escapar(valor.replace("\\", "/").rsplit("/", 1)[-1])
        mapa = str(registro.campos.get("mapa", ""))
        if coluna == "conteudo" and mapa:
            # Localização compartilhada no WhatsApp: a tabela de mensagens não
            # tem coluna de mapa, então o link vai junto das coordenadas.
            return (RelatorioService._escapar(valor) + f' <link href="{RelatorioService._escapar(mapa)}"'
                    ' color="blue">abrir no mapa</link>')
        return RelatorioService._escapar(valor)

    @staticmethod
    def _larguras(colunas: tuple, largura_util: float) -> list:
        """O conteúdo da mensagem recebe o espaço que sobra das demais."""
        pesos = {
            "momento": 1.5, "direcao": 1.0, "numero": 1.5, "contato": 1.8,
            "lida": 0.6, "duracao_segundos": 0.8, "conteudo": 4.5,
        }
        total = sum(pesos.get(coluna, 1.0) for coluna in colunas)
        return [largura_util * pesos.get(coluna, 1.0) / total for coluna in colunas]


SUFIXO_PROCEDENCIA = ".procedencia.json"


NOME_DATAS_DOS_BACKUPS = "datas_dos_backups.json"


def _momento(epoch: float, fuso) -> datetime:
    from datetime import timezone

    momento = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return momento.astimezone(fuso) if fuso is not None else momento


def nota_do_backup(pasta_aquisicao: Path, arquivo_de_origem: Path, sha256: str, resultado,
                   fuso=None, idioma=None) -> str:
    """
    De quando é o conteúdo de um backup do WhatsApp — dito no documento.

    A data de gravação vem, de preferência, do registro feito NA aquisição
    (o aparelho respondeu, e a resposta está sob o lacre). Aquisição antiga,
    sem esse registro, usa a data do arquivo preservada pela cópia, e diz
    que ela não foi registrada no lacre. Junto vai a mensagem mais recente
    contida no backup, que vem do próprio conteúdo.
    """
    gravado, fonte = None, ""
    for registro_json in Path(pasta_aquisicao).rglob(NOME_DATAS_DOS_BACKUPS):
        try:
            registros = json.loads(registro_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for registro in registros if isinstance(registros, list) else []:
            epoch = registro.get("gravado_no_aparelho_epoch")
            if registro.get("sha256", "").lower() == (sha256 or "").lower() and epoch:
                gravado = _momento(epoch, fuso)
                fonte = traduzir("rs_nota_fonte_aparelho", idioma)
                break
        if gravado:
            break
    if gravado is None and Path(arquivo_de_origem).is_file():
        gravado = _momento(Path(arquivo_de_origem).stat().st_mtime, fuso)
        fonte = traduzir("rs_nota_fonte_arquivo", idioma)
    momentos = [r.momento for r in getattr(resultado, "registros", []) if r.momento]
    partes = []
    if gravado:
        partes.append(traduzir("rs_nota_backup_com_data", idioma,
                               data=gravado.strftime('%d/%m/%Y %H:%M'), fonte=fonte))
    else:
        partes.append(traduzir("rs_nota_backup_sem_data", idioma))
    if momentos:
        partes.append(traduzir("rs_nota_mais_recente", idioma,
                               data=max(momentos).strftime('%d/%m/%Y %H:%M')))
    partes.append(traduzir("rs_nota_posteriores", idioma))
    return " ".join(partes)


def ler_procedencia_do_decifrado(caminho: Path) -> dict:
    """
    A procedência gravada ao lado de um banco decifrado, ou vazio quando o
    arquivo não é um decifrado. É ela que liga o banco em claro ao arquivo
    cifrado da aquisição — sem isso ele seria um banco sem origem.
    """
    ao_lado = Path(str(caminho) + SUFIXO_PROCEDENCIA)
    if not ao_lado.is_file():
        return {}
    try:
        dados = json.loads(ao_lado.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _aquisicao_de_teste(pasta_aquisicao: Path) -> bool:
    from core.operador import ler_da_aquisicao

    lido = ler_da_aquisicao(Path(pasta_aquisicao))
    return bool(lido and lido[0].de_teste)


def e_aquisicao_ios(pasta_aquisicao: Path) -> bool:
    """`True` para aquisição de iPhone: pelo nome (`ios_...`) ou pelo backup nela."""
    pasta_aquisicao = Path(pasta_aquisicao)
    return pasta_aquisicao.name.lower().startswith("ios_") or bool(
        backup_ios.backups_da_aquisicao(pasta_aquisicao)
    )


def levantar_artefatos(pasta_aquisicao, fuso=None) -> list:
    """
    Os artefatos de conteúdo da aquisição, interpretados e conferidos
    contra o selo. É a mesma leitura que alimenta o relatório de conteúdo:
    os demais documentos a reutilizam em vez de reinterpretar.
    """
    return RelatorioService._levantar(Path(pasta_aquisicao), fuso)
