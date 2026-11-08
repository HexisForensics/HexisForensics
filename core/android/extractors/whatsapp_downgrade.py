"""
WhatsApp sem root, pela substituição temporária do aplicativo (downgrade).

O banco de mensagens em claro (`msgstore.db`) mora na área privada do
WhatsApp, e num aparelho de fábrica nada o alcança: o `adb backup` do
aplicativo atual devolve só o manifesto do pacote (medido num moto x4,
Android 9, WhatsApp 2.26: um `.ab` de 897 bytes, sem dado algum).

Versões antigas do WhatsApp entregavam a área privada inteira ao `adb
backup`. O método troca o aplicativo por uma dessas versões SEM apagar os
dados (`pm uninstall -k`), tira o backup e reinstala o aplicativo original.
A versão antiga nunca é aberta: ela só precisa estar instalada para o
sistema aceitar o backup.

**É o módulo mais invasivo da suíte, e ele diz isso antes de rodar.**
Substitui um aplicativo no dispositivo examinado, e se a reinstalação do
original falhar o aparelho fica com a versão antiga — que, aberta, pode
não reconhecer os dados e levar o usuário a apagá-los. Por isso:

- só roda por seleção expressa (o "Marcar todos" não o inclui);
- nada é tocado antes de os APKs originais estarem copiados e conferidos
  na estação — são eles que permitem desfazer;
- a reinstalação do original é tentada SEMPRE, inclusive quando o backup
  falha ou a execução é cancelada;
- a versão instalada é conferida no fim, e se não for a original o módulo
  FALHA em voz alta, mesmo tendo obtido o banco.

O APK antigo não acompanha a suíte e não é baixado por ela: o examinador o
fornece em `binario/whatsapp_legado.apk`, e o SHA-256 dele entra na
aquisição — é parte do método, e quem repetir o exame precisa do mesmo.

O alcance tem data de validade: depende do `adb backup`, que o Android
removeu a partir da versão 12, e de o sistema aceitar a instalação da
versão antiga, o que não é garantido em todo fabricante.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from core import backup_android
from core.base_extractor import Perfil, ResultadoExtracao
from core.hashing import calcular_sha256
from core.instalacao import raiz_da_instalacao
from core.registry import registrar_extrator

from .base import AndroidExtractor

PACOTE = "com.whatsapp"
NOME_APK_LEGADO = "whatsapp_legado.apk"
PASTA = "whatsapp_downgrade"
NIVEL_API_ANDROID_12 = 31
TEMPO_DO_BACKUP = 300  # segundos para o examinador confirmar na tela

# Dentro do `.ab`, cada domínio do aplicativo tem um apelido.
DOMINIOS_DO_BACKUP = {"db": "databases", "f": "files", "sp": "shared_prefs", "r": "raiz"}


def caminho_do_apk_legado() -> Path:
    return raiz_da_instalacao() / "binario" / NOME_APK_LEGADO


@registrar_extrator
class WhatsAppDowngradeExtractor(AndroidExtractor):
    id = "android_whatsapp_downgrade"
    nome_exibicao = "WhatsApp — Mensagens por substituição temporária do aplicativo (sem root)"
    ordem = 55
    selecao_expressa = True
    perfil_minimo = Perfil.DES
    descricao = (
        "Obtém o banco de mensagens em claro do WhatsApp em aparelho sem root: "
        "substitui temporariamente o aplicativo por uma versão antiga que aceita "
        "'adb backup', tira o backup e reinstala o original. ALTERA O DISPOSITIVO. "
        f"Exige o APK antigo em 'binario/{NOME_APK_LEGADO}' e Android anterior ao 12."
    )

    limitacoes_conhecidas = (
        "Depende do 'adb backup', removido do sistema a partir do Android 12, e de o "
        "aparelho aceitar a instalação da versão antiga do aplicativo — o que varia "
        "entre fabricantes e versões.",
        "Obtém o que o aplicativo mantinha no momento do backup. Mensagem apagada "
        "pelo usuário não é recuperada por esta via.",
        "O backup traz a área privada do aplicativo, não as mídias do armazenamento "
        "compartilhado, que são adquiridas pelo módulo de mídia e backups do WhatsApp.",
        "Só alcança o WhatsApp comum (com.whatsapp); o WhatsApp Business não é tratado.",
    )

    alteracoes_no_dispositivo = (
        (
            "O aplicativo WhatsApp é desinstalado com preservação dos dados, substituído "
            "por uma versão antiga e, ao final, reinstalado na versão original.",
            "É a única via de obter o banco de mensagens em claro sem privilégio elevado. "
            "Os dados do aplicativo não são apagados; os APKs originais são copiados e "
            "conferidos na estação antes de qualquer alteração, para permitir desfazê-la.",
        ),
        (
            "Interação com a tela do aparelho para autorizar o 'adb backup'.",
            "O Android exige confirmação manual na tela para concluir o backup.",
        ),
    )

    # ------------------------------------------------------------------
    def disponivel(self) -> Tuple[bool, str]:
        disponivel, motivo = super().disponivel()
        if not disponivel:
            return disponivel, motivo
        if not caminho_do_apk_legado().is_file():
            return False, (
                f"O APK antigo do WhatsApp não está em '{caminho_do_apk_legado()}'. Ele não "
                "acompanha a suíte: o examinador o fornece, e o SHA-256 dele é registrado "
                "na aquisição. Sem ele este módulo não tem como rodar."
            )
        return True, ""

    # ------------------------------------------------------------------
    def _comando(self, argumentos: List[str], arquivo_de_saida: Path, timeout: int = 180):
        """Executa e preserva o que o ADB respondeu — toda saída de comando é evidência."""
        resultado = self.adb.executar_detalhado(argumentos, timeout=timeout)
        try:
            arquivo_de_saida.write_text(
                f"comando: adb {' '.join(argumentos)}\n"
                f"codigo de saida: {resultado.codigo_saida}\n"
                f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return resultado

    def _versao_instalada(self) -> Tuple[str, str]:
        """(versionCode, versionName) do WhatsApp instalado; vazios se não instalado."""
        saida = self.adb.executar(["shell", "dumpsys", "package", PACOTE])
        codigo = re.search(r"versionCode=(\d+)", saida)
        nome = re.search(r"versionName=(\S+)", saida)
        return (codigo.group(1) if codigo else "", nome.group(1) if nome else "")

    def _caminhos_dos_apks(self) -> List[str]:
        saida = self.adb.executar(["shell", "pm", "path", PACOTE])
        return [
            linha.strip()[len("package:"):]
            for linha in saida.splitlines()
            if linha.strip().startswith("package:")
        ]

    def _copiar_originais(self, pasta: Path) -> Tuple[List[Path], str]:
        """
        Copia os APKs instalados para a estação. Devolve `(arquivos, motivo)`;
        motivo preenchido significa que NÃO é seguro prosseguir.
        """
        remotos = self._caminhos_dos_apks()
        if not remotos:
            return [], "o sistema não informou onde estão os APKs do aplicativo instalado"
        locais = []
        for remoto in remotos:
            local = pasta / Path(remoto).name
            motivo = self._copiar_arquivo_avulso(remoto, local)
            if motivo:
                return [], f"não foi possível copiar '{remoto}': {motivo}"
            if not local.is_file() or local.stat().st_size == 0:
                return [], f"a cópia de '{remoto}' veio vazia"
            # Conferência contra o aparelho: o que será reinstalado tem de
            # ser, byte a byte, o que estava instalado.
            remoto_sha = self.adb.executar(
                ["shell", f"sha256sum {self.aspas_para_shell(remoto)}"]
            ).split()
            if remoto_sha and remoto_sha[0].lower() != calcular_sha256(local).lower():
                return [], f"a cópia de '{remoto}' NÃO confere com o hash calculado no aparelho"
            locais.append(local)
        return locais, ""

    def _restaurar(self, originais: List[Path], pasta: Path) -> Tuple[bool, str]:
        """Reinstala o aplicativo original. Devolve `(restaurado, saída do ADB)`."""
        if len(originais) == 1:
            argumentos = ["install", "-r", "-d", str(originais[0])]
        else:
            argumentos = ["install-multiple", "-r", "-d"] + [str(apk) for apk in originais]
        resultado = self._comando(argumentos, pasta / "4_reinstalacao_do_original_saida.txt", 600)
        return "Success" in resultado.stdout, (resultado.stdout + " " + resultado.stderr).strip()

    @staticmethod
    def _extrair(conteudo, destino: Path) -> List[Path]:
        """
        Grava os arquivos do backup em `<destino>/com.whatsapp/<dominio>/...`.
        O `.ab` continua sendo a evidência como veio; isto é a leitura dele,
        feita antes do selo para que os leitores de conteúdo a encontrem.
        """
        gravados = []
        prefixo = f"apps/{PACOTE}/"
        for nome, dado in conteudo.membros.items():
            if not nome.startswith(prefixo) or nome.endswith("/" + backup_android.NOME_MANIFESTO):
                continue
            partes = nome[len(prefixo):].split("/")
            dominio = DOMINIOS_DO_BACKUP.get(partes[0], partes[0])
            # Nomes vêm do aparelho: nada de subir de pasta nem de caractere
            # que o Windows recusa.
            seguros = [re.sub(r'[<>:"|?*\\]', "_", p) for p in partes[1:] if p not in ("", ".", "..")]
            if not seguros:
                continue
            caminho = destino / PACOTE / dominio / Path(*seguros)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(dado)
            gravados.append(caminho)
        return gravados

    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        pasta = pasta_caso / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        apk_legado = caminho_do_apk_legado()

        if not apk_legado.is_file():
            return ResultadoExtracao(
                False,
                f"Não executado: o APK antigo não está em '{apk_legado}'. O dispositivo NÃO "
                "foi alterado.",
                pasta,
            )

        sdk = self.nivel_api()
        if sdk is not None and sdk >= NIVEL_API_ANDROID_12:
            return ResultadoExtracao(
                False,
                f"Não executado: o aparelho tem Android com API {sdk}, e o 'adb backup' foi "
                "removido do sistema a partir do Android 12 (API 31). O dispositivo NÃO foi "
                "alterado. Isto não diz nada sobre haver ou não mensagens no aparelho.",
                pasta,
            )
        if not self.adb.pacote_instalado(PACOTE):
            return ResultadoExtracao(
                False,
                f"Não executado: o pacote '{PACOTE}' não está instalado no aparelho. O "
                "dispositivo NÃO foi alterado.",
                pasta,
            )

        codigo_original, nome_original = self._versao_instalada()
        sha_legado = calcular_sha256(apk_legado)
        (pasta / "0_metodo.txt").write_text(
            "SUBSTITUIÇÃO TEMPORÁRIA DO APLICATIVO (downgrade)\n"
            f"Pacote: {PACOTE}\n"
            f"Versão instalada antes: {nome_original or 'não apurada'} "
            f"(versionCode {codigo_original or 'não apurado'})\n"
            f"APK antigo empregado: {apk_legado.name}\n"
            f"SHA-256 do APK antigo: {sha_legado}\n"
            f"Tamanho do APK antigo: {apk_legado.stat().st_size} bytes\n",
            encoding="utf-8",
        )
        self.log(f"[*] WhatsApp instalado: {nome_original} (versionCode {codigo_original}).")
        self.log(f"[*] APK antigo: {apk_legado.name} — SHA-256 {sha_legado}")

        # --- 1. Cópia dos originais: nada é tocado antes disto dar certo.
        self.log("[*] Copiando os APKs originais para a estação (é o que permite desfazer)...")
        originais, motivo = self._copiar_originais(pasta / "apk_original")
        if motivo:
            return ResultadoExtracao(
                False,
                f"Não executado: {motivo}. Sem a cópia conferida do aplicativo original não "
                "há como desfazer a substituição, e por isso o dispositivo NÃO foi alterado.",
                pasta,
            )
        self.progresso(20)
        if self.cancelado:
            return ResultadoExtracao(False, "Cancelado antes de alterar o dispositivo.", pasta)

        # --- 2. Substituição.
        self.registrar_alteracao(
            pasta_caso,
            f"WhatsApp {nome_original} desinstalado com preservação dos dados "
            f"('pm uninstall -k') e substituído pelo APK antigo (SHA-256 {sha_legado}).",
            "Única via de obter o banco de mensagens em claro sem privilégio elevado. Os "
            f"{len(originais)} APK(s) originais foram copiados e conferidos na estação antes.",
        )
        self.log("[*] Desinstalando o WhatsApp COM preservação dos dados...")
        desinstalacao = self._comando(
            ["shell", "pm", "uninstall", "-k", PACOTE], pasta / "1_desinstalacao_saida.txt"
        )
        if "Success" not in desinstalacao.stdout:
            return ResultadoExtracao(
                False,
                "O aparelho recusou a desinstalação com preservação dos dados "
                f"({desinstalacao.stdout or desinstalacao.stderr or 'sem resposta'}). O "
                "aplicativo original permanece instalado.",
                pasta,
            )

        ab = pasta / f"backup_{PACOTE}.ab"
        motivo_da_falha = ""
        try:
            self.log("[*] Instalando a versão antiga (ela NÃO deve ser aberta no aparelho)...")
            instalacao = self._comando(
                ["install", "-r", "-d", str(apk_legado)],
                pasta / "2_instalacao_do_antigo_saida.txt", 300,
            )
            self.progresso(45)
            if "Success" not in instalacao.stdout:
                motivo_da_falha = (
                    "o aparelho recusou a instalação da versão antiga ("
                    + (instalacao.stdout + " " + instalacao.stderr).strip()[:300] + ")"
                )
            elif self.cancelado:
                motivo_da_falha = "a execução foi cancelada antes do backup"
            else:
                self.log(
                    "[*] Iniciando o backup — OLHE A TELA DO APARELHO e toque em 'Fazer "
                    "backup dos meus dados', SEM digitar senha."
                )
                self.registrar_alteracao(
                    pasta_caso,
                    "Interação com a tela do aparelho para autorizar o 'adb backup' do WhatsApp.",
                    "O Android exige confirmação manual na tela para concluir o backup.",
                )
                if not self.adb.backup_pacote(PACOTE, ab, timeout=TEMPO_DO_BACKUP):
                    motivo_da_falha = (
                        "o backup não foi obtido (a confirmação na tela pode não ter sido "
                        "feita a tempo, ou o sistema não entregou arquivo algum)"
                    )
        finally:
            # --- 3. Restauração: SEMPRE, aconteça o que acontecer acima.
            self.progresso(70)
            self.log("[*] Reinstalando o WhatsApp original...")
            restaurado, saida_da_restauracao = self._restaurar(originais, pasta)
            codigo_final, nome_final = self._versao_instalada()
            restaurado = restaurado and codigo_final == codigo_original
            self.registrar_alteracao(
                pasta_caso,
                (f"WhatsApp reinstalado na versão original ({nome_final})."
                 if restaurado else
                 "A reinstalação do WhatsApp original NÃO foi confirmada: versão instalada "
                 f"agora '{nome_final or 'nenhuma'}' (versionCode {codigo_final or '—'}), "
                 f"esperada '{nome_original}' (versionCode {codigo_original})."),
                "Encerramento da substituição temporária do aplicativo.",
            )

        nao_restaurado = (
            "" if restaurado else
            " ATENÇÃO — O APARELHO NÃO VOLTOU AO ESTADO ORIGINAL: a versão instalada agora é "
            f"'{nome_final or 'nenhuma'}', e era '{nome_original}'. NÃO ABRA O WHATSAPP NO "
            f"APARELHO. Os APKs originais estão em '{PASTA}/apk_original' e devem ser "
            f"reinstalados manualmente ('adb install-multiple -r'). Resposta do ADB: "
            f"{saida_da_restauracao[:300]}"
        )

        if motivo_da_falha:
            return ResultadoExtracao(
                False,
                f"Nenhuma mensagem foi obtida: {motivo_da_falha}. Isto NÃO significa ausência "
                "de mensagens no aparelho." + nao_restaurado,
                pasta,
                {"restauracao_pendente": True} if nao_restaurado else {},
            )

        # --- 4. O backup só conta se tiver o banco dentro.
        conteudo = backup_android.abrir(ab)
        if not conteudo.legivel:
            return ResultadoExtracao(
                False,
                f"O backup foi obtido ({ab.name}), mas não pôde ser lido: {conteudo.motivo}. "
                "Está preservado como veio; nenhuma mensagem foi extraída dele." + nao_restaurado,
                pasta,
                {"restauracao_pendente": True} if nao_restaurado else {},
            )
        extraidos = self._extrair(conteudo, pasta / "extraido")
        banco = pasta / "extraido" / PACOTE / "databases" / "msgstore.db"
        self.progresso(100)
        if not banco.is_file() or banco.stat().st_size == 0:
            return ResultadoExtracao(
                False,
                f"O backup veio com {len(extraidos)} arquivo(s), mas SEM o banco de mensagens "
                "(msgstore.db): a versão antiga instalada não entregou a área privada. "
                "Nenhuma mensagem foi obtida — o que não significa ausência de mensagens no "
                "aparelho." + nao_restaurado,
                pasta,
                {"restauracao_pendente": True} if nao_restaurado else {},
            )

        if nao_restaurado:
            # O banco veio, e ainda assim é FALHA: um aparelho examinado que
            # não voltou ao estado de antes não é desfecho que se relate
            # como sucesso com ressalva.
            return ResultadoExtracao(
                False,
                f"O banco de mensagens FOI obtido ({banco.stat().st_size} bytes, em "
                f"'{PASTA}/extraido')." + nao_restaurado,
                pasta,
                {"restauracao_pendente": True, "arquivos_extraidos": len(extraidos)},
            )

        self.log(f"[CONCLUÍDO] msgstore.db obtido: {banco.stat().st_size} bytes.")
        return ResultadoExtracao(
            True,
            f"Banco de mensagens do WhatsApp obtido em claro ({banco.stat().st_size} bytes), "
            f"com {len(extraidos)} arquivo(s) da área privada do aplicativo. O aplicativo "
            f"original ({nome_original}) foi reinstalado e conferido.",
            pasta,
            {
                "arquivos_extraidos": len(extraidos),
                "bytes_do_banco": banco.stat().st_size,
                "sha256_do_apk_legado": sha_legado,
                "versao_original": nome_original,
            },
        )
