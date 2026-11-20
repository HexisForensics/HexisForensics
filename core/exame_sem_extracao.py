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

# O tipo de bloqueio é DADO canônico (gravado no exame.json e casado por
# `startswith`): fica em PT. Para a PROSA do motivo, mapeia-se cada valor
# canônico à sua chave de exibição, resolvida no idioma do caso.
_BLOQUEIO_CHAVE = {
    "PIN numérico": "esx_bloq_pin",
    "Padrão (desenho)": "esx_bloq_padrao",
    "Senha alfanumérica": "esx_bloq_senha",
    "Biometria (digital ou rosto)": "esx_bloq_biometria",
    "Bloqueio de natureza não identificada": "esx_bloq_nao_id",
}


def ler_exame(pasta_aquisicao: Path) -> Optional[dict]:
    """O registro do exame sem extração, ou `None` se a aquisição não é um."""
    try:
        dados = json.loads((Path(pasta_aquisicao) / PASTA / NOME_EXAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def motivo_da_impossibilidade(exame: dict, idioma: str = None) -> str:
    """A frase do motivo, montada só do que foi declarado e registrado."""
    from core.idioma import traduzir
    if exame.get("liga") == "Não":
        return traduzir("esx_motivo_nao_liga", idioma)
    bloqueio = (exame.get("tipo_de_bloqueio") or "").strip()
    if bloqueio and not bloqueio.startswith("Não se aplica"):
        chave = _BLOQUEIO_CHAVE.get(bloqueio)
        exibicao = traduzir(chave, idioma) if chave else bloqueio
        texto = traduzir("esx_motivo_bloqueio", idioma, bloqueio=exibicao)
    else:
        texto = traduzir("esx_motivo_sem_acesso", idioma)
    tentativa = exame.get("tentativa") or {}
    if tentativa.get("realizada"):
        texto += traduzir("esx_motivo_tentativa", idioma, resultado=tentativa['resultado'])
    return texto


def texto_da_conclusao(exame: dict, idioma: str = None) -> str:
    from core.idioma import traduzir
    return traduzir("esx_conclusao", idioma, motivo=motivo_da_impossibilidade(exame, idioma))


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
            return linhas, self._t("esx_adb_nao_exec", stderr=resultado.stderr)
        estados = []
        for linha in resultado.stdout.splitlines()[1:]:
            partes = linha.split()
            if len(partes) >= 2:
                estados.append((partes[0], partes[1]))
        if not estados:
            return linhas, self._t("esx_adb_sem_resposta")
        rotulos = {
            "unauthorized": self._t("esx_adb_nao_autorizado"),
            "offline": self._t("esx_adb_offline"),
            "device": self._t("esx_adb_autorizado"),
        }
        return linhas, "; ".join(
            self._t("esx_adb_aparelho", serial=serial,
                    rotulo=rotulos.get(estado, self._t("esx_adb_estado", estado=estado)))
            for serial, estado in estados
        ) + "."

    def _sondar_ios(self, pasta_caso: Path) -> Tuple[list, str]:
        from core.ios.client import IOSClient

        cliente = self.client or IOSClient()
        linhas, publicos = cliente.sondar()
        if not publicos:
            marcadores = ("RECUSADA", "FALHOU", "REFUSED", "FAILED",
                          "RECHAZADA", "FALLÓ")
            recusa = next((l for l in linhas if any(m in l for m in marcadores)), "")
            if recusa:
                return linhas, self._t("esx_ios_nao_permitiu", recusa=recusa.strip())
            return linhas, self._t("esx_ios_sem_resposta")
        # O que o iPhone informa sem pareamento é dado lido do aparelho: vai
        # para a identificação, como em qualquer aquisição.
        gravar_identificacao(pasta_caso, {
            "fabricante": "Apple",
            "modelo": publicos.get("ProductType", ""),
            "versao_ios": publicos.get("ProductVersion", ""),
            "build_ios": publicos.get("BuildVersion", ""),
            "udid": publicos.get("UniqueDeviceID", ""),
        })
        confia = any("JÁ confia" in l or "ALREADY trusts" in l or "YA confía" in l
                     for l in linhas)
        detectado = self._t("esx_ios_detectado",
                            modelo=publicos.get('ProductType') or self._t("esx_ios_modelo_nao_informado"),
                            versao=publicos.get('ProductVersion', '?'))
        return linhas, detectado + (self._t("esx_ios_confia") if confia
                                    else self._t("esx_ios_nao_confia"))

    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = Path(pasta_caso) / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        momento = datetime.now().astimezone().isoformat(timespec="seconds")

        if self.dados.get("liga") == "Não":
            linhas = [self._t("esx_nao_liga_linha")]
            tentativa = {"realizada": False, "momento": momento,
                         "resultado": self._t("esx_nao_liga_resultado")}
        else:
            self.log(self._t("esx_tentando"))
            try:
                if self.plataforma is Plataforma.IOS:
                    linhas, resultado = self._sondar_ios(pasta_caso)
                else:
                    linhas, resultado = self._sondar_android()
            except Exception as erro:  # a tentativa nunca derruba o registro
                linhas = [self._t("esx_falhou_linha", tipo=type(erro).__name__, erro=erro)]
                resultado = self._t("esx_falhou_resultado", erro=erro)
            tentativa = {"realizada": True, "momento": momento, "resultado": resultado}

        (pasta / NOME_TENTATIVA).write_text(
            self._t("esx_tentativa_titulo", momento=momento) + "\n"
            + self._t("esx_tentativa_plataforma", valor=self.plataforma.value)
            + "\n\n" + "\n".join(linhas) + "\n",
            encoding="utf-8",
        )
        exame = dict(self.dados, plataforma=self.plataforma.value, registrado_em=momento,
                     tentativa=tentativa)
        (pasta / NOME_EXAME).write_text(
            json.dumps(exame, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.registrar_decisao(
            pasta_caso,
            self._t("esx_decisao"),
            motivo_da_impossibilidade(exame, self._idi_selo),
        )
        self.progresso(100)
        mensagem = self._t("esx_msg", resultado=tentativa['resultado'])
        self.log(self._t("esx_registrado", valor=mensagem))
        return ResultadoExtracao(False, mensagem, pasta, {"exame_sem_extracao": True})
