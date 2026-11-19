"""
Decifragem do backup do WhatsApp de uma aquisição, com a chave de 64 dígitos.

O arquivo cifrado (`msgstore.db.crypt15`) está na aquisição, sob o selo, e
não é tocado. O banco em claro é material DERIVADO: vai para
`<caso>/decifrados/<aquisição>/`, com um arquivo de procedência ao lado que
o liga ao cifrado de onde saiu — o hash do cifrado, o hash selado no
manifesto e o hash do próprio decifrado. É por essa procedência que os
leitores de conteúdo, os documentos e o índice o encontram.

A decifragem é registrada como complemento ao caso, **com a chave**. Ela
não é segredo a proteger do processo: é o que permite a outro examinador
repetir a conta e chegar ao mesmo banco. Sem a chave no registro, o
resultado seria afirmação sem meio de conferência.

O complemento registra também o que o procedimento ALTEROU no dispositivo:
para existir um backup com chave conhecida, alguém ativou essa opção no
aplicativo e mandou fazer o backup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from core.case import idioma_do_caso, juntar_complemento, pasta_do_caso, pasta_dos_decifrados
from core.hashing import calcular_sha256, gerar_manifesto, ler_manifesto, localizar_manifesto
from core.idioma import traduzir
from core.versao import identificacao_ferramenta
from core.whatsapp_crypt15 import ErroDeDecifragem, decifrar, normalizar_chave
from services.relatorio_service import SUFIXO_PROCEDENCIA

PACOTE_PADRAO = "com.whatsapp"


def _confere(procedencia: dict, idioma=None) -> str:
    """Se o hash do cifrado confere com o manifesto, no idioma do caso."""
    if procedencia["sha256_da_origem"] == procedencia["sha256_da_origem_no_manifesto"]:
        return traduzir("dec_confere", idioma)
    if procedencia["sha256_da_origem_no_manifesto"]:
        return traduzir("dec_nao_confere", idioma)
    return traduzir("dec_sem_hash", idioma)


@dataclass
class ResultadoDecifragem:
    erro: str = ""
    decifrados: List[str] = field(default_factory=list)
    falhas: List[str] = field(default_factory=list)
    pasta: Path = None
    banco_principal: bool = False
    idioma: str = None

    @property
    def resumo(self) -> str:
        if self.erro:
            return self.erro
        linhas = [traduzir("dec_resumo_ok", self.idioma, n=len(self.decifrados))]
        linhas += [f"  ✔ {nome}" for nome in self.decifrados]
        if self.falhas:
            linhas.append(traduzir("dec_resumo_falhas", self.idioma, n=len(self.falhas)))
            linhas += [f"  ✖ {texto}" for texto in self.falhas]
        if self.decifrados and not self.banco_principal:
            linhas.append(traduzir("dec_resumo_sem_principal", self.idioma))
        return "\n".join(linhas)


def backups_crypt15(pasta_aquisicao: Path) -> List[Path]:
    """
    Os backups que a suíte sabe LER depois de decifrados: o banco de
    mensagens (`msgstore*.db`) e o de contatos (`wa.db`), que dá nome aos
    números. O WhatsApp grava outros `.crypt15` (figurinhas, configurações,
    status); decifrá-los só encheria a lista de "não é um banco".

    O mesmo arquivo pode ter sido adquirido por dois módulos (o de WhatsApp
    e o dump do sistema de arquivos). Cópias idênticas contam uma vez.
    """
    encontrados, vistos = [], set()
    for caminho in sorted(Path(pasta_aquisicao).rglob("*.crypt15")):
        nome = caminho.name.lower()
        if not (nome.startswith("msgstore") or nome == "wa.db.crypt15"):
            continue
        identidade = (caminho.name, calcular_sha256(caminho))
        if identidade in vistos:
            continue
        vistos.add(identidade)
        encontrados.append(caminho)
    return encontrados


def _pacote_de(relativo: str) -> str:
    return "com.whatsapp.w4b" if "business" in relativo.lower() or "w4b" in relativo.lower() \
        else PACOTE_PADRAO


def decifrar_whatsapp(pasta_aquisicao: Path, chave_digitada: str) -> ResultadoDecifragem:
    """
    Decifra todos os `.crypt15` da aquisição com a chave dada.

    Nada é escrito dentro da aquisição. Arquivo que não abrir com a chave é
    listado com o motivo — um backup antigo, feito antes de a chave ser
    ativada, é o caso esperado.
    """
    pasta_aquisicao = Path(pasta_aquisicao)
    idi = idioma_do_caso(pasta_aquisicao)
    resultado = ResultadoDecifragem(idioma=idi)

    try:
        chave = normalizar_chave(chave_digitada)
    except ErroDeDecifragem as erro:
        resultado.erro = str(erro)
        return resultado

    backups = backups_crypt15(pasta_aquisicao)
    if not backups:
        resultado.erro = traduzir("dec_wa_sem_backup", idi)
        return resultado

    manifesto = localizar_manifesto(pasta_aquisicao)
    try:
        selados = ler_manifesto(manifesto) if manifesto else {}
    except (OSError, ValueError):
        selados = {}

    destino = pasta_dos_decifrados(pasta_aquisicao)
    resultado.pasta = destino
    registros = []

    for backup in backups:
        relativo = backup.relative_to(pasta_aquisicao).as_posix()
        try:
            banco = decifrar(backup, chave)
        except ErroDeDecifragem as erro:
            resultado.falhas.append(f"{relativo}: {erro}")
            continue

        nome = backup.name[: -len(".crypt15")]  # msgstore.db, msgstore-2026-10-11.1.db ...
        saida = destino / _pacote_de(relativo) / "databases" / nome
        try:
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.write_bytes(banco)
            procedencia = {
                "origem": relativo,
                "sha256_da_origem": calcular_sha256(backup),
                "sha256_da_origem_no_manifesto": selados.get(relativo, ""),
                "sha256_do_decifrado": calcular_sha256(saida),
                "bytes_do_decifrado": len(banco),
                "decifrado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
                "ferramenta": identificacao_ferramenta(),
                "metodo": traduzir("dec_wa_metodo", idi),
            }
            Path(str(saida) + SUFIXO_PROCEDENCIA).write_text(
                json.dumps(procedencia, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as erro:
            resultado.falhas.append(traduzir("dec_wa_nao_gravado", idi, relativo=relativo, erro=erro))
            continue

        resultado.decifrados.append(relativo)
        resultado.banco_principal = resultado.banco_principal or nome == "msgstore.db"
        registros.append((relativo, procedencia))

    if not resultado.decifrados:
        resultado.erro = traduzir("dec_wa_nenhum", idi) + "\n" + "\n".join(resultado.falhas)
        return resultado

    linhas = [
        traduzir("dec_aquisicao", idi, aquisicao=pasta_aquisicao.name),
        traduzir("dec_wa_chave", idi, valor=chave.hex()),
        traduzir("dec_wa_metodo_linha", idi),
        traduzir("dec_wa_authtag", idi),
        "",
        traduzir("dec_wa_repetir", idi),
        "",
        traduzir("dec_wa_alteracao", idi),
        "",
        traduzir("dec_wa_arquivos", idi),
    ]
    for relativo, procedencia in registros:
        confere = _confere(procedencia, idi)
        linhas += [
            f"  {relativo}",
            f"    {traduzir('dec_sha_cifrado', idi)}   {procedencia['sha256_da_origem']} ({confere})",
            f"    {traduzir('dec_sha_decifrado', idi)} {procedencia['sha256_do_decifrado']} "
            f"({procedencia['bytes_do_decifrado']} bytes)",
        ]
    if resultado.falhas:
        linhas += ["", traduzir("dec_wa_nao_abriram", idi)]
        linhas += [f"  {texto}" for texto in resultado.falhas]

    try:
        caso = pasta_do_caso(pasta_aquisicao)
        if caso != pasta_aquisicao.resolve():
            juntar_complemento(
                caso, traduzir("dec_wa_complemento", idi, aquisicao=pasta_aquisicao.name),
                "\n".join(linhas)
            )
            gerar_manifesto(caso)
    except OSError as erro:
        resultado.falhas.append(traduzir("dec_nao_registrado", idi, erro=erro))
    return resultado


# ---------------------------------------------------------------------------
# Backup cifrado do iPhone
# ---------------------------------------------------------------------------
def senha_gerada_na_aquisicao(pasta_aquisicao: Path) -> str:
    """
    A senha temporária que o módulo de backup cifrado gerou nesta aquisição.

    Só é devolvida se o arquivo que a guarda confere com o selo: senha lida
    de arquivo alterado depois da aquisição não é "a gerada nesta
    aquisição". Sem arquivo, sem selo ou sem conferir: `""` — e o examinador
    informa a senha (a do dono, quando era ele quem tinha senha de backup).
    """
    from core import backup_ios
    from core.ios.extractors.backup_cifrado import NOME_SENHA

    pasta_aquisicao = Path(pasta_aquisicao)
    # Aquisições anteriores a 31/10/2026 guardavam a senha em `backup_ios/`.
    arquivo = next((pasta_aquisicao / nome / NOME_SENHA for nome in
                    (backup_ios.PASTA_CIFRADO, backup_ios.PASTA)
                    if (pasta_aquisicao / nome / NOME_SENHA).is_file()),
                   pasta_aquisicao / backup_ios.PASTA_CIFRADO / NOME_SENHA)
    manifesto = localizar_manifesto(pasta_aquisicao)
    if not arquivo.is_file() or manifesto is None:
        return ""
    relativo = arquivo.relative_to(pasta_aquisicao).as_posix()
    selado = ler_manifesto(manifesto).get(relativo, "")
    if not selado or selado.lower() != calcular_sha256(arquivo).lower():
        return ""
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.startswith("Senha:"):
            return linha.split(":", 1)[1].strip()
    return ""


def decifrar_backup_ios(pasta_aquisicao: Path, senha: str) -> ResultadoDecifragem:
    """
    Decifra, do backup cifrado do iPhone, os bancos que a suíte sabe ler.

    Mesmas regras do WhatsApp: o backup cifrado fica na aquisição, sob o
    selo, intocado; o que sai em claro vai para `decifrados/`, cada banco
    com a procedência ao lado; e a decifragem vira complemento do caso COM
    a senha, para que outro examinador a repita e chegue ao mesmo resultado.
    """
    from core import backup_ios

    pasta_aquisicao = Path(pasta_aquisicao)
    idi = idioma_do_caso(pasta_aquisicao)
    resultado = ResultadoDecifragem(idioma=idi)
    if not senha:
        resultado.erro = traduzir("dec_ios_sem_senha", idi)
        return resultado

    cifrados = []
    for backup in backup_ios.backups_da_aquisicao(pasta_aquisicao):
        try:
            if backup_ios.esta_cifrado(backup):
                cifrados.append(backup)
        except backup_ios.ErroBackupIOS as erro:
            resultado.falhas.append(f"{backup.name}: {erro}")
    if not cifrados:
        resultado.erro = traduzir("dec_ios_sem_backup", idi)
        return resultado

    manifesto = localizar_manifesto(pasta_aquisicao)
    try:
        selados = ler_manifesto(manifesto) if manifesto else {}
    except (OSError, ValueError):
        selados = {}

    destino_base = pasta_dos_decifrados(pasta_aquisicao)
    resultado.pasta = destino_base
    registros = []
    alvos = [a for arquivos in backup_ios.ARQUIVOS_DE_INTERESSE.values() for a in arquivos]
    for backup in cifrados:
        relativo_do_backup = backup.relative_to(pasta_aquisicao).as_posix()
        destino = destino_base / relativo_do_backup
        try:
            decifrados, ausentes = backup_ios.decifrar_arquivos(backup, senha, destino, alvos)
        except backup_ios.ErroBackupIOS as erro:
            resultado.falhas.append(f"{relativo_do_backup}: {erro}")
            continue
        for arquivo, saida in decifrados.items():
            origem = backup_ios.caminho_no_backup(backup, arquivo).relative_to(
                pasta_aquisicao).as_posix()
            procedencia = {
                "origem": origem,
                "arquivo_no_aparelho": arquivo.rotulo,
                "sha256_da_origem": calcular_sha256(pasta_aquisicao / origem),
                "sha256_da_origem_no_manifesto": selados.get(origem, ""),
                "sha256_do_decifrado": calcular_sha256(saida),
                "bytes_do_decifrado": saida.stat().st_size,
                "decifrado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
                "ferramenta": identificacao_ferramenta(),
                "metodo": traduzir("dec_ios_metodo", idi),
            }
            Path(str(saida) + SUFIXO_PROCEDENCIA).write_text(
                json.dumps(procedencia, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            resultado.decifrados.append(arquivo.rotulo)
            registros.append((origem, procedencia))
        resultado.falhas += [traduzir("dec_ios_sem_arquivo", idi, rotulo=rotulo)
                             for rotulo in ausentes]

    resultado.banco_principal = bool(resultado.decifrados)
    if not resultado.decifrados:
        resultado.erro = traduzir("dec_ios_nada", idi) + "\n" + "\n".join(resultado.falhas)
        return resultado

    linhas = [
        traduzir("dec_aquisicao", idi, aquisicao=pasta_aquisicao.name),
        traduzir("dec_ios_senha", idi, senha=senha),
        traduzir("dec_ios_metodo_linha", idi),
        "",
        traduzir("dec_ios_repetir", idi),
        "",
        traduzir("dec_ios_arquivos", idi),
    ]
    for origem, procedencia in registros:
        confere = _confere(procedencia, idi)
        linhas += [
            f"  {procedencia['arquivo_no_aparelho']}  ({origem})",
            f"    {traduzir('dec_sha_cifrado', idi)}   {procedencia['sha256_da_origem']} ({confere})",
            f"    {traduzir('dec_sha_decifrado', idi)} {procedencia['sha256_do_decifrado']} "
            f"({procedencia['bytes_do_decifrado']} bytes)",
        ]
    if resultado.falhas:
        linhas += ["", traduzir("dec_ios_nao_decifrados", idi)] + [f"  {t}" for t in resultado.falhas]
    try:
        caso = pasta_do_caso(pasta_aquisicao)
        if caso != pasta_aquisicao.resolve():
            juntar_complemento(
                caso, traduzir("dec_ios_complemento", idi, aquisicao=pasta_aquisicao.name),
                "\n".join(linhas)
            )
            gerar_manifesto(caso)
    except OSError as erro:
        resultado.falhas.append(traduzir("dec_nao_registrado", idi, erro=erro))
    return resultado
