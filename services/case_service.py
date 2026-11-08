"""
Serviço de gerenciamento de casos e diretórios de extração.
Responsável por sugerir identificadores e listar projetos existentes.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.protocolos import gravar_respostas
from core.case import (
    CAMPOS_DO_CASO,
    CAMPOS_DO_DISPOSITIVO,
    NAO_INFORMADO,
    NOME_CADEIA_CUSTODIA,
    PASTA_FOTOS,
    criar_pasta_aquisicao,
    descrever_aquisicao,
    e_pasta_de_aquisicao,
    gravar_caso,
    juntar_complemento,
    ler_caso,
    montar_cadeia_custodia,
    registrar_info_caso,
    sanitizar_nome,
    substituir_campos_da_cadeia,
    sugerir_proximo_identificador,
    tem_registro_do_caso,
)
from core.fundamento import (
    TipoDocumento,
    anexar_documento,
    anexar_documentos,
    gravar_autorizacao_da_aquisicao,
    ler_autorizacao,
)
from core.hashing import gerar_manifesto, localizar_manifesto
from core.operador import NAO_DECLARADO, conta_da_estacao, de_dicionario
from core.operador import ler_da_aquisicao as ler_operador_da_aquisicao
from core.operador import gravar_na_aquisicao as gravar_operador_na_aquisicao
from core.procedimento import RegistroProcedimento


# ---------------------------------------------------------------------------
# Leitura de casos já gravados, para o Gerenciador de Projetos.
#
# Vive aqui, e não na janela, por dois motivos. O primeiro é a regra da
# arquitetura: `ui/` apresenta, não faz IO nem interpreta registro de
# evidência. O segundo é que a janela fazia esse trabalho com
# `linha.startswith("Equipamento:")` espalhado em quatro métodos, e cada
# cópia era uma chance de duas telas discordarem sobre o mesmo caso.
# ---------------------------------------------------------------------------

# Rótulos do `cadeia_custodia.txt` que NÃO descrevem o caso: os da peça e os
# de controle. Num caso antigo, sem `caso.json`, tudo o mais que a aquisição
# traz é tratado como dado do caso — sem que este módulo precise conhecer
# os nomes dos campos de então.
ROTULOS_FORA_DO_CASO = frozenset(
    [rotulo for _, rotulo in CAMPOS_DO_DISPOSITIVO] + ["Caso", "Tipo Projeto", "Fotos Anexas"]
)

# Valores que significam "ninguém preencheu", nos registros de hoje e nos antigos.
VALORES_VAZIOS = frozenset(["", "N/A", NAO_INFORMADO])


def campos_do_caso() -> list:
    """(chave, rótulo) dos dados do caso, para a interface montar o formulário."""
    return list(CAMPOS_DO_CASO)


@dataclass
class ResumoAquisicao:
    """Uma aquisição dentro de um caso, como a interface precisa vê-la."""

    pasta: Path
    plataforma: str
    momento: Optional[datetime]
    selada: bool
    arquivo_custodia: Optional[Path]
    dados: Dict[str, str] = field(default_factory=dict)
    # Quem executou, como ficou gravado na aquisição (ver `examinador_da_aquisicao`).
    examinador: str = ""

    def _campo(self, rotulo: str) -> str:
        valor = self.dados.get(rotulo, "")
        return "Não informado" if valor in VALORES_VAZIOS else valor

    @property
    def equipamento(self) -> str:
        return self._campo("Equipamento")

    @property
    def lacre(self) -> str:
        return self._campo("Lacre")

    @property
    def rotulo(self) -> str:
        data = self.momento.strftime("%d/%m/%Y %H:%M") if self.momento else "sem data"
        return f"{self.plataforma} · {data} · {self.equipamento} · lacre {self.lacre}"


@dataclass
class ResumoCaso:
    """
    Um caso, com o suficiente para ser reconhecido SEM ser aberto.

    `dados_do_caso` vai de rótulo a valor. Num caso com `caso.json`
    (`tem_registro`), vem dele. Num caso antigo vem do que as aquisições
    traziam — e aí duas aquisições podem discordar: `campos_divergentes`
    existe para a ficha mostrar a divergência em vez de escolher uma das
    versões em silêncio.
    """

    pasta: Path
    identificador: str
    aquisicoes: List[ResumoAquisicao] = field(default_factory=list)
    dados_do_caso: Dict[str, str] = field(default_factory=dict)
    campos_divergentes: List[str] = field(default_factory=list)
    documentos: List[dict] = field(default_factory=list)
    complementos: int = 0
    tem_registro: bool = False

    @property
    def reconhecimento(self) -> List[str]:
        """Os dados preenchidos do caso, para a linha que o identifica na lista."""
        return [valor for valor in self.dados_do_caso.values() if valor][:2]

    @property
    def examinadores(self) -> List[str]:
        """Examinadores das aquisições do caso, sem repetir, na ordem em que aparecem."""
        vistos: List[str] = []
        for aquisicao in self.aquisicoes:
            if aquisicao.examinador and aquisicao.examinador not in vistos:
                vistos.append(aquisicao.examinador)
        return vistos

    @property
    def lacres(self) -> List[str]:
        """Lacres distintos das peças do caso, na ordem das aquisições."""
        vistos: List[str] = []
        for aquisicao in self.aquisicoes:
            if aquisicao.lacre != "Não informado" and aquisicao.lacre not in vistos:
                vistos.append(aquisicao.lacre)
        return vistos

    @property
    def ultima_atividade(self) -> Optional[datetime]:
        momentos = [a.momento for a in self.aquisicoes if a.momento]
        return max(momentos) if momentos else None

    @property
    def metadados_divergentes(self) -> bool:
        return bool(self.campos_divergentes)


def examinador_da_aquisicao(pasta_aquisicao: Path) -> str:
    """
    O examinador como ficou gravado NA aquisição, sob o selo — e não o
    cadastro de hoje, que pode ter sido editado depois.

    Aquisição anterior ao registro de operador e operador não declarado são
    situações diferentes, e o texto diz qual das duas.
    """
    lido = ler_operador_da_aquisicao(pasta_aquisicao)
    if lido is None:
        return "examinador não registrado"
    operador, _conta = lido
    return operador.nome.strip() if operador.declarado else f"examinador {NAO_DECLARADO}"


def ler_cadeia_custodia(arquivo: Path) -> Dict[str, str]:
    """
    Lê um `cadeia_custodia.txt` como pares `chave: valor`.

    Linhas de cabeçalho (`=== ... ===`) não têm dois-pontos e caem fora
    naturalmente. Valor vazio é preservado como vazio: campo em branco é
    informação — significa que ninguém preencheu —, e trocá-lo por um
    traço faria a tela afirmar o que o registro não diz.
    """
    dados: Dict[str, str] = {}
    try:
        conteudo = arquivo.read_text(encoding="utf-8")
    except OSError:
        return dados
    for linha in conteudo.splitlines():
        if ":" not in linha or linha.startswith("="):
            continue
        chave, valor = linha.split(":", 1)
        dados[chave.strip()] = valor.strip()
    return dados


class CaseService:
    def __init__(self, pasta_raiz: Path):
        self.pasta_raiz = pasta_raiz
        # Registro do procedimento do caso atualmente aberto. Fica aqui,
        # e nao na UI, para que `ui/` continue sem nenhum `import core...`.
        self._registro: Optional[RegistroProcedimento] = None

    # ------------------------------------------------------------------
    # Registro do procedimento (ISO/IEC 27037): ambiente, relogio,
    # decisoes metodologicas e alteracoes provocadas no dispositivo.
    # ------------------------------------------------------------------
    def abrir_registro_procedimento(
        self, pasta_caso: Path, identificador_caso: str, plataforma: str, id_dispositivo: str
    ) -> None:
        self._registro = RegistroProcedimento(pasta_caso)
        self._registro.abrir(identificador_caso, plataforma, id_dispositivo)

    def registrar_operador(self, pasta_aquisicao: Path, perfil: dict) -> str:
        """
        Grava o operador no registro do procedimento e em `operador.json`
        dentro da aquisição — antes do selo. Devolve o resumo de uma linha.
        """
        operador = de_dicionario(perfil)
        conta = conta_da_estacao()
        if self._registro is not None:
            self._registro.registrar_operador(operador.em_linhas(), conta)
        try:
            gravar_operador_na_aquisicao(pasta_aquisicao, operador, conta)
        except OSError:
            # Como todo o diário: falha de anotação não interrompe aquisição.
            pass
        return operador.resumo()

    def registrar_ambiente(self, versao_adb: Optional[str] = None) -> None:
        if self._registro is not None:
            self._registro.registrar_ambiente(versao_adb)

    def registrar_relogio(self, resumo_relogio: str) -> None:
        if self._registro is not None:
            self._registro.registrar_relogio(resumo_relogio)

    def registrar_decisao(self, decisao: str, motivo: str) -> None:
        if self._registro is not None:
            self._registro.registrar_decisao(decisao, motivo)

    def registrar_alteracao(self, alteracao: str, justificativa: str) -> None:
        if self._registro is not None:
            self._registro.registrar_alteracao(alteracao, justificativa)

    def encerrar_registro_procedimento(self, resumo: str) -> None:
        if self._registro is not None:
            self._registro.encerrar(resumo)

    # ------------------------------------------------------------------
    # Autorização de acesso aos dados
    # ------------------------------------------------------------------
    @staticmethod
    def aquisicao_selada(pasta: Path) -> bool:
        """Se a pasta já tem manifesto — e portanto não pode ser reescrita."""
        return localizar_manifesto(Path(pasta)) is not None

    def pasta_do_caso(self, identificador: str) -> Path:
        """Pasta do caso a partir do identificador digitado."""
        return self.pasta_raiz / sanitizar_nome(identificador)

    def documentos_do_caso(self, identificador: str) -> list[dict]:
        """
        Documentos de autorização já anexados a este caso, em campos simples.

        Serve para a interface mostrar o que o caso já tem: da segunda
        aquisição em diante a mesma decisão cobre o novo aparelho, e anexar
        de novo o mesmo PDF só produziria duplicidade.
        """
        autorizacao = ler_autorizacao(self.pasta_do_caso(identificador))
        return [
            {
                "tipo": documento.tipo.name,
                "rotulo": documento.rotulo,
                "arquivo": str(documento.arquivo),
                "nome": Path(documento.arquivo).name,
                "sha256": documento.sha256,
                "descricao": documento.descricao,
                "juntado_em": documento.juntado_em,
            }
            for documento in autorizacao.documentos
        ]

    @staticmethod
    def _tipo_documento(chave: str) -> TipoDocumento:
        try:
            return TipoDocumento[chave]
        except KeyError:
            return TipoDocumento.OUTRO

    def registrar_autorizacao(
        self, pasta_aquisicao: Path, documentos_novos: Optional[list] = None
    ) -> str:
        """
        Anexa os documentos escolhidos ao caso e registra, na aquisição,
        quais estavam à vista neste momento.

        Os documentos vão um nível acima porque uma autorização cobre vários
        dispositivos do mesmo exame. O que fica dentro da aquisição é a
        relação deles com os respectivos hashes — e é isso que o selo do dia
        prende no tempo.

        Roda **sempre**, mesmo sem documento nenhum: nesse caso o caso passa
        a declarar por extenso que nada foi anexado. Ausência silenciosa é
        indistinguível de esquecimento.

        Levanta `ValueError` se algum arquivo não existir ou já estiver
        anexado.
        """
        pasta_aquisicao = Path(pasta_aquisicao)
        pasta_caso = pasta_aquisicao.parent

        escolhas = [
            (
                self._tipo_documento(bruto.get("tipo", "")),
                Path(bruto["arquivo"]),
                bruto.get("descricao", ""),
            )
            for bruto in documentos_novos or []
        ]
        # Em lote de propósito: anexar três documentos numa mesma aquisição
        # tem de deixar UM registro no caso, e não três folhas seguidas.
        autorizacao = anexar_documentos(pasta_caso, escolhas)
        gravar_autorizacao_da_aquisicao(pasta_aquisicao, autorizacao)

        if self._registro is not None:
            self._registro.registrar_fundamento(autorizacao.resumo)

        return autorizacao.resumo

    def anexar_ao_caso(
        self, pasta_caso: Path, tipo: str, arquivo: Path, descricao: str = ""
    ) -> Path:
        """
        Anexa um documento a um caso que já existe, e resela o caso.

        É o caminho da decisão que só foi digitalizada dias depois, ou do
        aditamento. Nenhuma aquisição já selada é tocada: o documento entra
        no nível do caso, um complemento registra a juntada com data própria
        e o manifesto novo passa a cobrir também o que entrou.
        """
        pasta_caso = Path(pasta_caso)
        documento = anexar_documento(
            pasta_caso, self._tipo_documento(tipo), Path(arquivo), descricao
        )

        self.juntar_complemento(
            pasta_caso,
            "Juntada de documento de autorização",
            "\n".join(
                [
                    f"Documento: {documento.rotulo}",
                    f"Arquivo:   {Path(documento.arquivo).name}",
                    f"SHA-256:   {documento.sha256}",
                    "",
                    "O documento foi anexado à pasta do caso após aquisições já",
                    "seladas. As aquisições anteriores permanecem como estavam e",
                    "NÃO passam a contar com este documento: cada uma registra os",
                    "documentos que estavam à vista no momento em que foi feita.",
                ]
            ),
        )
        return documento.arquivo

    def juntar_complemento(self, pasta_caso: Path, titulo: str, texto: str) -> Path:
        """
        Junta um complemento ao caso e o resela.

        A aquisição selada não é tocada: o complemento fica no nível do
        caso, e o novo manifesto do caso passa a cobrir também o que foi
        juntado. O manifesto anterior é preservado, então o histórico de
        quando cada peça entrou permanece demonstrável.
        """
        caminho = juntar_complemento(Path(pasta_caso), titulo, texto)
        try:
            gerar_manifesto(Path(pasta_caso))
        except OSError:
            pass
        return caminho


    # ------------------------------------------------------------------
    # Leitura de casos gravados (Gerenciador de Projetos)
    # ------------------------------------------------------------------
    def resumo_do_caso(self, pasta_caso: Path) -> ResumoCaso:
        """
        Monta a ficha de um caso a partir do que está gravado em disco.

        Não inventa nada: campo ausente fica ausente. Se as aquisições
        discordarem sobre um metadado do caso, a divergência é registrada
        em `campos_divergentes` — a ficha prefere mostrar o conflito a
        escolher uma das versões.
        """
        resumo = ResumoCaso(pasta=pasta_caso, identificador=pasta_caso.name)

        for sub in sorted(pasta_caso.iterdir()):
            if not sub.is_dir() or not e_pasta_de_aquisicao(sub.name):
                continue
            plataforma, momento = descrever_aquisicao(sub.name)
            arquivo = sub / NOME_CADEIA_CUSTODIA
            arquivo = arquivo if arquivo.is_file() else None
            resumo.aquisicoes.append(
                ResumoAquisicao(
                    pasta=sub,
                    plataforma=plataforma,
                    momento=momento,
                    selada=self.aquisicao_selada(sub),
                    arquivo_custodia=arquivo,
                    dados=ler_cadeia_custodia(arquivo) if arquivo else {},
                    examinador=examinador_da_aquisicao(sub),
                )
            )

        # Mais recente primeiro: é a ordem em que o examinador procura.
        resumo.aquisicoes.sort(
            key=lambda a: (a.momento is not None, a.momento), reverse=True
        )

        if tem_registro_do_caso(pasta_caso):
            resumo.tem_registro = True
            gravados = ler_caso(pasta_caso)
            resumo.dados_do_caso = {
                rotulo: gravados.get(chave, "") for chave, rotulo in CAMPOS_DO_CASO
            }
        else:
            # Caso antigo: os dados do caso viviam dentro de cada aquisição.
            # A versão mais recente vale, e o desacordo é anotado.
            rotulos: List[str] = []
            for aquisicao in resumo.aquisicoes:
                for rotulo in aquisicao.dados:
                    if rotulo not in ROTULOS_FORA_DO_CASO and rotulo not in rotulos:
                        rotulos.append(rotulo)
            for rotulo in rotulos:
                valores = [
                    a.dados[rotulo]
                    for a in resumo.aquisicoes
                    if a.dados.get(rotulo, "") not in VALORES_VAZIOS
                ]
                if not valores:
                    continue
                resumo.dados_do_caso[rotulo] = valores[0]
                if len(set(valores)) > 1:
                    resumo.campos_divergentes.append(rotulo)

        try:
            resumo.documentos = self.documentos_do_caso(pasta_caso.name)
        except Exception:
            # Caso sem autorização registrada, ou registro ilegível. A
            # ficha mostra "nenhum documento", que é verdade, em vez de
            # a janela inteira falhar por causa de um caso.
            resumo.documentos = []

        pasta_complementos = pasta_caso / "complementos"
        if pasta_complementos.is_dir():
            resumo.complementos = len(
                [f for f in pasta_complementos.glob("*.txt") if f.name != "INDICE.txt"]
            )

        return resumo

    def listar_resumos_casos(self) -> List[ResumoCaso]:
        """
        Todos os casos da pasta de extrações, do mais recente para o mais
        antigo. É o que permite ACHAR um caso sem abrir um por um.
        """
        if not self.pasta_raiz.exists():
            return []
        resumos = [
            self.resumo_do_caso(pasta)
            for pasta in self.pasta_raiz.iterdir()
            if pasta.is_dir()
        ]
        resumos.sort(
            key=lambda r: (
                r.ultima_atividade is not None,
                r.ultima_atividade or datetime.min,
                r.identificador,
            ),
            reverse=True,
        )
        return resumos

    # ------------------------------------------------------------------
    # Registro do caso e cadeia de custódia do dispositivo
    # ------------------------------------------------------------------
    def dados_do_caso(self, identificador: str) -> Dict[str, str]:
        """Dados gravados em `caso.json`, por chave. Vazio se o caso não o tem."""
        return ler_caso(self.pasta_do_caso(identificador))

    def gravar_dados_do_caso(self, identificador: str, dados: Dict[str, str]) -> None:
        """Abre o registro do caso. Usado na criação; depois disso, `retificar_caso`."""
        gravar_caso(self.pasta_do_caso(identificador), dados)

    def retificar_caso(self, pasta_caso: Path, dados: Dict[str, str]) -> bool:
        """
        Altera os dados do caso e registra a alteração como complemento.

        As aquisições não são tocadas: cada uma guarda, sob o selo, os dados
        do caso como estavam no dia em que foi feita. O complemento diz o
        que mudou e quando. Devolve `False` se nada mudou.
        """
        pasta_caso = Path(pasta_caso)
        tinha_registro = tem_registro_do_caso(pasta_caso)
        antes = ler_caso(pasta_caso)
        depois = {chave: str(dados.get(chave, "") or "").strip() for chave, _ in CAMPOS_DO_CASO}
        if tinha_registro and antes == depois:
            return False

        gravar_caso(pasta_caso, depois)
        linhas = []
        if not tinha_registro:
            linhas += [
                "Este caso não tinha registro próprio: os dados do caso estavam",
                "apenas dentro de cada aquisição. O registro foi criado agora.",
                "",
            ]
        for chave, rotulo in CAMPOS_DO_CASO:
            anterior = antes.get(chave, "") or NAO_INFORMADO
            atual = depois[chave] or NAO_INFORMADO
            marca = "  (alterado)" if anterior != atual else ""
            linhas.append(f"{rotulo}: {anterior}  ->  {atual}{marca}")
        self.juntar_complemento(pasta_caso, "Retificação dos dados do caso", "\n".join(linhas))
        return True

    def gravar_cadeia_custodia(
        self, pasta_aquisicao: Path, identificador: str, dispositivo: dict
    ) -> Path:
        """
        Grava `cadeia_custodia.txt` e as fotos da peça dentro da aquisição,
        antes do selo. Os dados do caso são COPIADOS de `caso.json`: a
        segunda aquisição herda o que a primeira cadastrou.
        """
        pasta_aquisicao = Path(pasta_aquisicao)
        fotos_gravadas = []
        fotos = [Path(foto) for foto in dispositivo.get("fotos") or []]
        if fotos:
            pasta_fotos = pasta_aquisicao / PASTA_FOTOS
            pasta_fotos.mkdir(exist_ok=True)
            for indice, origem in enumerate(fotos, 1):
                destino = pasta_fotos / f"foto_{indice}_{origem.name}"
                shutil.copy2(origem, destino)
                fotos_gravadas.append(destino.name)

        texto = montar_cadeia_custodia(
            sanitizar_nome(identificador),
            self.dados_do_caso(identificador),
            dispositivo,
            fotos_gravadas,
        )
        caminho = pasta_aquisicao / NOME_CADEIA_CUSTODIA
        caminho.write_text(texto, encoding="utf-8")
        return caminho

    @staticmethod
    def cadeia_com_dispositivo_retificado(arquivo_custodia: Path, dispositivo: dict) -> str:
        """Texto da cadeia de custódia com os dados da peça trocados, e só eles."""
        novos = {
            rotulo: dispositivo.get(chave, "") for chave, rotulo in CAMPOS_DO_DISPOSITIVO
        }
        return substituir_campos_da_cadeia(
            Path(arquivo_custodia).read_text(encoding="utf-8"),
            novos,
            "CADEIA DE CUSTÓDIA (DISPOSITIVO RETIFICADO)",
        )

    def sugerir_identificador(self) -> str:
        """
        Sugere o proximo identificador sequencial (ex.: CASO_001, CASO_002).

        Delega a `core.case`, unica fonte da nomenclatura de casos. Manter
        uma segunda implementacao aqui ja custou uma sugestao errada: o
        padrao frouxo lia a data de uma pasta chamada `teste_dia_220826` e
        sugeria `CASO_220827`.
        """
        self.pasta_raiz.mkdir(parents=True, exist_ok=True)
        return sugerir_proximo_identificador(self.pasta_raiz)

    def sanitizar_preview(self, texto: str) -> str:
        """
        Sanitiza o texto digitado para garantir um nome de pasta válido no sistema de arquivos.
        """
        # Remove caracteres inválidos para pastas
        limpo = re.sub(r'[\\/*?:"<>|]', "", texto)
        return limpo.replace(" ", "_")

    def listar_casos_existentes(self) -> list[str]:
        """
        Lista todas as pastas de projetos/casos válidas encontradas na raiz de extrações.
        """
        if not self.pasta_raiz.exists():
            return []

        projetos = []
        for p in self.pasta_raiz.iterdir():
            if p.is_dir():
                projetos.append(p.name)

        # Ordena alfabeticamente ou por ordem decrescente de criação
        return sorted(projetos, reverse=True)

    def abrir_caso(self, nome_plataforma: str, identificador: str, id_dispositivo: str) -> Path:
        """
        Cria e devolve a pasta desta aquisição, dentro da pasta do caso.

        O caso é um projeto e pode reunir várias aquisições — inclusive de
        dispositivos diferentes. A pasta do caso é reaproveitada; a da
        aquisição, nunca: duas coletas no mesmo destino sobrescrevem
        arquivos e produzem um manifesto que cobre a mistura sem indicar
        que houve duas.
        """
        pasta_aquisicao = criar_pasta_aquisicao(
            self.pasta_raiz, identificador, nome_plataforma
        )
        registrar_info_caso(
            pasta_aquisicao, identificador, nome_plataforma, id_dispositivo
        )
        return pasta_aquisicao


# ---------------------------------------------------------------------------
# Autorização — opções para a interface montar seus campos sem conhecer
# os tipos de `core`.
# ---------------------------------------------------------------------------
def gravar_protocolos_respondidos(pasta_aquisicao, protocolos, observacoes: str = ""):
    """
    Junta ao caso as respostas do examinador aos protocolos periciais.

    Existe aqui pela mesma razão de `opcoes_tipo_documento`: a interface
    precisa persistir a declaração sem importar nada de `core`. Devolve o
    caminho do complemento gravado.
    """
    return gravar_respostas(pasta_aquisicao, protocolos, observacoes)


def opcoes_tipo_documento() -> list:
    """(chave, rótulo) de cada tipo de documento de autorização."""
    return [(tipo.name, tipo.value) for tipo in TipoDocumento]
