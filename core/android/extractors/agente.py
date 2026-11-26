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
# fonte -> chave de idioma do rótulo
ROTULOS = {"contatos": "lg_ag_rot_contatos", "chamadas": "lg_ag_rot_chamadas",
           "sms": "lg_ag_rot_sms", "mms": "lg_ag_rot_mms"}


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
            return False, self._t("lg_ag_sem_apk_disp", caminho=caminho_do_apk())
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

    def _quantidade(self, nome: str, registros: int, pasta: Path) -> str:
        """
        Quanto veio de uma fonte, dito sem inflar.

        A agenda vem como uma linha por NÚMERO por CONTA: o mesmo telefone
        aparece uma vez na conta Google, outra na do WhatsApp, outra na do
        Duo. Num Samsung real, 4.668 linhas eram 2.117 contatos. Dizer
        "4.668 agenda" sugeria o dobro de pessoas.
        """
        if nome != "contatos":
            return self._t("lg_ag_qtd_simples", registros=registros, rotulo=self._t(ROTULOS[nome]))
        contatos = set()
        try:
            for linha in (pasta / "contatos.jsonl").read_text(encoding="utf-8").splitlines():
                if linha.strip():
                    identificador = json.loads(linha).get("contact_id")
                    if identificador is not None:
                        contatos.add(identificador)
        except (OSError, ValueError):
            contatos = set()
        texto = self._t("lg_ag_qtd_agenda", registros=registros)
        return texto + (self._t("lg_ag_qtd_agenda_contatos", n=len(contatos)) if contatos else "")

    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta = pasta_caso / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        apk = caminho_do_apk()
        if not apk.is_file():
            return ResultadoExtracao(
                False, self._t("lg_ag_sem_apk_exec", apk=apk), pasta,
            )

        sha_do_apk = calcular_sha256(apk)
        ja_estava = self.adb.pacote_instalado(PACOTE)
        (pasta / "0_agente.txt").write_text(
            self._t("lg_ag_cabecalho", pacote=PACOTE, apk=apk.name, sha=sha_do_apk,
                    tamanho=apk.stat().st_size,
                    ja=self._t("lg_ag_sim") if ja_estava else self._t("lg_ag_nao")),
            encoding="utf-8",
        )
        self.log(self._t("lg_ag_apk_log", apk=apk.name, sha=sha_do_apk))
        if ja_estava:
            self.log(self._t("lg_ag_ja_instalado"))

        # --- 1. Instalação
        self.registrar_alteracao(
            pasta_caso,
            self._t("lg_ag_alt_instala", pacote=PACOTE, sha=sha_do_apk),
            self._t("lg_ag_alt_instala_motivo"),
        )
        self.log(self._t("lg_ag_instalando"))
        instalacao = self._comando(
            ["install", "-g", "-r", str(apk)], pasta / "1_instalacao_saida.txt", 180
        )
        self.progresso(20)
        if "Success" not in instalacao.stdout:
            ficou = self.adb.pacote_instalado(PACOTE)
            saida = (instalacao.stdout + " " + instalacao.stderr).strip()[:300]
            mensagem = self._t("lg_ag_recusou_instalacao", saida=saida)
            if ficou:
                mensagem += self._t("lg_ag_consta_instalado")
            return ResultadoExtracao(
                False, mensagem, pasta,
                {"restauracao_pendente": True} if ficou else {},
            )

        recolhidos = {}
        motivo_da_falha = ""
        try:
            # --- 2. Coleta
            self.log(self._t("lg_ag_executando"))
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
                    self._t("lg_ag_cancelada") if self.cancelado else
                    self._t("lg_ag_nao_concluiu", n=TEMPO_DA_COLETA)
                )
            else:
                # --- 3. Recolhimento, com hash na gravação
                for nome in (NOME_ESTADO,) + ARQUIVOS:
                    tamanho, resumo = self._recolher(nome, pasta / nome)
                    recolhidos[nome] = (tamanho, resumo)
                    self.log(self._t("lg_ag_recolhido", nome=nome, tamanho=tamanho))
        finally:
            # --- 4. Remoção: SEMPRE, aconteça o que acontecer acima.
            self.progresso(85)
            self.log(self._t("lg_ag_desinstalando"))
            self._comando(["uninstall", PACOTE], pasta / "3_desinstalacao_saida.txt", 60)
            removido = not self.adb.pacote_instalado(PACOTE)
            self.registrar_alteracao(
                pasta_caso,
                self._t("lg_ag_alt_remove_ok", pacote=PACOTE) if removido else
                self._t("lg_ag_alt_remove_falhou", pacote=PACOTE),
                self._t("lg_ag_alt_remove_motivo"),
            )

        nao_removido = "" if removido else self._t("lg_ag_nao_removido", pacote=PACOTE)
        pendencia = {"restauracao_pendente": True} if nao_removido else {}

        if motivo_da_falha:
            return ResultadoExtracao(
                False,
                self._t("lg_ag_nenhum_dado", motivo=motivo_da_falha) + nao_removido,
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
                self._t("lg_ag_estado_ilegivel") + nao_removido,
                pasta, pendencia,
            )

        fontes = agente_android.situacao_das_fontes(estado)
        obtidos, recusados, vazios = [], [], []
        for nome in FONTES_PRINCIPAIS:
            fonte = fontes.get(nome, {})
            if fonte.get("erro") or fonte.get("provedor_respondeu") is False or not fonte:
                recusados.append(self._t(ROTULOS[nome]))
            elif int(fonte.get("registros") or 0) > 0:
                obtidos.append(self._quantidade(nome, int(fonte["registros"]), pasta))
            else:
                vazios.append(self._t(ROTULOS[nome]))
        for nome, fonte in fontes.items():
            if fonte.get("erro"):
                self.log(self._t("lg_ag_recusou_fonte", nome=nome, erro=fonte['erro']))

        self.progresso(100)
        partes = []
        if recusados:
            partes.append(self._t("lg_ag_recusado_parte", lista=", ".join(recusados)))
        if vazios:
            partes.append(self._t("lg_ag_vazio_parte", lista=", ".join(vazios)))
        complemento = (" " + "; ".join(partes) + ".") if partes else ""
        detalhes = dict(pendencia, sha256_do_agente=sha_do_apk,
                        registros={n: fontes.get(n, {}).get("registros") for n in FONTES_PRINCIPAIS})
        if recusados:
            detalhes["acesso_negado"] = True

        if not obtidos:
            # Nenhum registro obtido. É preciso distinguir AUSÊNCIA VERIFICADA
            # (provedor respondeu, sem erro: zero registros é achado) de RECUSA
            # (erro ou sem resposta). Tratar as duas como falha esconde o
            # achado — o mesmo defeito da Identificação corrigido para o Xiaomi,
            # exposto aqui pelo primeiro aparelho VAZIO em que o agente rodou
            # (Moto G9 Plus, Android 11): os quatro provedores responderam, sem
            # erro, com zero registros, e o módulo chamava isso de "recusa".
            if nao_removido:
                # Agente que ficou no aparelho é falha em voz alta, qualquer que
                # seja o desfecho da leitura.
                return ResultadoExtracao(
                    False,
                    self._t("lg_ag_sem_registro") + complemento
                    + self._t("lg_ag_recusa_nao_ausencia") + nao_removido,
                    pasta, detalhes,
                )
            if not recusados:
                # Todas as fontes responderam, sem erro, com zero registros:
                # ausência VERIFICADA. É achado, não falha — e não é recusa.
                # O dado obtido é o estado confirmado dos provedores.
                self.log(self._t("lg_concluido",
                                 valor=self._t("lg_ag_ausencia_log", lista=", ".join(vazios))))
                return ResultadoExtracao(
                    True,
                    self._t("lg_ag_ausencia_verificada", lista=", ".join(vazios))
                    + self._t("lg_ag_desinstalado_conferido"),
                    pasta, detalhes,
                )
            # Parte respondeu vazio e parte recusou (ou tudo recusou): a recusa
            # deixa incerteza real. Ressalva (acesso_negado) quando ao menos uma
            # fonte respondeu; falha honesta quando NADA respondeu.
            return ResultadoExtracao(
                bool(vazios),
                self._t("lg_ag_sem_registro") + complemento
                + self._t("lg_ag_recusa_nao_ausencia"),
                pasta, detalhes,
            )
        if nao_removido:
            return ResultadoExtracao(
                False,
                self._t("lg_ag_obtido_parcial", lista=", ".join(obtidos)) + complemento
                + nao_removido, pasta, detalhes,
            )
        self.log(self._t("lg_concluido",
                         valor=self._t("lg_ag_concluido_log", lista=", ".join(obtidos))))
        return ResultadoExtracao(
            True,
            self._t("lg_ag_obtido_ok", lista=", ".join(obtidos)) + complemento
            + self._t("lg_ag_desinstalado_conferido"),
            pasta, detalhes,
        )
