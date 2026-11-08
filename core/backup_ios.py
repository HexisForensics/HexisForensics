"""
Leitura do backup local de um iPhone — o mesmo formato que o iTunes grava.

Um backup do iOS não guarda os arquivos com o nome que eles têm no
aparelho. Cada arquivo é identificado pelo par (domínio, caminho) —
`HomeDomain` + `Library/SMS/sms.db` — e gravado com o SHA-1 desse par como
nome, numa subpasta com os dois primeiros caracteres: `3d/3d0d7e5f...`. O
`Manifest.db` é o índice; o `Manifest.plist` diz se o backup está cifrado.

Duas situações, e nenhuma se confunde com "o aparelho não tinha o dado":

- **Backup sem criptografia**: o arquivo é localizado pelo SHA-1 do par e
  está em claro. Se não está lá, o backup NÃO o contém — o iOS decide o
  que entra (registro de chamadas, por exemplo, só vem em backup cifrado).
- **Backup cifrado**: cada arquivo tem chave própria, protegida pela senha
  de backup que o dono definiu no aparelho. Sem a senha nada se lê, e nada
  se afirma. Com ela, os arquivos de interesse são decifrados para FORA da
  aquisição (`decifrados/`), como o backup do WhatsApp no Android.

Nada aqui altera a pasta do backup: ela está sob o selo.
"""

from __future__ import annotations

import hashlib
import plistlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PASTA = "backup_ios"
# O backup cifrado tem pasta própria. Na mesma pasta, o iOS faz o segundo
# backup POR CIMA do primeiro (backup incremental): com os dois módulos
# marcados, o backup comum sumia e o desfecho continuava dizendo que ele
# tinha sido obtido (teste com o iPhone 11 real, 31/10/2026).
PASTA_CIFRADO = "backup_ios_cifrado"
PASTAS = (PASTA, PASTA_CIFRADO)
NOME_MANIFEST_PLIST = "Manifest.plist"
SUFIXOS_COMPANHEIROS = ("-wal", "-shm")


@dataclass(frozen=True)
class ArquivoIOS:
    """Um arquivo de interesse: onde ele mora no aparelho."""

    dominio: str
    caminho: str

    @property
    def identificador(self) -> str:
        """O nome do arquivo dentro do backup: SHA-1 de `dominio-caminho`."""
        return hashlib.sha1(f"{self.dominio}-{self.caminho}".encode("utf-8")).hexdigest()

    @property
    def nome(self) -> str:
        return self.caminho.rsplit("/", 1)[-1]

    @property
    def rotulo(self) -> str:
        return f"{self.dominio}/{self.caminho}"

    def companheiro(self, sufixo: str) -> "ArquivoIOS":
        return ArquivoIOS(self.dominio, self.caminho + sufixo)


# Os bancos que a suíte sabe ler. Cada chave pode ter mais de uma origem
# (o WhatsApp comum e o Business moram em domínios diferentes).
ARQUIVOS_DE_INTERESSE: Dict[str, Tuple[ArquivoIOS, ...]] = {
    "sms": (ArquivoIOS("HomeDomain", "Library/SMS/sms.db"),),
    "chamadas": (ArquivoIOS("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata"),),
    "contatos": (ArquivoIOS("HomeDomain", "Library/AddressBook/AddressBook.sqlitedb"),),
    "whatsapp": (
        ArquivoIOS("AppDomainGroup-group.net.whatsapp.WhatsApp.shared", "ChatStorage.sqlite"),
        ArquivoIOS("AppDomainGroup-group.net.whatsapp.WhatsAppSMB.shared", "ChatStorage.sqlite"),
    ),
}


class ErroBackupIOS(Exception):
    """O backup não pôde ser lido ou decifrado — a mensagem diz por quê."""


