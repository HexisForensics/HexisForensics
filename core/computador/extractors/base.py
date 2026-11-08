"""
Base comum a todos os extratores de Computador: fornece acesso
compartilhado a um `ComputadorDevice` e implementa a checagem padrão de
disponibilidade (execução no Windows + unidade alvo ainda acessível).

Diferente do Android/iOS — onde existe "o" dispositivo conectado via
cabo/pareamento —, aqui o examinador escolhe, entre as unidades detectadas
pelo Windows, qual será periciada. Isso significa que a unidade alvo
(`caminho_unidade`, ex. 'E:\\') não é conhecida no momento em que a classe
é instanciada: a GUI instancia todos os extratores selecionados da mesma
forma para as três plataformas (`classe()`, sem argumentos). Por isso a
unidade é definida em seguida, via `definir_unidade()`, chamado pela
camada de serviço assim que o examinador escolhe a unidade no
`DiskPanel` — antes de checar `disponivel()` ou rodar `executar()`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

from core.base_extractor import BaseExtractor, Plataforma
from core.case import raiz_das_extracoes

from core.instalacao import raiz_da_instalacao

from .. import disk_client
from ..device import ComputadorDevice


def raiz_instalacao_suite() -> Path:
    """
    Diretório onde a suíte está instalada **agora**, descoberto a cada
    chamada — nunca um caminho fixo. Uma instalação movida (Desktop,
    outro disco, ambiente de teste) continua sendo detectada.

    Os dois modos de execução respondem de formas diferentes, e é por isso
    que há dois caminhos aqui:

    - **Rodando do código-fonte**, este arquivo vive em
      `<raiz>/core/computador/extractors/base.py`, três níveis abaixo da
      raiz.
    - **Empacotada em executável**, `__file__` aponta para dentro da pasta
      temporária que o empacotador cria ao descompactar o programa
      (`sys._MEIPASS`), que não tem relação nenhuma com o lugar onde o
      `.exe` está. Contar `parents` ali devolveria uma pasta do `Temp`, e
      a proteção contra copiar a própria suíte apontaria para o lugar
      errado — some sem falhar, que é o pior modo de sumir. Congelada, a
      referência que vale é `sys.executable`.
    """
    return raiz_da_instalacao()


def podar_subpastas_ignoradas(
    pasta_atual: str, subpastas: List[str], pastas_ignoradas: List[Path]
) -> List[Path]:
    """
    Remove de `subpastas` **em memória** (a lista que `os.walk` usa para
    decidir onde descer em seguida) qualquer subpasta direta de
    `pasta_atual` que esteja em `pastas_ignoradas`. É assim que se poda um
    `os.walk` em andamento — alterar a lista no lugar impede o walk de
    sequer visitar aquele diretório, o que é o que evita o loop de
    cópia/indexação (ver `ComputadorExtractor.pastas_a_ignorar`).
    Compartilhado por `logical_copy.py` e `file_index.py`. Devolve os
    caminhos removidos, para o chamador poder registrar o que excluiu.

    `resolve()` é chamado **uma vez por subpasta**, e não uma vez por
    teste: ele vai ao sistema de arquivos para desfazer junções e links, e
    esta função roda em cada nível de uma varredura que pode percorrer um
    disco inteiro, com centenas de milhares de diretórios.
    """
    pasta_atual_path = Path(pasta_atual)
    mantidas: List[str] = []
    excluidas: List[Path] = []
    for nome in subpastas:
        caminho = pasta_atual_path / nome
        if caminho.resolve() in pastas_ignoradas:
            excluidas.append(caminho)
        else:
            mantidas.append(nome)
    if excluidas:
        subpastas[:] = mantidas
    return excluidas


class ComputadorExtractor(BaseExtractor):
    plataforma = Plataforma.COMPUTADOR

    def __init__(self, device: Optional[ComputadorDevice] = None, **kwargs):
        super().__init__(**kwargs)
        self.device = device or ComputadorDevice()
        self.caminho_unidade: Optional[str] = None

    def definir_unidade(self, caminho_unidade: str) -> None:
        """
        Define qual unidade (ex.: 'E:\\') este extrator vai periciar.
        Chamado pela camada de serviço assim que o examinador escolhe a
        unidade no `DiskPanel`, antes de checar `disponivel()`/rodar
        `executar()`.
        """
        self.caminho_unidade = caminho_unidade

    def disponivel(self) -> Tuple[bool, str]:
        if not disk_client.rodando_no_windows():
            return False, "Este módulo funciona apenas no Windows."

        if not self.caminho_unidade:
            return False, "Nenhuma unidade de disco foi selecionada."

        status = self.device.verificar_unidade(self.caminho_unidade)
        if not status.disponivel:
            return False, status.mensagem
        return True, ""

    def unidade_obrigatoria(self) -> str:
        """
        Devolve `caminho_unidade` já validado como não-nulo, para uso em
        `executar()`. A camada de serviço só chama `executar()` depois que
        `disponivel()` confirmou que uma unidade foi definida (ver
        `services/extraction_service.py`), então a ausência aqui indica um
        uso indevido da classe — por isso a checagem é uma `assert`, não um
        retorno de erro tratável.
        """
        assert self.caminho_unidade is not None, (
            "executar() foi chamado sem definir_unidade() ter sido chamado antes "
            "(ou sem checar disponivel())."
        )
        return self.caminho_unidade

    def pastas_a_ignorar(self, pasta_aquisicao: Path) -> List[Path]:
        """
        Pastas que nunca devem ser percorridas, copiadas ou indexadas como
        se fossem conteúdo do disco periciado — recalculadas a cada
        chamada, nunca fixas:

        1. `raiz_instalacao_suite()` — onde o HexisForensics estiver
           instalado neste momento (código-fonte, `.git/`, binários e a
           saída das extrações). É a proteção principal: periciar a
           própria unidade onde a suíte roda é comum ao testar sem disco
           externo à mão, e nem o código nem a saída são dado do usuário.
        2. `raiz_das_extracoes(pasta_aquisicao)` — a pasta que guarda
           **todos** os casos. Na instalação padrão é redundante com a
           primeira, e continua valendo se a saída for configurada fora da
           pasta da suíte.

        O segundo item sobe pela `core.case`, e não por `.parent`: o que
        chega aqui é a pasta da **aquisição**
        (`extracoes/CASO_012/computador_20260828_143000`), não a do caso.
        Um `.parent` só pararia na pasta do caso corrente e deixaria os
        **demais casos** de fora da exclusão — a aquisição copiaria para
        dentro de si a evidência de todos os casos anteriores, e o
        manifesto a selaria como se fosse do disco periciado.

        Sem essas exclusões, um extrator que copia ou indexa arquivos
        entra em recursão ao encontrar a própria saída dentro da árvore
        que varre, copiando de volta para dentro de si o que acabou de
        gravar, até parecer travado ou encher o disco.
        """
        return [raiz_instalacao_suite(), raiz_das_extracoes(pasta_aquisicao)]
