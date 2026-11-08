"""
Migrado de `4_caracteristicas_tecnicas.py`: relatório técnico do dispositivo.

O módulo lia nove propriedades, uma a uma, e devolvia `sucesso=True` sem
olhar para nenhuma delas. Aparelho desconectado no meio do exame, ou
autorização revogada na tela, rendia "Relatório técnico gerado." sobre um
arquivo de campos em branco — a ferramenta afirmando que caracterizou um
aparelho do qual não leu nada.

Hoje a leitura é **uma só**: o `getprop` inteiro, preservado bruto como
evidência (stdout e stderr), e os campos do relatório saem dele. Três
desfechos, e só três:

- nada do núcleo que identifica o aparelho foi lido → FALHA;
- o núcleo veio, mas algum campo esperado não → sucesso com ressalva
  (`campos_nao_apurados`), nomeando o que faltou;
- tudo veio → sucesso.

Campo que o aparelho não declara não vira linha em branco: é dito que não
foi apurado. Linha em branco sugere que o valor é vazio; "não apurado" diz
que a ferramenta não sabe.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.aparelho import gravar_tecnicos
from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator

from .base import AndroidExtractor

# campo -> (rótulo no relatório, propriedades candidatas em ordem de preferência)
#
# NUCLEO é o que identifica o aparelho e o sistema; sem nenhum deles não há
# caracterização. COMPLEMENTARES dependem de versão e de fabricante — a
# ausência deles é esperada em parte dos aparelhos e não gera ressalva, mas
# é dita no relatório.
NUCLEO = {
    "fabricante": ("Fabricante", ("ro.product.manufacturer",)),
    "modelo": ("Modelo", ("ro.product.model",)),
    "marca": ("Marca/Nome Comercial", ("ro.product.brand",)),
    "numero_serie": ("Número de Série (OS)", ("ro.serialno", "ro.boot.serialno")),
    "arquitetura_cpu": ("Arquitetura do CPU", ("ro.product.cpu.abi",)),
    "versao_android": ("Versão do Android", ("ro.build.version.release",)),
    "versao_sdk": ("Versão da API (SDK)", ("ro.build.version.sdk",)),
}

COMPLEMENTARES = {
    "patch_seguranca": ("Patch de Segurança", ("ro.build.version.security_patch",)),
    "impressao_digital_build": ("Impressão digital do build", ("ro.build.fingerprint",)),
    "tipo_build": ("Tipo do build", ("ro.build.type",)),
    "estado_criptografia": ("Estado da criptografia", ("ro.crypto.state",)),
    "tipo_criptografia": ("Tipo de criptografia", ("ro.crypto.type",)),
    "boot_verificado": ("Estado do boot verificado", ("ro.boot.verifiedbootstate",)),
    "bootloader_travado": ("Bootloader travado (1=sim)", ("ro.boot.flash.locked",)),
    "versao_bootloader": ("Versão do bootloader", ("ro.bootloader",)),
    "banda_base": ("Banda base (rádio)", ("gsm.version.baseband",)),
    "operadora_sim": ("Operadora do SIM", ("gsm.sim.operator.alpha",)),
    "fuso_horario": ("Fuso horário configurado", ("persist.sys.timezone",)),
}

_LINHA_GETPROP = re.compile(r"^\[([^\]]+)\]: \[(.*)\]$")

# Comandos cujo texto vai inteiro para o relatório, sem interpretação: o
# formato muda entre versões e fabricantes, e extrair número dali seria
# apresentar palpite como medida.
COMANDOS_BRUTOS = (
    ("kernel.txt", ["shell", "uname", "-a"], "KERNEL"),
    ("armazenamento.txt", ["shell", "df"], "ARMAZENAMENTO (df)"),
    ("bateria.txt", ["shell", "dumpsys", "battery"], "BATERIA"),
)


def interpretar_getprop(texto: str) -> dict:
    """Converte a saída do `getprop` (`[chave]: [valor]`) em dicionário."""
    propriedades = {}
    for linha in (texto or "").splitlines():
        casou = _LINHA_GETPROP.match(linha.strip())
        if casou:
            propriedades[casou.group(1)] = casou.group(2).strip()
    return propriedades


def _apurar(propriedades: dict, tabela: dict) -> dict:
    apurado = {}
    for campo, (_rotulo, candidatas) in tabela.items():
        for nome in candidatas:
            valor = propriedades.get(nome, "")
            if valor:
                apurado[campo] = valor
                break
    return apurado


@registrar_extrator
class DeviceInfoExtractor(AndroidExtractor):
    id = "android_device_info"
    nome_exibicao = "Características Técnicas do Dispositivo"
    descricao = (
        "Lê as propriedades do sistema (getprop) e gera um relatório com fabricante, "
        "modelo, série, versão do sistema, patch de segurança, estado da criptografia, "
        "do bootloader e do boot verificado, além de kernel, armazenamento e bateria. "
        "A saída bruta dos comandos é preservada ao lado do relatório."
    )
    ordem = 10

    limitacoes_conhecidas = (
        "As características são as que o próprio sistema do aparelho declara. "
        "Em dispositivo com sistema modificado, esses valores podem não "
        "corresponder ao hardware real.",
        "Estado de criptografia, do bootloader e do boot verificado dependem de "
        "propriedades que nem toda versão ou fabricante expõe. Campo não "
        "declarado pelo aparelho é reportado como NÃO APURADO, nunca presumido.",
    )

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta_info = pasta_caso / "device_specs"
        pasta_info.mkdir(parents=True, exist_ok=True)
        caminho_arquivo = pasta_info / "caracteristicas_tecnicas.txt"

        self.log("[*] Lendo as propriedades do sistema (getprop)...")
        self.progresso(10)
        leitura = self.adb.executar_detalhado(["shell", "getprop"], timeout=60)
        (pasta_info / "getprop_bruto.txt").write_text(leitura.stdout or "", encoding="utf-8")
        if leitura.stderr:
            (pasta_info / "getprop_bruto_stderr.txt").write_text(
                leitura.stderr, encoding="utf-8"
            )
        self.progresso(50)

        propriedades = interpretar_getprop(leitura.stdout)
        nucleo = _apurar(propriedades, NUCLEO)
        complementares = _apurar(propriedades, COMPLEMENTARES)

        if not nucleo:
            motivo = leitura.motivo_falha or (
                "o comando respondeu sem nenhuma propriedade de identificação"
            )
            mensagem = (
                "Características técnicas NÃO obtidas — nenhuma propriedade de "
                f"identificação foi lida do aparelho ({motivo}). A tentativa foi "
                "preservada em getprop_bruto.txt."
            )
            self.log(f"[FALHA] {mensagem}")
            return ResultadoExtracao(False, mensagem, caminho_saida=pasta_info)

        blocos_brutos = self._coletar_brutos(pasta_info)
        id_conexao = getattr(self.adb, "serial", None) or self.device.obter_id_dispositivo()
        self.progresso(80)

        nucleo_faltante = [NUCLEO[c][0] for c in NUCLEO if c not in nucleo]
        complementar_faltante = [
            COMPLEMENTARES[c][0] for c in COMPLEMENTARES if c not in complementares
        ]

        linhas = [
            "=" * 58,
            "RELATÓRIO DE CARACTERÍSTICAS TÉCNICAS".center(58),
            "=" * 58,
            "Data/Hora da Coleta (estação, com fuso): "
            f"{datetime.now().astimezone().isoformat(timespec='seconds')}",
            f"ID de Conexão ADB: {id_conexao}",
            "-" * 58,
        ]
        for tabela, apurado in ((NUCLEO, nucleo), (COMPLEMENTARES, complementares)):
            for campo, (rotulo, _candidatas) in tabela.items():
                linhas.append(f"{rotulo + ':':<32}{apurado.get(campo, 'NÃO APURADO')}")
            linhas.append("-" * 58)
        for titulo, texto in blocos_brutos:
            linhas += ["", f"[{titulo}]", texto or "NÃO APURADO (o comando não devolveu saída)"]
        linhas.append("=" * 58)
        caminho_arquivo.write_text("\n".join(linhas), encoding="utf-8")

        # O mesmo conteúdo em forma estruturada, ao lado da prosa: o laudo
        # precisa dos valores, e interpretar texto formatado para obtê-los
        # seria frágil — frágil aqui significa laudo descrevendo o aparelho
        # errado.
        gravar_tecnicos(pasta_caso, dict(nucleo, **complementares, id_conexao=id_conexao))
        self.progresso(100)

        detalhes = {"campos_apurados": len(nucleo) + len(complementares)}
        mensagem = (
            f"Relatório técnico gerado: {len(nucleo) + len(complementares)} "
            "característica(s) lida(s) do aparelho."
        )
        if nucleo_faltante:
            detalhes["campos_nao_apurados"] = nucleo_faltante
            mensagem += (
                " Ressalva: o aparelho não declarou "
                + ", ".join(nucleo_faltante)
                + "."
            )
        if complementar_faltante:
            detalhes["complementares_nao_declarados"] = complementar_faltante
            self.log(
                "[AVISO] Não declarado por este aparelho: "
                + ", ".join(complementar_faltante)
                + "."
            )

        self.log(f"[CONCLUÍDO] {mensagem}")
        return ResultadoExtracao(
            True, mensagem, caminho_saida=caminho_arquivo, detalhes=detalhes
        )

    def _coletar_brutos(self, pasta_info: Path) -> list:
        """Executa os comandos de texto livre, preservando stdout e stderr."""
        blocos = []
        for nome_arquivo, comando, titulo in COMANDOS_BRUTOS:
            resultado = self.adb.executar_detalhado(comando, timeout=60)
            texto = resultado.stdout or ""
            (pasta_info / nome_arquivo).write_text(texto, encoding="utf-8")
            if resultado.stderr:
                (pasta_info / nome_arquivo).with_name(
                    Path(nome_arquivo).stem + "_stderr.txt"
                ).write_text(resultado.stderr, encoding="utf-8")
            blocos.append((titulo, texto))
        return blocos