def localizar_backups(pasta: Path) -> List[Path]:
    """As pastas de backup do iOS dentro de `pasta` (as que têm `Manifest.plist`)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    return sorted(
        manifesto.parent for manifesto in pasta.rglob(NOME_MANIFEST_PLIST)
        if manifesto.is_file()
    )


def backups_da_aquisicao(pasta_aquisicao: Path) -> List[Path]:
    """Todos os backups do iOS da aquisição: o comum e o cifrado, cada um na sua pasta."""
    return [backup for nome in PASTAS
            for backup in localizar_backups(Path(pasta_aquisicao) / nome)]


def ler_manifest_plist(pasta_backup: Path) -> dict:
    try:
        dados = plistlib.loads((Path(pasta_backup) / NOME_MANIFEST_PLIST).read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError) as erro:
        raise ErroBackupIOS(f"O Manifest.plist do backup não pôde ser lido ({erro}).") from erro
    return dados if isinstance(dados, dict) else {}


def esta_cifrado(pasta_backup: Path) -> bool:
    return bool(ler_manifest_plist(pasta_backup).get("IsEncrypted"))


def caminho_no_backup(pasta_backup: Path, arquivo: ArquivoIOS) -> Path:
    """Onde o arquivo estaria dentro da pasta do backup (exista ou não)."""
    identificador = arquivo.identificador
    return Path(pasta_backup) / identificador[:2] / identificador


def materializar(pasta_backup: Path, arquivo: ArquivoIOS, destino: Path) -> Optional[Path]:
    """
    Copia um arquivo de backup SEM criptografia para `destino`, com o nome
    real e com os companheiros `-wal`/`-shm` ao lado — sem eles o SQLite
    não enxerga o que ainda não foi consolidado no banco. Devolve o caminho
    da cópia, ou `None` se o backup não contém o arquivo.

    O original, sob o selo, não é tocado.
    """
    original = caminho_no_backup(pasta_backup, arquivo)
    if not original.is_file():
        return None
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    copia = destino / arquivo.nome
    shutil.copy2(original, copia)
    for sufixo in SUFIXOS_COMPANHEIROS:
        companheiro = caminho_no_backup(pasta_backup, arquivo.companheiro(sufixo))
        if companheiro.is_file():
            shutil.copy2(companheiro, destino / (arquivo.nome + sufixo))
    return copia


def decifrar_arquivos(
    pasta_backup: Path, senha: str, destino: Path, arquivos: List[ArquivoIOS]
) -> Tuple[Dict[ArquivoIOS, Path], List[str]]:
    """
    Decifra, de um backup cifrado, os arquivos pedidos e seus companheiros.

    Grava em `destino/<domínio>/<caminho>`. Devolve `({arquivo: caminho},
    [ausentes])`: arquivo que o backup não contém é listado, não omitido.
    Senha errada levanta `ErroBackupIOS` — e nada é gravado.
    """
    try:
        from pyiosbackup import Backup
    except ImportError as erro:
        raise ErroBackupIOS(
            f"A biblioteca de leitura de backup do iPhone (pyiosbackup) não está instalada ({erro})."
        ) from erro
    try:
        backup = Backup.from_path(Path(pasta_backup), senha)
    except Exception as erro:
        raise ErroBackupIOS(
            "O backup não abriu com esta senha. É a senha de backup que o dono definiu no "
            f"iPhone (não o código de desbloqueio) ({type(erro).__name__}: {erro})."
        ) from erro

    decifrados: Dict[ArquivoIOS, Path] = {}
    ausentes: List[str] = []
    for arquivo in arquivos:
        for alvo in [arquivo] + [arquivo.companheiro(s) for s in SUFIXOS_COMPANHEIROS]:
            try:
                entrada = backup.get_entry_by_domain_and_path(alvo.dominio, alvo.caminho)
                conteudo = entrada.read_bytes()
            except Exception:
                if alvo is arquivo:
                    ausentes.append(arquivo.rotulo)
                continue
            saida = Path(destino) / alvo.dominio / alvo.caminho
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.write_bytes(conteudo)
            if alvo is arquivo:
                decifrados[arquivo] = saida
    return decifrados, ausentes


def informacoes_do_backup(pasta_backup: Path) -> dict:
    """O que o próprio backup declara: aparelho, versão, data, cifragem."""
    pasta_backup = Path(pasta_backup)
    dados = {}
    try:
        manifesto = ler_manifest_plist(pasta_backup)
    except ErroBackupIOS:
        manifesto = {}
    lockdown = manifesto.get("Lockdown") or {}
    dados["cifrado"] = "sim" if manifesto.get("IsEncrypted") else "não"
    dados["versao_ios"] = str(lockdown.get("ProductVersion") or "")
    dados["modelo"] = str(lockdown.get("ProductType") or "")
    dados["numero_serie"] = str(lockdown.get("SerialNumber") or "")
    dados["udid"] = str(lockdown.get("UniqueDeviceID") or "")
    dados["nome_do_aparelho"] = str(lockdown.get("DeviceName") or "")
    if manifesto.get("Date"):
        dados["data_do_backup"] = str(manifesto["Date"])
    return {chave: valor for chave, valor in dados.items() if valor}
