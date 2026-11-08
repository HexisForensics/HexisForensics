"""
Agenda, chamadas, SMS e MMS por aplicativo agente — a via que não depende
de root nem da versão do Android.

Em aparelho de fábrica o shell do ADB não tem permissão para ler SMS e
chamadas. Até o Android 11 isso se contornava pelo backup do sistema; do
Android 12 em diante o backup deixou de existir, e sem privilégio elevado
resta uma porta: um aplicativo com as permissões de leitura concedidas.

Este módulo instala o agente da suíte (`agente_android/`, alguns
kilobytes, só permissões de LEITURA e nenhuma de rede), manda-o ler os
provedores do sistema, recolhe o que ele gravou e o DESINSTALA.

**Instalar um aplicativo é alteração no dispositivo examinado**, e por isso
o módulo é de seleção expressa e segue as mesmas regras do outro módulo que
mexe em aplicativo:

- o APK empregado entra na aquisição com o SHA-256 — é parte do método;
- a desinstalação é tentada SEMPRE, inclusive quando a coleta falha;
- o aparelho é conferido no fim, e agente que ficou instalado é FALHA em
  voz alta, mesmo com os dados em mãos.

O que o agente não leu é dito: cada fonte traz no `estado.json` quantos
registros vieram ou o erro que o sistema deu, e fonte com erro vira
ressalva — nunca "nenhum registro".
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Tuple

from core import agente_android
from core.agente_android import ARQUIVOS, NOME_ESTADO, PACOTE, PASTA
from core.base_extractor import Perfil, ResultadoExtracao
from core.hashing import EscritorComHash, calcular_sha256
from core.instalacao import raiz_da_instalacao
from core.registry import registrar_extrator

from .base import AndroidExtractor

NOME_DO_APK = "forensic_agente.apk"
ATIVIDADE = f"{PACOTE}/.Coletar"
TEMPO_DA_COLETA = 180  # segundos até o agente gravar o estado.json

# Fontes cujo conteúdo é o objetivo do módulo; as de MMS auxiliares não contam.
FONTES_PRINCIPAIS = ("contatos", "chamadas", "sms", "mms")
ROTULOS = {"contatos": "agenda", "chamadas": "chamadas", "sms": "SMS", "mms": "MMS"}


def caminho_do_apk() -> Path:
    return raiz_da_instalacao() / "assets" / "agente" / NOME_DO_APK


@registrar_extrator
class AgenteExtractor(AndroidExtractor):
    id = "android_agente"
    nome_exibicao = "Agenda, Chamadas e SMS por aplicativo agente (qualquer versão do Android)"
    ordem = 45
    selecao_expressa = True
    perfil_minimo = Perfil.DEFR
    descricao = (
        "Instala no aparelho o aplicativo agente da suíte, que lê agenda, chamadas, SMS "
        "e MMS com permissão própria, recolhe o resultado e o desinstala. É a via para "
        "Android 12 em diante, onde o backup do sistema não existe. ALTERA O DISPOSITIVO "
        "(instala e remove um aplicativo)."
    )

    limitacoes_conhecidas = (
        "Obtém o que os provedores do sistema entregam a um aplicativo com permissão de "
        "leitura. Registro apagado pelo usuário não é recuperado por esta via.",
        "O Android pode recusar a instalação por linha de comando (proteção do fabricante "
        "ou verificação de aplicativos ligada) ou pedir confirmação na tela do aparelho.",
        "Provado em aparelhos Motorola e Samsung (Android 9 a 13) e no emulador. NÃO "
        "verificado em Xiaomi/Redmi/POCO (MIUI e HyperOS), que costumam exigir a opção "
        "\"Instalar via USB\" ligada e conta Mi conectada: nesses aparelhos a instalação "
        "pode ser recusada.",
        "O conteúdo binário dos anexos de MMS não é copiado: constam o tipo e o nome de "
        "cada parte.",
    )

    alteracoes_no_dispositivo = (
        (
            "Um aplicativo (o agente de coleta da suíte) é instalado no aparelho, recebe as "
            "permissões de leitura de contatos, chamadas e SMS, é executado uma vez e é "
            "desinstalado ao final.",
            "Sem privilégio elevado, e sem o backup do sistema (removido no Android 12), é a "
            "única via de leitura de SMS e chamadas. O agente só lê, não tem permissão de "
            "rede, e o APK empregado fica na aquisição com o SHA-256.",
        ),
    )

    # ------------------------------------------------------------------
    def disponivel(self) -> Tuple[bool, str]:
        disponivel, motivo = super().disponivel()
        if not disponivel:
            return disponivel, motivo
        if not caminho_do_apk().is_file():
            return False, (
                f"O aplicativo agente não está em '{caminho_do_apk()}'. Ele é gerado por "
                "'py agente_android/compilar.py' e acompanha a suíte."
            )
        return True, ""

    def _comando(self, argumentos, arquivo_de_saida: Path, timeout: int = 120):
        """Executa e preserva o que o ADB respondeu — toda saída de comando é evidência."""
        resultado = self.adb.executar_detalhado(argumentos, timeout=timeout)
        try:
            arquivo_de_saida.write_text(
                f"comando: adb {' '.join(str(a) for a in argumentos)}\n"
                f"codigo de saida: {resultado.codigo_saida}\n"
                f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return resultado

    def _ler_do_agente(self, nome: str) -> str:
        return self.adb.executar(["exec-out", f"run-as {PACOTE} cat files/{nome}"], timeout=30)

    def _recolher(self, nome: str, destino: Path) -> Tuple[int, str]:
        """Copia um arquivo da área do agente, com hash na gravação. `(bytes, sha256)`."""
        with open(destino, "wb") as arquivo:
            escritor = EscritorComHash(arquivo)
            resultado = self.adb.stream_binario(
                ["exec-out", f"run-as {PACOTE} cat files/{nome}"], escritor.escrever
            )
        return resultado.bytes_lidos, escritor.hash_hex

    @staticmethod
    def _quantidade(nome: str, registros: int, pasta: Path) -> str:
        """
        Quanto veio de uma fonte, dito sem inflar.

        A agenda vem como uma linha por NÚMERO por CONTA: o mesmo telefone
        aparece uma vez na conta Google, outra na do WhatsApp, outra na do
        Duo. Num Samsung real, 4.668 linhas eram 2.117 contatos. Dizer
        "4.668 agenda" sugeria o dobro de pessoas.
        """
        if nome != "contatos":
            return f"{registros} {ROTULOS[nome]}"
        contatos = set()
        try:
            for linha in (pasta / "contatos.jsonl").read_text(encoding="utf-8").splitlines():
                if linha.strip():
                    identificador = json.loads(linha).get("contact_id")
                    if identificador is not None:
                        contatos.add(identificador)
        except (OSError, ValueError):
            contatos = set()
        texto = f"{registros} número(s) de agenda"
        return texto + (f" em {len(contatos)} contato(s)" if contatos else "")

    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta = pasta_caso / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        apk = caminho_do_apk()
        if not apk.is_file():
            return ResultadoExtracao(
                False, f"Não executado: o aplicativo agente não está em '{apk}'. O "
                "dispositivo NÃO foi alterado.", pasta,
            )

        sha_do_apk = calcular_sha256(apk)
        ja_estava = self.adb.pacote_instalado(PACOTE)
        (pasta / "0_agente.txt").write_text(
            "APLICATIVO AGENTE DE COLETA\n"
            f"Pacote: {PACOTE}\n"
            f"APK empregado: {apk.name}\n"
            f"SHA-256 do APK: {sha_do_apk}\n"
            f"Tamanho do APK: {apk.stat().st_size} bytes\n"
            f"Já estava instalado no aparelho antes desta execução: {'SIM' if ja_estava else 'não'}\n",
            encoding="utf-8",
        )
        self.log(f"[*] Aplicativo agente: {apk.name} — SHA-256 {sha_do_apk}")
        if ja_estava:
            self.log(
                "[!] O agente JÁ estava instalado no aparelho (resto de uma execução "
                "interrompida). Será substituído e removido ao final."
            )

        # --- 1. Instalação
        self.registrar_alteracao(
            pasta_caso,
            f"Aplicativo agente '{PACOTE}' (SHA-256 {sha_do_apk}) instalado no aparelho, com "
            "as permissões de leitura de contatos, chamadas e SMS concedidas na instalação.",
            "Única via de leitura de SMS e chamadas sem privilégio elevado quando o backup "
            "do sistema não existe ou não entrega os dados. O agente só lê e não tem "
            "permissão de rede.",
        )
        self.log("[*] Instalando o agente (mantenha a tela do aparelho DESBLOQUEADA)...")
        instalacao = self._comando(
            ["install", "-g", "-r", str(apk)], pasta / "1_instalacao_saida.txt", 180
        )
        self.progresso(20)
        if "Success" not in instalacao.stdout:
            ficou = self.adb.pacote_instalado(PACOTE)
            return ResultadoExtracao(
                False,
                "O aparelho recusou a instalação do agente ("
                + (instalacao.stdout + " " + instalacao.stderr).strip()[:300]
                + "). Nenhum dado foi obtido por esta via — o que NÃO significa ausência de "
                "dados no aparelho. Verifique se há um pedido de confirmação na tela."
                + (" ATENÇÃO: o agente consta como instalado; remova-o." if ficou else ""),
                pasta,
                {"restauracao_pendente": True} if ficou else {},
            )

        recolhidos = {}
        motivo_da_falha = ""
        try:
            # --- 2. Coleta
            self.log("[*] Executando a coleta no aparelho...")
            self._comando(["shell", "am", "start", "-W", "-n", ATIVIDADE],
                          pasta / "2_execucao_saida.txt", 60)
            limite = time.time() + TEMPO_DA_COLETA
            estado_bruto = ""
            while time.time() < limite and not self.cancelado:
                estado_bruto = self._ler_do_agente(NOME_ESTADO)
                if estado_bruto.strip().startswith("{"):
                    break
                time.sleep(2)
            self.progresso(60)

            if not estado_bruto.strip().startswith("{"):
                motivo_da_falha = (
                    "a execução foi cancelada" if self.cancelado else
                    f"o agente não concluiu a coleta em {TEMPO_DA_COLETA} segundos"
                )
            else:
                # --- 3. Recolhimento, com hash na gravação
                for nome in (NOME_ESTADO,) + ARQUIVOS:
                    tamanho, resumo = self._recolher(nome, pasta / nome)
                    recolhidos[nome] = (tamanho, resumo)
                    self.log(f"    {nome}: {tamanho} byte(s)")
        finally:
            # --- 4. Remoção: SEMPRE, aconteça o que acontecer acima.
            self.progresso(85)
            self.log("[*] Desinstalando o agente...")
            self._comando(["uninstall", PACOTE], pasta / "3_desinstalacao_saida.txt", 60)
            removido = not self.adb.pacote_instalado(PACOTE)
            self.registrar_alteracao(
                pasta_caso,
                f"Aplicativo agente '{PACOTE}' desinstalado; conferido que não consta mais "
                "entre os pacotes do aparelho." if removido else
                f"A desinstalação do agente '{PACOTE}' NÃO foi confirmada: o pacote ainda "
                "consta no aparelho.",
                "Encerramento da coleta por aplicativo agente.",
            )

        nao_removido = "" if removido else (
            f" ATENÇÃO — O AGENTE CONTINUA INSTALADO NO APARELHO ('{PACOTE}'). Remova-o "
            "manualmente (adb uninstall, ou pelas configurações do aparelho) e registre."
        )
        pendencia = {"restauracao_pendente": True} if nao_removido else {}

        if motivo_da_falha:
            return ResultadoExtracao(
                False,
                f"Nenhum dado foi obtido: {motivo_da_falha}. Isto NÃO significa ausência de "
                "dados no aparelho." + nao_removido,
                pasta, pendencia,
            )

        (pasta / "hashes_na_aquisicao.txt").write_text(
            "".join(f"{resumo} *{nome}  ({tamanho} bytes)\n"
                    for nome, (tamanho, resumo) in recolhidos.items()),
            encoding="utf-8",
        )

        estado = agente_android.ler_estado(pasta)
        if estado is None:
            return ResultadoExtracao(
                False,
                "O agente respondeu, mas o estado da coleta não pôde ser lido. Os arquivos "
                "recolhidos foram preservados; nada se afirma sobre o que contêm." + nao_removido,
                pasta, pendencia,
            )

        fontes = agente_android.situacao_das_fontes(estado)
        obtidos, recusados, vazios = [], [], []
        for nome in FONTES_PRINCIPAIS:
            fonte = fontes.get(nome, {})
            if fonte.get("erro") or fonte.get("provedor_respondeu") is False or not fonte:
                recusados.append(ROTULOS[nome])
            elif int(fonte.get("registros") or 0) > 0:
                obtidos.append(self._quantidade(nome, int(fonte["registros"]), pasta))
            else:
                vazios.append(ROTULOS[nome])
        for nome, fonte in fontes.items():
            if fonte.get("erro"):
                self.log(f"[ALERTA] O sistema recusou '{nome}' ao agente: {fonte['erro']}")

        self.progresso(100)
        partes = []
        if recusados:
            partes.append("RECUSADO pelo sistema ao agente: " + ", ".join(recusados))
        if vazios:
            partes.append("o provedor respondeu sem registro: " + ", ".join(vazios))
        complemento = (" " + "; ".join(partes) + ".") if partes else ""
        detalhes = dict(pendencia, sha256_do_agente=sha_do_apk,
                        registros={n: fontes.get(n, {}).get("registros") for n in FONTES_PRINCIPAIS})
        if recusados:
            detalhes["acesso_negado"] = True

        if not obtidos:
            return ResultadoExtracao(
                False,
                "O agente foi executado, mas nenhum registro foi obtido." + complemento
                + " Recusa não é ausência de dado no aparelho." + nao_removido,
                pasta, detalhes,
            )
        if nao_removido:
            return ResultadoExtracao(
                False, "Dados obtidos pelo agente: " + ", ".join(obtidos) + "." + complemento
                + nao_removido, pasta, detalhes,
            )
        self.log("[CONCLUÍDO] Agente: " + ", ".join(obtidos) + ".")
        return ResultadoExtracao(
            True,
            "Dados obtidos pelo aplicativo agente: " + ", ".join(obtidos) + "." + complemento
            + " O agente foi desinstalado e a remoção foi conferida.",
            pasta, detalhes,
        )
