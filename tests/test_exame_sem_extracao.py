"""
Testes do exame sem extração: aparelho bloqueado, que não liga ou quebrado.

O laudo negativo precisa ser honesto nos dois sentidos: diz com clareza que
não foi possível extrair, e NUNCA diz que o aparelho não tem dados. O que
o examinador declara sai como declaração; a resposta do aparelho à
tentativa de conexão sai como registro, sob o selo.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core.android.adb_client import ResultadoComando  # noqa: E402
from core.base_extractor import Plataforma  # noqa: E402
from core.case import criar_pasta_aquisicao  # noqa: E402
from core.exame_sem_extracao import (  # noqa: E402
    NOME_EXAME,
    NOME_TENTATIVA,
    PASTA,
    ExameSemExtracao,
    ler_exame,
)
from core.hashing import conferir_manifesto  # noqa: E402
from services import laudo_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402
from services.exame_service import criar_registro, e_exame_sem_extracao  # noqa: E402
from services.extraction_service import ExtractionService  # noqa: E402

aplicacao = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def ler_pdf(caminho: Path) -> str:
    documento = QPdfDocument()
    documento.load(str(caminho))
    return " ".join(
        " ".join(documento.getAllText(p).text().split()) for p in range(documento.pageCount())
    )


class ADBFalso:
    def __init__(self, stdout):
        self.stdout = stdout
        self.comandos = []

    def executar_detalhado(self, argumentos, timeout=None, vincular_serial=True):
        self.comandos.append((argumentos, vincular_serial))
        return ResultadoComando(0, self.stdout, "")


class IPhoneFalso:
    def __init__(self, publicos):
        self.publicos = publicos

    def sondar(self):
        if not self.publicos:
            return ["listagem de dispositivos: 1 iPhone(s) visível(is)",
                    "sessão sem pareamento: RECUSADA — PasswordProtected"], {}
        return ["listagem de dispositivos: 1 iPhone(s) visível(is)",
                "sessão sem pareamento: aberta; o iPhone NÃO confia nesta estação"], self.publicos


BLOQUEADO = {
    "liga": "Sim", "estado_ao_receber": "Desligado", "bateria": "40%",
    "isolado_da_rede": "Sim", "tipo_de_bloqueio": "PIN numérico",
    "tentativas": "Aparelho ligado; tela de bloqueio por PIN; credencial não fornecida.",
    "recomendacao": "Reexame mediante fornecimento da credencial de desbloqueio.",
}

with tempfile.TemporaryDirectory() as temporario:
    raiz = Path(temporario) / "extracoes"

    # -----------------------------------------------------------------------
    print("\n[1] A tentativa de conexão é registrada, sem alterar o aparelho")
    # -----------------------------------------------------------------------
    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "Android", datetime(2026, 10, 24, 9, 0))
    adb = ADBFalso("List of devices attached\nZY22ABC\tunauthorized usb:1-1 transport_id:3")
    resultado = ExameSemExtracao(Plataforma.ANDROID, BLOQUEADO, client=adb).executar(pasta)
    checar("o registro NUNCA é sucesso: nenhum dado do conteúdo foi obtido",
           not resultado.sucesso and "Nenhum dado do conteúdo" in resultado.mensagem)
    checar("o único comando é a listagem global do ADB, que não altera nada",
           adb.comandos == [(["devices", "-l"], False)])
    checar("a resposta 'unauthorized' vira resultado legível",
           "NÃO AUTORIZADO" in resultado.mensagem and "ZY22ABC" in resultado.mensagem)
    bruto = (pasta / PASTA / NOME_TENTATIVA).read_text(encoding="utf-8")
    checar("e a resposta crua do ADB fica preservada", "unauthorized usb:1-1" in bruto)
    exame = ler_exame(pasta)
    checar("o que o examinador declarou fica gravado junto",
           exame["tipo_de_bloqueio"] == "PIN numérico" and exame["tentativa"]["realizada"])

    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "Android", datetime(2026, 10, 24, 9, 1))
    adb = ADBFalso("List of devices attached\n")
    resultado = ExameSemExtracao(Plataforma.ANDROID, BLOQUEADO, client=adb).executar(pasta)
    checar("nenhum aparelho no ADB é dito como tal, sem inventar a causa",
           "nenhum aparelho respondeu ao ADB" in resultado.mensagem)

    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "Android", datetime(2026, 10, 24, 9, 2))
    adb = ADBFalso("não deveria ser chamado")
    resultado = ExameSemExtracao(
        Plataforma.ANDROID, dict(BLOQUEADO, liga="Não"), client=adb).executar(pasta)
    checar("aparelho que não liga: nenhuma tentativa, e isso é dito",
           not adb.comandos and "não realizada" in resultado.mensagem)

    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "iOS", datetime(2026, 10, 24, 9, 3))
    resultado = ExameSemExtracao(Plataforma.IOS, BLOQUEADO, client=IPhoneFalso(
        {"ProductType": "iPhone12,3", "ProductVersion": "17.5", "UniqueDeviceID": "UDID1"}
    )).executar(pasta)
    checar("iPhone sem confiança: detectado, e diz que NÃO confia na estação",
           "NÃO confia" in resultado.mensagem and "iPhone12,3" in resultado.mensagem)
    from core.aparelho import ler_caracteristicas  # noqa: E402
    checar("o que o iPhone informa sem pareamento entra como apurado do aparelho",
           dict(ler_caracteristicas(pasta).em_pares()).get("Versão do iOS") == "17.5")

    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "iOS", datetime(2026, 10, 24, 9, 4))
    resultado = ExameSemExtracao(Plataforma.IOS, BLOQUEADO, client=IPhoneFalso({})).executar(pasta)
    checar("iPhone que recusa a sessão: a recusa é registrada com o texto do erro",
           "não permitiu a comunicação" in resultado.mensagem
           and "PasswordProtected" in resultado.mensagem)

    # -----------------------------------------------------------------------
    print("\n[2] Pelo caminho de toda aquisição: registro, selo e laudo negativo")
    # -----------------------------------------------------------------------
    servico = CaseService(raiz)
    pasta = criar_pasta_aquisicao(raiz, "CASO_NEG", "Android", datetime(2026, 10, 24, 10, 0))
    servico.abrir_registro_procedimento(pasta, "CASO_NEG", "Android", "celular_android")
    servico.registrar_operador(pasta, {"nome": "Fulana Examinadora"})
    servico.gravar_dados_do_caso("CASO_NEG", {"referencia": "Proc. 99", "descricao": "Teste"})
    servico.gravar_cadeia_custodia(pasta, "CASO_NEG", {"marca_modelo": "Motorola", "lacre": "L-77"})

    registro = criar_registro("Android", BLOQUEADO)
    registro.client = ADBFalso("List of devices attached\nZY22ABC\tunauthorized")
    ExtractionService([registro], pasta).run()
    checar("a aquisição fecha com selo íntegro", conferir_manifesto(pasta).integro)
    checar("e é reconhecida como exame sem extração", e_exame_sem_extracao(pasta))
    procedimento = (pasta / "registro_procedimento.txt").read_text(encoding="utf-8")
    checar("o registro do procedimento traz a decisão e o motivo",
           "Exame registrado SEM extração" in procedimento)
    checar("e NÃO afirma depuração USB autorizada (não houve)",
           "Depuração USB ativada" not in procedimento)

    documento = laudo_service.gerar(
        pasta, {"numero": "12/2026", "objetivo": "Extração de conversas.",
                "consideracoes": ""},
        examinador={"nome": "Fulana Examinadora"},
    )
    checar("o laudo é gerado sem erro", not documento.erro and documento.caminho.is_file())
    texto = ler_pdf(documento.caminho)
    checar("é a versão 'Exame sem Extração'", "Exame sem Extração" in texto)
    checar("traz o estado declarado e o tipo de bloqueio",
           "PIN numérico" in texto and "40%" in texto)
    checar("traz a tentativa registrada, com o resultado do aparelho",
           "NÃO AUTORIZADO" in texto and "tentativa_de_conexao.txt" in texto)
    checar("a conclusão diz que não foi possível extrair",
           "Não foi possível extrair dados do dispositivo" in texto)
    checar("e que isso NÃO é ausência de dados",
           "não é ausência de dados" in texto and "NÃO permite concluir" in texto)
    checar("traz a recomendação", "Reexame mediante fornecimento da credencial" in texto)
    checar("o lacre da peça consta", "L-77" in texto)
    checar("o nome genérico da aquisição NÃO sai como apurado do aparelho",
           "celular_android" not in texto.split("Registro examinado")[0]
           and "Identificador usado na aquisição" not in texto
           and "não houve extração, e a tentativa de conexão" in texto
           and "módulos que as leem não foram executados" not in texto)
    checar("não traz seções de conteúdo que não existe",
           "Conteúdo interpretado" not in texto and "Módulos empregados" not in texto)
    checar("o laudo fica fora da aquisição, que continua íntegra",
           pasta.resolve() not in documento.caminho.resolve().parents
           and conferir_manifesto(pasta).integro)

print("\n" + "=" * 60)
if falhas:
    print(f"FALHARAM {len(falhas)} verificação(ões):")
    for nome in falhas:
        print(f"  - {nome}")
    sys.exit(1)
print("Todas as verificações passaram.")
