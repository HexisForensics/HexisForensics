"""
Testes da Ficha do Aparelho: a capa de leitura rápida da aquisicao.

A ficha e DERIVADA e NUNCA pode ser gravada dentro da aquisicao selada.
Ela abre com o que a coleta OBTEVE; o que nao veio consta como NAO APURADO
-- e NAO APURADO nunca e afirmado como ausencia do dado no aparelho. Cada
campo cita a fonte, dentro da aquisicao, de onde o valor foi lido.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core.aparelho import gravar_identificacao, gravar_tecnicos  # noqa: E402
from core.case import criar_pasta_aquisicao  # noqa: E402
from core.desfecho import (  # noqa: E402
    RESSALVA,
    SUCESSO,
    DesfechoDaColeta,
    ModuloExecutado,
    gravar_desfecho,
)
from core.ficha import NAO_APURADO, montar_ficha, render_texto  # noqa: E402
from core.hashing import calcular_sha256, conferir_manifesto, gerar_manifesto  # noqa: E402
from services import ficha_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402

aplicacao = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def ler_pdf(caminho: Path):
    documento = QPdfDocument()
    documento.load(str(caminho))
    paginas = documento.pageCount()
    return "\n".join(documento.getAllText(p).text() for p in range(paginas)), paginas


# Trecho real do `dumpsys trust`, como o modulo de estado inicial o preserva:
# o aparelho foi recebido DESBLOQUEADO (deviceLocked=0).
BLOQUEIO = (
    "Trust manager state:\n"
    "  User \"Owner\" (id=0, flags=0x13)\n"
    "    deviceLocked=0\n"
    "    trustManaged=0\n"
)


def montar_aquisicao(raiz: Path, caso: str, momento: datetime, lacre: str) -> Path:
    servico = CaseService(raiz)
    pasta = criar_pasta_aquisicao(raiz, caso, "Android", momento)
    servico.abrir_registro_procedimento(pasta, caso, "Android", "SERIAL-" + lacre)
    servico.registrar_operador(pasta, {"nome": "Fulana Examinadora", "funcao": "Perita"})
    servico.registrar_ambiente("1.0.41")
    servico.gravar_dados_do_caso(caso, {"referencia": "Proc. 88", "descricao": "Teste ficha"})
    servico.gravar_cadeia_custodia(pasta, caso, {"marca_modelo": "Telefone", "lacre": lacre})

    # Estado inicial: o aparelho chegou desbloqueado.
    (pasta / "estado_inicial").mkdir()
    (pasta / "estado_inicial" / "bloqueio_de_tela.txt").write_text(BLOQUEIO, encoding="utf-8")

    # O que os modulos de caracteristicas e identificacao apuraram. De
    # proposito, 'estado_criptografia' fica de fora: tem de sair NAO APURADO.
    gravar_tecnicos(pasta, {
        "fabricante": "Motorola",
        "modelo": "moto g(60)",
        "numero_serie": "ZF6XXSERIE",
        "versao_android": "13",
        "patch_seguranca": "2024-05-05",
        "boot_verificado": "green",
        "bootloader_travado": "1",
    })
    gravar_identificacao(pasta, {
        "imei": "350123456789012",
        "numero_telefone": "+5511999998888",
        "iccid": "89550900000000000011",
        "operadora_sim": "Operadora X",
    })

    # Desfecho: um modulo concluido, um com ressalva (acesso_negado ao IMEI).
    gravar_desfecho(pasta, DesfechoDaColeta(modulos=[
        ModuloExecutado("android_sms", "Mensagens SMS", situacao=SUCESSO,
                        mensagem="4 mensagem(ns)."),
        ModuloExecutado("android_identificacao", "Identificação do aparelho",
                        situacao=RESSALVA, mensagem="IMEI por via alternativa.",
                        ressalvas=["acesso_negado"]),
    ]))

    servico.encerrar_registro_procedimento("2 módulo(s) executado(s).")
    gerar_manifesto(pasta)
    return pasta


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / "extracoes"
    aquisicao = montar_aquisicao(raiz, "CASO_400", datetime(2026, 9, 10, 10, 0, 0), "L-9")
    caso = raiz / "CASO_400"

    # -----------------------------------------------------------------------
    print("\n[1] core.ficha: abre com o obtido, NAO APURADO para o que faltou")
    # -----------------------------------------------------------------------
    ficha = montar_ficha(aquisicao)
    por_rotulo = {c.rotulo: c for c in ficha.campos}

    checar("bloqueio ao receber vem do sistema, nao do examinador",
           por_rotulo["Bloqueio ao ser recebido"].valor == "DESBLOQUEADO"
           and por_rotulo["Bloqueio ao ser recebido"].apurado)
    checar("a fonte do bloqueio e o arquivo selado do estado inicial",
           por_rotulo["Bloqueio ao ser recebido"].fonte == "estado_inicial/bloqueio_de_tela.txt")
    checar("o IMEI obtido consta como apurado",
           por_rotulo["IMEI"].valor == "350123456789012" and por_rotulo["IMEI"].apurado)
    checar("numero e ICCID da linha constam (o que VEIO nao fica enterrado)",
           por_rotulo["Número de telefone"].valor == "+5511999998888"
           and por_rotulo["ICCID do chip"].valor == "89550900000000000011")
    checar("campo nao obtido consta como NAO APURADO, e marcado como nao apurado",
           por_rotulo["Estado da criptografia"].valor == NAO_APURADO
           and not por_rotulo["Estado da criptografia"].apurado)
    checar("versao do sistema sai numa linha so (Android, aqui)",
           por_rotulo["Versão do sistema"].valor == "13")
    checar("campo opcional nao apurado (UDID) NAO polui a ficha",
           "UDID" not in por_rotulo)
    checar("o desfecho da coleta entra na ficha",
           "2 módulo(s)" in por_rotulo["Desfecho da coleta"].valor)
    checar("a ressalva declarada e carregada junto",
           ficha.ressalvas and ficha.ressalvas[0][0] == "Identificação do aparelho"
           and "acesso_negado" in ficha.ressalvas[0][1])

    texto = render_texto(ficha)
    checar("o texto diz que NAO APURADO != ausencia no aparelho",
           "não significa ausência do dado no aparelho" in texto)

    # -----------------------------------------------------------------------
    print("\n[2] ficha_service: PDF fora do selo, com o selo impresso")
    # -----------------------------------------------------------------------
    documento = ficha_service.gerar(aquisicao)
    checar("a ficha e gerada sem erro",
           not documento.erro and documento.caminho.is_file())
    checar("fica em <caso>/documentos, FORA da aquisicao",
           documento.caminho.parent.resolve() == (caso / "documentos").resolve())
    checar("o nome do arquivo identifica a aquisicao de origem",
           aquisicao.name in documento.caminho.name)
    checar("a aquisicao continua integra depois da ficha",
           conferir_manifesto(aquisicao).integro)

    texto_pdf, paginas = ler_pdf(documento.caminho)
    selo = calcular_sha256(aquisicao / "manifesto_hashes.txt")
    checar("o SHA-256 do manifesto esta no rodape de toda pagina",
           texto_pdf.count(selo) >= paginas)
    checar("o titulo e FICHA DO APARELHO", "FICHA DO APARELHO" in texto_pdf)
    checar("o bloqueio ao receber consta", "DESBLOQUEADO" in texto_pdf)
    checar("o IMEI obtido consta", "350123456789012" in texto_pdf)
    checar("o que nao veio aparece como NAO APURADO", NAO_APURADO in texto_pdf)
    checar("a fonte selada e citada", "estado_inicial/bloqueio_de_tela.txt" in texto_pdf)
    checar("as paginas sao numeradas com o total", f"Página 1 de {paginas}" in texto_pdf)

    segunda = ficha_service.gerar(aquisicao)
    checar("reemitir NAO apaga a emissao anterior",
           segunda.caminho != documento.caminho and documento.caminho.is_file())

    # Pasta fora do padrao de nome: a ficha NAO pode cair dentro do selo.
    avulsa = raiz / "pasta_fora_do_padrao"
    avulsa.mkdir()
    (avulsa / "dado.txt").write_text("x", encoding="utf-8")
    gerar_manifesto(avulsa)
    documento_avulso = ficha_service.gerar(avulsa)
    checar("pasta fora do padrao: a ficha NAO e gravada dentro dela",
           not documento_avulso.erro
           and avulsa.resolve() not in documento_avulso.caminho.resolve().parents)
    checar("e ela continua integra", conferir_manifesto(avulsa).integro)

    # -----------------------------------------------------------------------
    print("\n[3] Aquisicao sem registros: a ficha nao inventa, so NAO APURADO")
    # -----------------------------------------------------------------------
    vazia = criar_pasta_aquisicao(raiz, "CASO_401", "Android", datetime(2026, 9, 11, 10, 0, 0))
    gerar_manifesto(vazia)
    ficha_vazia = montar_ficha(vazia)
    checar("sem nada apurado, nenhum campo mente",
           not ficha_vazia.algum_apurado
           and all(c.valor == NAO_APURADO for c in ficha_vazia.campos))
    documento_vazio = ficha_service.gerar(vazia)
    checar("e a ficha ainda e gerada, so que toda NAO APURADA",
           not documento_vazio.erro and documento_vazio.caminho.is_file())

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
