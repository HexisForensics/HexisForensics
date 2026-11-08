"""
Ponto de entrada da aplicação HexisForensics.

A identidade visual (cores, logo, ícone, nome de exibição) é carregada a
partir de um perfil de branding (ver `services.branding_service`) — gerar
uma build "de marca branca" para outro cliente é: criar uma nova pasta em
`branding/<nome>/branding.json` e apontar `branding/active.json` para ela
(campo "perfil"). Nenhuma alteração de código nem variável de ambiente é
necessária.

Uso:
    python main.py

Requisitos: ver requirements.txt (principalmente PySide6).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from services import registro_de_erros
from services.branding_service import carregar_branding
from ui.main_window import MainWindow
from ui.style import aplicar_tema
from ui.widgets.tela_entrada import TelaEntrada


def autoteste(caminho_saida: str) -> int:
    """
    Confere, DE DENTRO do programa em execução, o que só se descobre
    executando: quantos módulos de extração cada plataforma enxerga, onde
    a suíte acha que está instalada e se encontrou o ADB.

    Existe por causa do empacotamento. Os extratores são descobertos por
    import dinâmico, que o empacotador não vê: um executável montado sem
    eles abre normalmente e mostra a lista de módulos VAZIA, sem erro
    nenhum. O script de build roda isto contra o executável pronto e
    compara com o código-fonte.
    """
    import json
    from pathlib import Path

    from core.android.adb_client import ADBClient
    from core.instalacao import empacotada, modo_desenvolvimento, raiz_da_instalacao
    from services.device_service import ANDROID, COMPUTADOR, IOS
    from services.extraction_service import listar_extratores
    from ui.main_window import PASTA_EXTRACOES

    adb_ok, adb_mensagem = ADBClient().verificar_binario()
    relatorio = {
        "empacotada": empacotada(),
        "raiz_da_instalacao": str(raiz_da_instalacao()),
        "pasta_extracoes": str(PASTA_EXTRACOES),
        "modulos": {
            nome: sorted(classe.id for classe in listar_extratores(nome))
            for nome in (ANDROID, IOS, COMPUTADOR)
        },
        "adb_encontrado": adb_ok,
        # A conta de testes (Forensic Admin) nunca pode existir na versão
        # distribuída; o empacotador recusa a entrega se existir.
        "forensic_admin_disponivel": modo_desenvolvimento(),
        "adb_mensagem": adb_mensagem,
        "marca": carregar_branding().nome_exibicao,
    }
    Path(caminho_saida).write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


def _avisar_erro(caminho, resumo: str) -> None:
    """Mostra ao examinador que algo deu errado e onde ficou o registro."""
    from PySide6.QtWidgets import QMessageBox

    onde = (f"Os detalhes foram gravados em:\n{caminho}\n\nEnvie este arquivo a quem dá "
            "suporte à ferramenta.") if caminho else "Não foi possível gravar os detalhes."
    QMessageBox.critical(
        None, "Erro inesperado",
        f"A ferramenta encontrou um erro inesperado:\n{resumo}\n\n{onde}\n\n"
        "Se a tela parar de responder, feche a ferramenta e abra de novo. Nenhuma "
        "aquisição lacrada é alterada por este erro.",
    )


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--autoteste":
        return autoteste(sys.argv[2])

    # Sem isto o Windows agrupa a janela sob o ícone do interpretador
    # Python na barra de tarefas, e não sob o da suíte.
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HexisForensics.Suite")
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    registro_de_erros.instalar(avisar=_avisar_erro)
    # O programa termina quando a janela principal FECHA, e não quando a
    # última janela visível some: no bloqueio e na troca de examinador a
    # principal fica escondida, e fechar a tela de entrada encerrava tudo
    # logo depois de a senha ser aceita.
    app.setQuitOnLastWindowClosed(False)

    marca = carregar_branding()  # resolve sozinho via branding/active.json

    app.setApplicationName(marca.nome_exibicao)
    app.setOrganizationName(marca.nome_exibicao)
    aplicar_tema(app, marca)

    # Ninguém usa a suíte sem entrar: a sessão é quem assina cada aquisição.
    if TelaEntrada(marca).exec() != TelaEntrada.Accepted:
        return 0

    janela = MainWindow(marca)
    janela.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
