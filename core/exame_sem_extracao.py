"""
Exame sem extração: o registro de um aparelho que não pôde ser extraído.

Aparelho bloqueado por credencial, que não liga, quebrado: ainda assim há
um exame a documentar — a peça, o lacre, as fotografias, o estado em que
estava e o que se tentou. O resultado é um laudo negativo honesto, que diz
que não foi possível extrair e por quê, e que NÃO diz que o aparelho não
tem dados.

O que o examinador declara (estado, tipo de bloqueio, tentativas) vai como
declaração dele. O que a ferramenta pode verificar, ela verifica: se o
aparelho liga, tenta a conexão e guarda a resposta crua — o ADB dizendo
"unauthorized", o iPhone recusando a sessão. É isso que separa "o examinador
informou que estava bloqueado" de "a conexão foi tentada e recusada, conforme
o registro anexo".

A tentativa NÃO altera o aparelho: no Android é a listagem de dispositivos
do ADB; no iPhone, uma sessão sem pedido de pareamento — o "Confiar neste
computador?" não é disparado.

O registro é feito como um módulo comum (não aparece na lista de módulos),
para correr pelo mesmo caminho de toda aquisição: registro do procedimento,
cadeia de custódia, manifesto e selo. Ele NUNCA é sucesso: nenhum dado do
conteúdo do aparelho é obtido, e o desfecho diz isso.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from core.aparelho import gravar_identificacao
from core.base_extractor import BaseExtractor, Plataforma, ResultadoExtracao

PASTA = "exame_sem_extracao"
NOME_EXAME = "exame.json"
NOME_TENTATIVA = "tentativa_de_conexao.txt"

TIPOS_DE_BLOQUEIO = (
    "PIN numérico",
    "Padrão (desenho)",
    "Senha alfanumérica",
    "Biometria (digital ou rosto)",
    "Bloqueio de natureza não identificada",
    "Não se aplica (o aparelho não liga)",
)
RESPOSTAS = ("Sim", "Não", "Não verificado")
RECOMENDACAO_PADRAO = "Reexame mediante fornecimento da credencial de desbloqueio."

CONCLUSAO = (
    "Não foi possível extrair dados do dispositivo examinado. {motivo} Nenhum dado do "
    "conteúdo do aparelho foi obtido, e isso NÃO permite concluir nada sobre o que ele "
    "contém: a ausência de extração não é ausência de dados. O lacre da peça consta da "
    "seção 3."
)


def ler_exame(pasta_aquisicao: Path) -> Optional[dict]:
    """O registro do exame sem extração, ou `None` se a aquisição não é um."""
    try:
        dados = json.loads((Path(pasta_aquisicao) / PASTA / NOME_EXAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def motivo_da_impossibilidade(exame: dict) -> str:
    """A frase do motivo, montada só do que foi declarado e registrado."""
    if exame.get("liga") == "Não":
        return "O aparelho não ligou, conforme declarado pelo examinador."
    bloqueio = (exame.get("tipo_de_bloqueio") or "").strip()
    texto = (
        f"O aparelho estava protegido por bloqueio de tela do tipo {bloqueio}, conforme "
        "declarado pelo examinador, e a credencial não estava disponível."
        if bloqueio and not bloqueio.startswith("Não se aplica") else
        "O examinador declarou que o acesso ao aparelho não foi possível."
    )
    tentativa = exame.get("tentativa") or {}
    if tentativa.get("realizada"):
        texto += f" A tentativa de conexão registrada pela ferramenta resultou: {tentativa['resultado']}"
    return texto


def texto_da_conclusao(exame: dict) -> str:
    return CONCLUSAO.format(motivo=motivo_da_impossibilidade(exame))


class ExameSemExtracao(BaseExtractor):
    """Não é registrado: entra só pelo botão 'Exame sem extração'."""

    id = "exame_sem_extracao"
    nome_exibicao = "Exame sem extração (registro da impossibilidade)"
    descricao = (
        "Registra a peça, o estado em que estava e a tentativa de conexão de um aparelho "
        "que não pôde ser extraído. Nenhum dado do conteúdo é obtido."
    )
    limitacoes_conhecidas = (
        "Nenhum dado do conteúdo do aparelho é obtido: o registro documenta a peça, o estado "
        "declarado pelo examinador e a resposta do aparelho à tentativa de conexão.",
    )

    def __init__(self, plataforma: Plataforma, dados: dict, client=None, **kwargs):
        super().__init__(**kwargs)
        self.plataforma = plataforma
        self.dados = dict(dados or {})
        self.client = client

    def disponivel(self) -> Tuple[bool, str]:
        return True, ""

    # ------------------------------------------------------------------
    def _sondar_android(self) -> Tuple[list, str]:
        from core.android.adb_client import ADBClient

        cliente = self.client or ADBClient()
        resultado = cliente.executar_detalhado(["devices", "-l"], timeout=30, vincular_serial=False)
        linhas = [
            "comando: adb devices -l",
            f"codigo de saida: {resultado.codigo_saida}",
            "--- stdout ---", resultado.stdout, "--- stderr ---", resultado.stderr,
        ]
        if resultado.codigo_saida != 0 and not resultado.stdout:
            return linhas, f"o ADB não pôde ser executado nesta estação ({resultado.stderr})."
        estados = []
        for linha in resultado.stdout.splitlines()[1:]:
            partes = linha.split()
            if len(partes) >= 2:
                estados.append((partes[0], partes[1]))
        if not estados:
            return linhas, "nenhum aparelho respondeu ao ADB."
        rotulos = {
            "unauthorized": "respondeu como NÃO AUTORIZADO — a conexão de depuração não foi "
                            "aceita no aparelho",
            "offline": "respondeu como OFFLINE",
            "device": "respondeu como AUTORIZADO; nenhuma extração foi feita neste registro",
        }
        return linhas, "; ".join(
            f"o aparelho '{serial}' {rotulos.get(estado, f'respondeu no estado {estado}')}"
            for serial, estado in estados
        ) + "."

    def _sondar_ios(self, pasta_caso: Path) -> Tuple[list, str]:
        from core.ios.client import IOSClient

        cliente = self.client or IOSClient()
        linhas, publicos = cliente.sondar()
        if not publicos:
            recusa = next((l for l in linhas if "RECUSADA" in l or "FALHOU" in l), "")
            if recusa:
                return linhas, f"o iPhone não permitiu a comunicação ({recusa.strip()})."
            return linhas, "nenhum iPhone respondeu pela conexão USB."
        # O que o iPhone informa sem pareamento é dado lido do aparelho: vai
        # para a identificação, como em qualquer aquisição.
        gravar_identificacao(pasta_caso, {
            "fabricante": "Apple",
            "modelo": publicos.get("ProductType", ""),
            "versao_ios": publicos.get("ProductVersion", ""),
            "build_ios": publicos.get("BuildVersion", ""),
            "udid": publicos.get("UniqueDeviceID", ""),
        })
        confia = any("JÁ confia" in l for l in linhas)
        return linhas, (
            f"o iPhone foi detectado ({publicos.get('ProductType', 'modelo não informado')}, "
            f"iOS {publicos.get('ProductVersion', '?')}) e "
            + ("confia nesta estação; nenhuma extração foi feita neste registro."
               if confia else "NÃO confia nesta estação: sem o desbloqueio e a autorização na "
                              "tela, o iOS não entrega dado algum.")
        )

    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta = Path(pasta_caso) / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        momento = datetime.now().astimezone().isoformat(timespec="seconds")

        if self.dados.get("liga") == "Não":
            linhas = ["Tentativa de conexão NÃO realizada: o examinador declarou que o aparelho "
                      "não liga."]
            tentativa = {"realizada": False, "momento": momento,
                         "resultado": "não realizada — o aparelho não liga."}
        else:
            self.log("[*] Tentando a conexão com o aparelho, sem alterá-lo...")
            try:
                if self.plataforma is Plataforma.IOS:
                    linhas, resultado = self._sondar_ios(pasta_caso)
                else:
                    linhas, resultado = self._sondar_android()
            except Exception as erro:  # a tentativa nunca derruba o registro
                linhas = [f"A tentativa falhou na estação: {type(erro).__name__}: {erro}"]
                resultado = f"a tentativa falhou na estação ({erro})."
            tentativa = {"realizada": True, "momento": momento, "resultado": resultado}

        (pasta / NOME_TENTATIVA).write_text(
            f"TENTATIVA DE CONEXÃO — {momento}\n"
            f"Plataforma: {self.plataforma.value}\n\n" + "\n".join(linhas) + "\n",
            encoding="utf-8",
        )
        exame = dict(self.dados, plataforma=self.plataforma.value, registrado_em=momento,
                     tentativa=tentativa)
        (pasta / NOME_EXAME).write_text(
            json.dumps(exame, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.registrar_decisao(
            pasta_caso,
            "Exame registrado SEM extração.",
            motivo_da_impossibilidade(exame),
        )
        self.progresso(100)
        mensagem = (
            "Exame sem extração registrado. Nenhum dado do conteúdo do aparelho foi obtido. "
            f"Tentativa de conexão: {tentativa['resultado']}"
        )
        self.log(f"[REGISTRADO] {mensagem}")
        return ResultadoExtracao(False, mensagem, pasta, {"exame_sem_extracao": True})
