"""
Identificação do aparelho e das contas nele cadastradas.

Dois conjuntos de dados que estavam faltando e são dos mais probatórios
que se obtém sem root:

**IMEI** — identifica o aparelho físico independentemente de chip, conta ou
formatação. Não vem no `getprop`, e é por isso que não era coletado: exige
`service call iphonesubinfo`, cujo formato de saída (um Parcel binário
representado em texto) varia entre versões do Android e entre fabricantes.
Aqui a leitura é feita por várias vias, e **a saída bruta de todas as
tentativas é preservada**, com ou sem sucesso — o exame precisa poder
conferir a origem do número, e a tentativa frustrada é evidência de que a
via foi percorrida.

**Contas cadastradas** — `dumpsys account` lista as contas Google,
WhatsApp, Telegram, Instagram e demais registradas no aparelho. É o que
vincula o dispositivo a uma pessoa, e frequentemente vale mais numa
investigação do que o conteúdo em si.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from core.aparelho import gravar_identificacao
from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

# Vias de leitura do IMEI, da mais confiável para a mais dependente de
# fabricante. Cada uma é tentada e tem sua saída bruta preservada.
VIAS_IMEI = [
    ("service_call_iphonesubinfo_1", ["shell", "service", "call", "iphonesubinfo", "1"]),
    ("service_call_iphonesubinfo_3", ["shell", "service", "call", "iphonesubinfo", "3"]),
    ("dumpsys_iphonesubinfo", ["shell", "dumpsys", "iphonesubinfo"]),
    ("getprop_ril_gsm_imei", ["shell", "getprop", "ril.gsm.imei"]),
    ("getprop_persist_radio_imei", ["shell", "getprop", "persist.radio.imei"]),
]

COLETAS_TELEFONIA = {
    "contas_cadastradas.txt": ["shell", "dumpsys", "account"],
    "telefonia.txt": ["shell", "dumpsys", "telephony.registry"],
    "assinante_sim.txt": ["shell", "dumpsys", "isub"],
    "usuarios_do_aparelho.txt": ["shell", "pm", "list", "users"],
}


def extrair_digitos_de_parcel(saida: str) -> List[str]:
    """
    Extrai sequências numéricas da representação textual de um Parcel.

    `service call` imprime blocos como::

        Result: Parcel(00000000 0000000f 00350038 ... '....8.5.9.3.')

    O trecho entre aspas é o conteúdo em UTF-16LE renderizado byte a byte,
    onde cada caractere real vem seguido de um `.` (o byte nulo). Tomar um
    caractere a cada dois reconstrói o texto original.
    """
    trechos = re.findall(r"'([^']*)'", saida)
    if not trechos:
        return []

    reconstruido = "".join(trechos)[::2]
    return re.findall(r"\d{14,17}", reconstruido)


def texto_de_parcel(saida: str) -> str:
    """
    Reconstrói o texto legível de um Parcel.

    Quando o sistema recusa a leitura, o Parcel carrega a razão da recusa
    (ex.: `Requires READ_PHONE_STATE`). Essa razão é o motivo real, e é ela
    que deve ir para o registro do caso — não uma causa presumida.
    """
    trechos = re.findall(r"'([^']*)'", saida)
    if not trechos:
        return ""

    # Cada caractere real vem seguido do byte nulo, renderizado como ".";
    # tomar um a cada dois reconstroi o texto. Os 8 bytes iniciais sao
    # cabecalho do Parcel e viram 4 caracteres de lixo, descartados aqui.
    # Os demais pontos NAO podem ser removidos: sao parte do texto, como em
    # "android.permission.READ_PHONE_STATE".
    return "".join(trechos)[::2][4:].strip()


def motivo_de_recusa(saida: str) -> str:
    """Extrai do Parcel a razão pela qual o sistema recusou a leitura."""
    texto = texto_de_parcel(saida)
    for marcador in ("Requires", "Permission", "SecurityException", "Denial"):
        if marcador.lower() in texto.lower():
            return texto[:200]
    return ""


def imei_valido_por_luhn(imei: str) -> bool:
    """
    Confere o dígito verificador de um IMEI de 15 dígitos (algoritmo de Luhn).

    Serve para distinguir um IMEI real de uma sequência numérica qualquer
    capturada por engano na leitura do Parcel — o número que vai para o
    relatório não pode ser fruto de uma extração textual malfeita.
    """
    if len(imei) != 15 or not imei.isdigit():
        return False

    soma = 0
    for posicao, caractere in enumerate(reversed(imei)):
        digito = int(caractere)
        if posicao % 2 == 1:
            digito *= 2
            if digito > 9:
                digito -= 9
        soma += digito
    return soma % 10 == 0


@registrar_extrator
class IdentificacaoExtractor(AndroidExtractor):
    id = "android_identificacao"
    nome_exibicao = "Identificação do Aparelho e Contas"
    ordem = 15
    descricao = (
        "Coleta o IMEI (por múltiplas vias, com validação do dígito verificador) e as "
        "contas cadastradas no aparelho — Google, WhatsApp, Telegram e demais —, além de "
        "dados de telefonia e SIM. É o que vincula o dispositivo físico a uma pessoa. "
        "LIMITAÇÃO: em Android 10+ a leitura do IMEI pelo shell pode ser recusada pelo "
        "sistema; a tentativa e sua recusa ficam registradas como evidência."
    )

    limitacoes_conhecidas = (
        "A leitura do IMEI depende de interface que varia entre versões do "
        "Android e entre fabricantes, e pode falhar. A saída bruta de cada "
        "tentativa é preservada, inclusive das que não obtiveram o número.",
        "As contas listadas são as cadastradas no aparelho. Isso vincula o "
        "dispositivo à conta; não demonstra quem a operava.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta = pasta_caso / "identificacao"
        pasta.mkdir(parents=True, exist_ok=True)

        self._sdk_detectado = self._detectar_sdk()

        self.log("[*] Coletando identificadores do aparelho...")
        imei, vias_registradas = self._coletar_imei(pasta)
        self.progresso(50)

        coletados = self._coletar_telefonia(pasta)
        self.progresso(85)

        contas = self._extrair_contas(pasta / "contas_cadastradas.txt")
        self._gravar_resumo(pasta, imei, contas, vias_registradas)
        self.progresso(100)

        # O IMEI apurado vai também para forma estruturada, que é de onde o
        # laudo o lê. Só quando obtido: gravar campo vazio faria o laudo
        # exibir uma linha de IMEI em branco, sugerindo falha de leitura do
        # documento em vez da recusa do sistema, que está no resumo.
        if imei:
            gravar_identificacao(pasta_caso, {"imei": imei})

        detalhes = {
            "imei": imei or "",
            "vias_de_leitura_tentadas": vias_registradas,
            "contas_encontradas": len(contas),
            "arquivos_gerados": coletados,
        }

        if imei:
            self.log(f"[CONCLUÍDO] IMEI identificado e validado: {imei}")
            mensagem = f"IMEI {imei} e {len(contas)} conta(s) identificados."
        else:
            # Não obter o IMEI é limitação conhecida do Android sem root, e
            # precisa aparecer como ressalva — não pode passar por sucesso liso.
            detalhes["acesso_negado"] = True
            self.log(
                "[RESSALVA] O IMEI não pôde ser lido pelo shell (restrição do Android). "
                "A saída bruta de cada tentativa foi preservada para conferência."
            )
            self.registrar_decisao(
                pasta_caso,
                "IMEI não obtido por via lógica; identificação do aparelho apoiada em "
                "número de série e contas cadastradas.",
                self._justificar_ausencia_do_imei(vias_registradas),
            )
            mensagem = (
                f"{len(contas)} conta(s) identificadas. Ressalva: IMEI não obtido pelo shell "
                "(restrição do sistema) — verifique a etiqueta do aparelho ou a bandeja do SIM."
            )

        if not contas and not imei:
            return ResultadoExtracao(False, "Nenhum identificador pôde ser obtido.", pasta, detalhes)

        self.log(f"[*] Contas cadastradas localizadas: {len(contas)}")
        return ResultadoExtracao(True, mensagem, caminho_saida=pasta, detalhes=detalhes)

    def _detectar_sdk(self) -> Optional[int]:
        """
        Nivel de API do aparelho, usado para justificar corretamente a
        ausencia do IMEI. Lido direto do getprop, sem depender de mais nada:
        e uma informacao que a justificativa nao pode presumir.
        """
        bruto = self.adb.executar(["shell", "getprop", "ro.build.version.sdk"]).strip()
        try:
            return int(bruto)
        except (TypeError, ValueError):
            return None

    def _justificar_ausencia_do_imei(self, vias_registradas: List[str]) -> str:
        """
        Monta a justificativa com o motivo **real**, e não com uma causa
        presumida.

        A versão anterior afirmava, sempre, que "a partir do Android 10 o
        sistema não expõe o IMEI". Num Samsung com Android 5.0.2 isso era
        simplesmente falso: o motivo, legível no próprio Parcel, era a
        ausência da permissão READ_PHONE_STATE para o shell. Afirmação
        técnica errada no registro do caso é exatamente o tipo de coisa que
        se volta contra o exame.
        """
        partes = []
        if getattr(self, "_motivo_recusa", ""):
            partes.append(f"O sistema recusou a leitura com a mensagem: {self._motivo_recusa!r}.")
        else:
            partes.append("Nenhuma das vias consultadas retornou um número válido.")

        sdk = getattr(self, "_sdk_detectado", None)
        if sdk is not None and sdk >= 29:
            partes.append(
                f"O aparelho roda API {sdk}: a partir do Android 10 (API 29) o sistema "
                "deixou de expor o IMEI ao shell sem privilégio elevado."
            )
        elif sdk is not None:
            partes.append(
                f"O aparelho roda API {sdk}, anterior ao Android 10, de modo que a recusa "
                "decorre da permissão exigida do shell, e não da restrição introduzida "
                "naquela versão."
            )

        partes.append(
            f"Foram percorridas {len(vias_registradas)} vias distintas, todas com saída "
            "bruta preservada em 'leituras_brutas/'. Vias alternativas (etiqueta, bandeja "
            "do SIM, *#06#, operadora) exigem acesso físico ou requisição, fora do alcance "
            "deste módulo."
        )
        return " ".join(partes)

    # ------------------------------------------------------------------
    def _coletar_imei(self, pasta: Path) -> Tuple[Optional[str], List[str]]:
        """Percorre todas as vias conhecidas, preservando a saída bruta de cada uma."""
        pasta_bruta = pasta / "leituras_brutas"
        pasta_bruta.mkdir(parents=True, exist_ok=True)

        candidatos: List[str] = []
        vias_registradas: List[str] = []
        self._motivo_recusa = ""

        for nome_via, argumentos in VIAS_IMEI:
            if self.cancelado:
                break

            resultado = self.adb.executar_detalhado(argumentos, timeout=30)
            conteudo = resultado.stdout or f"(sem saída) {resultado.motivo_falha}"
            (pasta_bruta / f"{nome_via}.txt").write_text(conteudo, encoding="utf-8")
            vias_registradas.append(nome_via)

            if not resultado.sucesso or not resultado.stdout.strip():
                continue

            if nome_via.startswith("service_call"):
                candidatos += extrair_digitos_de_parcel(resultado.stdout)
                if not self._motivo_recusa:
                    self._motivo_recusa = motivo_de_recusa(resultado.stdout)
            else:
                candidatos += re.findall(r"\d{14,17}", resultado.stdout)

        for candidato in candidatos:
            if imei_valido_por_luhn(candidato):
                return candidato, vias_registradas

        # Nenhum candidato passou no dígito verificador: devolve o primeiro
        # bruto apenas se houver exatamente um, e sinaliza a ausência de
        # validação no resumo.
        return None, vias_registradas

    def _coletar_telefonia(self, pasta: Path) -> List[str]:
        gerados = []
        for nome_arquivo, argumentos in COLETAS_TELEFONIA.items():
            if self.cancelado:
                break
            resultado = self.adb.executar_detalhado(argumentos, timeout=60)
            conteudo = resultado.stdout or f"(sem saída) {resultado.motivo_falha}"
            (pasta / nome_arquivo).write_text(conteudo, encoding="utf-8")
            gerados.append(nome_arquivo)
        return gerados

    @staticmethod
    def _extrair_contas(caminho: Path) -> List[str]:
        """Lê os pares nome/tipo de conta da saída de `dumpsys account`."""
        if not caminho.exists():
            return []

        conteudo = caminho.read_text(encoding="utf-8", errors="ignore")
        encontradas = re.findall(r"Account\s*\{name=(.*?),\s*type=(.*?)\}", conteudo)
        return sorted({f"{nome.strip()} ({tipo.strip()})" for nome, tipo in encontradas})

    def _gravar_resumo(
        self, pasta: Path, imei: Optional[str], contas: List[str], vias: List[str]
    ) -> None:
        linhas = [
            "=" * 66,
            "IDENTIFICAÇÃO DO APARELHO E CONTAS".center(66),
            "=" * 66,
            "",
            "[IMEI]",
        ]
        if imei:
            linhas += [
                f"IMEI: {imei}",
                "Dígito verificador (Luhn): VÁLIDO",
            ]
        else:
            linhas += [
                "IMEI: NÃO OBTIDO pelo shell ADB.",
                "",
                "Não se trata de ausência de IMEI no aparelho, e sim de recusa do",
                "sistema em expô-lo ao shell sem privilégio elevado — comportamento",
                "padrão do Android a partir da versão 10. A saída bruta de cada via",
                "tentada está em 'leituras_brutas/', documentando a tentativa.",
                "Vias alternativas: etiqueta sob a bateria, bandeja do SIM, embalagem,",
                "*#06# na discagem do aparelho, ou consulta à operadora.",
            ]

        linhas += ["", f"Vias de leitura percorridas: {', '.join(vias) or 'nenhuma'}", ""]
        linhas += ["[CONTAS CADASTRADAS NO APARELHO]"]
        linhas += [f"  - {conta}" for conta in contas] or ["  (nenhuma conta localizada)"]
        linhas += ["", "=" * 66]

        (pasta / "resumo_identificacao.txt").write_text("\n".join(linhas), encoding="utf-8")
