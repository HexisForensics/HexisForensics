"""
Identificação do iPhone: o que o iOS declara de si mesmo.

Modelo, versão do iOS, número de série, UDID, IMEI, número de telefone e
ICCID vêm do serviço de informações do aparelho (lockdown), lido depois
que o iPhone confia na estação. Nada se escreve no aparelho.

A resposta inteira é preservada em texto — toda saída é evidência — e os
campos que o laudo usa vão para `identificacao/identificacao.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.aparelho import PASTA_IDENTIFICACAO, gravar_identificacao
from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from ..client import ErroIOS
from .base import IOSExtractor

# Chave do lockdown → campo de `core.aparelho.CAMPOS`.
CAMPOS_DO_LOCKDOWN = {
    "DeviceName": "nome_do_aparelho",
    "ProductType": "modelo",
    "ModelNumber": "numero_do_modelo",
    "ProductVersion": "versao_ios",
    "BuildVersion": "build_ios",
    "SerialNumber": "numero_serie",
    "UniqueDeviceID": "udid",
    "InternationalMobileEquipmentIdentity": "imei",
    "InternationalMobileEquipmentIdentity2": "imei_2",
    "PhoneNumber": "numero_telefone",
    "IntegratedCircuitCardIdentity": "iccid",
    "WiFiAddress": "endereco_wifi",
    "TimeZone": "fuso_horario",
    "WillEncrypt": "backup_cifrado",
}


@registrar_extrator
class IdentificacaoExtractorIOS(IOSExtractor):
    id = "ios_identificacao"
    nome_exibicao = "Identificação do iPhone (modelo, iOS, série, IMEI, número)"
    ordem = 5
    descricao = (
        "Lê o que o iOS declara de si mesmo: modelo, versão, número de série, UDID, IMEI, "
        "número de telefone e ICCID. Não escreve nada no aparelho."
    )

    limitacoes_conhecidas = (
        "Os valores são os que o iOS declara de si mesmo, sem verificação contra o hardware.",
        "Número de telefone e ICCID só aparecem com chip presente, e o iOS pode omiti-los "
        "conforme a operadora e a versão.",
    )

    alteracoes_no_dispositivo = (
        (
            "O iPhone registra a estação como computador confiável (pareamento).",
            "Sem o pareamento, autorizado na tela do aparelho, o iOS não informa nada a um "
            "computador. Nenhum dado do usuário é alterado.",
        ),
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = Path(pasta_caso) / PASTA_IDENTIFICACAO
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            valores = self.client.informacoes()
        except ErroIOS as erro:
            return ResultadoExtracao(False, self._t("lg_ii_nao_identificou", erro=erro), pasta)
        if not valores:
            return ResultadoExtracao(False, self._t("lg_ii_sem_info"), pasta)

        (pasta / "informacoes_do_ios.json").write_text(
            json.dumps(valores, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        apurados = {}
        for chave, campo in CAMPOS_DO_LOCKDOWN.items():
            valor = valores.get(chave, "")
            if campo == "backup_cifrado" and valor != "":
                valor = self._t("lg_fs_sim") if valor.lower() in ("true", "1") else self._t("lg_fs_nao")
            if valor:
                apurados[campo] = valor
        apurados["fabricante"] = "Apple"
        gravar_identificacao(pasta_caso, apurados)

        faltantes = [c for c in ("modelo", "versao_ios", "numero_serie", "imei")
                     if c not in apurados]
        mensagem = self._t("lg_ii_msg_ok", modelo=apurados.get('modelo', '?'),
                           versao=apurados.get('versao_ios', '?'),
                           serie=apurados.get('numero_serie', '?'))
        detalhes = {}
        if faltantes:
            detalhes["campos_nao_apurados"] = faltantes
            mensagem += self._t("lg_ii_nao_informados", lista=", ".join(faltantes))
        self.progresso(100)
        self.log(self._t("lg_concluido", valor=mensagem))
        return ResultadoExtracao(True, mensagem, pasta, detalhes)
