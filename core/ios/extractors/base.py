"""
Base comum a todos os extratores iOS — contraparte de
`core.android.extractors.base.AndroidExtractor`.

Implementa o mesmo contrato (`BaseExtractor`) do Android, então a
interface e o `ExtractionWorker` tratam as duas plataformas do mesmo jeito.

Aqui mora também o backup local, que é o coração da aquisição de iPhone
sem jailbreak: os dois módulos de backup (o comum e o de senha temporária)
fazem a mesma cópia e conferem o resultado da mesma maneira.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from core import backup_ios
from core.base_extractor import BaseExtractor, Plataforma, ResultadoExtracao
from core.hashing import calcular_sha256

from ..client import ErroIOS, IOSClient
from ..device import IOSDevice

NOME_HASHES = "hashes_na_aquisicao.txt"

# O que um backup SEM criptografia não traz, por decisão do próprio iOS.
EXCLUIDO_DO_BACKUP_SEM_CIFRA = (
    "registro de chamadas, senhas salvas, histórico de navegação, configurações de Wi-Fi "
    "e dados de saúde"
)


@dataclass
class DesfechoBackup:
    pasta: Optional[Path] = None
    arquivos: int = 0
    bytes_copiados: int = 0
    cifrado: Optional[bool] = None
    erro: str = ""
    hashes: List[Tuple[str, str, int]] = field(default_factory=list)


class IOSExtractor(BaseExtractor):
    plataforma = Plataforma.IOS
    # Onde o backup deste módulo é gravado, dentro da aquisição.
    pasta_do_backup = backup_ios.PASTA
    rotulo_privilegio = "requer jailbreak"

    def __init__(self, client: Optional[IOSClient] = None, **kwargs):
        super().__init__(**kwargs)
        self.client = client or IOSClient()
        self.device = IOSDevice(self.client)

    def definir_udid(self, udid: Optional[str]) -> None:
        """Vincula o módulo ao iPhone do caso — o `adb -s <serial>` do iOS."""
        self.client.definir_udid(udid)

    def disponivel(self) -> Tuple[bool, str]:
        return self.client.verificar_disponibilidade()

    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        return ResultadoExtracao(
            sucesso=False,
            mensagem=f"{self.nome_exibicao}: módulo sem implementação nesta versão.",
        )

    # ------------------------------------------------------------------
    def fazer_backup(self, pasta_caso: Path) -> DesfechoBackup:
        """
        Faz o backup local em `<aquisição>/<pasta_do_backup>/<UDID>/` e o confere.

        O hash de cada arquivo é calculado assim que o backup termina, antes
        de qualquer leitura, e gravado ao lado — é o estado do material no
        momento da aquisição.
        """
        desfecho = DesfechoBackup()
        destino = Path(pasta_caso) / self.pasta_do_backup
        ultimo = [-10]

        def progresso(percentual) -> None:
            try:
                valor = int(float(percentual))
            except (TypeError, ValueError):
                return
            self.progresso(10 + int(valor * 0.8))
            if valor >= ultimo[0] + 10:
                ultimo[0] = valor
                self.log(f"    backup: {valor}%")

        self.log("[*] Fazendo o backup local do iPhone (mantenha o cabo conectado e a tela "
                 "desbloqueada; pode levar muitos minutos)...")
        try:
            desfecho.pasta = self.client.fazer_backup(destino, progresso)
        except ErroIOS as erro:
            desfecho.erro = str(erro)
            if getattr(erro, "original", ""):
                self.log(f"    resposta do iPhone: {erro.original}")
            return desfecho

        if not (desfecho.pasta / backup_ios.NOME_MANIFEST_PLIST).is_file():
            desfecho.erro = (
                "O backup terminou sem o Manifest.plist: o material não é um backup completo "
                "e não será interpretado."
            )
            return desfecho
        try:
            desfecho.cifrado = backup_ios.esta_cifrado(desfecho.pasta)
        except backup_ios.ErroBackupIOS as erro:
            desfecho.erro = str(erro)
            return desfecho

        self.log("[*] Calculando o SHA-256 de cada arquivo do backup...")
        for arquivo in sorted(p for p in desfecho.pasta.rglob("*") if p.is_file()):
            tamanho = arquivo.stat().st_size
            desfecho.hashes.append(
                (calcular_sha256(arquivo), arquivo.relative_to(destino).as_posix(), tamanho)
            )
            desfecho.arquivos += 1
            desfecho.bytes_copiados += tamanho
        (destino / NOME_HASHES).write_text(
            "".join(f"{resumo} *{nome}  ({tamanho} bytes)\n"
                    for resumo, nome, tamanho in desfecho.hashes),
            encoding="utf-8",
        )
        return desfecho
