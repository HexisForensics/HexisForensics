"""
Testes dos documentos em PDF: Relatorio de Extracao e Laudo Pericial.

Os documentos sao derivados e NUNCA podem ser gravados dentro da aquisicao
selada -- nem quando a pasta nao segue o padrao de nome. E so afirmam o que
os registros da aquisicao sustentam: o que nao foi informado ou coletado
consta como nao informado ou nao coletado.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from core.case import criar_pasta_aquisicao  # noqa: E402
from core.hashing import calcular_sha256, conferir_manifesto, gerar_manifesto  # noqa: E402
from services import laudo_service, relatorio_extracao_service  # noqa: E402
from services.case_service import CaseService  # noqa: E402

aplicacao = QGuiApplication.instance() or QGuiApplication(sys.argv)
falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def ler_pdf(caminho: Path):
    """(texto de todas as paginas, quantidade de paginas)."""
    documento = QPdfDocument()
    documento.load(str(caminho))
    paginas = documento.pageCount()
    return "\n".join(documento.getAllText(p).text() for p in range(paginas)), paginas


SMS = (
    "Row: 0 _id=1, address=+5511911112222, date=1756000000000, type=1, read=1, "
    "body=Encontro na padaria amanha\n"
    "Row: 1 _id=2, address=+5511933334444, date=1756000100000, type=2, read=1, "
    "body=Combinado, levo o documento\n"
)
CONTATOS = "Row: 0 display_name=Fulano Padeiro, data1=+5511911112222\n"


def montar_aquisicao(raiz: Path, caso: str, momento: datetime, lacre: str) -> Path:
    servico = CaseService(raiz)
    pasta = criar_pasta_aquisicao(raiz, caso, "Android", momento)
    servico.abrir_registro_procedimento(pasta, caso, "Android", "SERIAL-" + lacre)
    servico.registrar_operador(pasta, {"nome": "Fulana Examinadora", "funcao": "Perita"})
    servico.registrar_ambiente("1.0.41")
    servico.gravar_dados_do_caso(caso, {"referencia": "Proc. 77", "descricao": "Teste"})
    servico.gravar_cadeia_custodia(pasta, caso, {"marca_modelo": "Telefone", "lacre": lacre})
    (pasta / "sms").mkdir()
    (pasta / "sms" / "sms_todas.txt").write_text(SMS, encoding="utf-8")
    (pasta / "contacts_calls").mkdir()
    (pasta / "contacts_calls" / "agenda_contatos_bruta.txt").write_text(CONTATOS, encoding="utf-8")
    (pasta / "media").mkdir()
    (pasta / "media" / "foto.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
    (pasta / "media" / "anotacoes.txt").write_text("senha do cofre: girassol", encoding="utf-8")
    (pasta / "media" / "contrato.pdf").write_bytes(b"%PDF-1.4 teste")
    (pasta / "media" / "gravacao.opus").write_bytes(b"OggS" + b"0" * 32)
    (pasta / "media" / "sem_extensao").write_bytes(b"?")
    servico.encerrar_registro_procedimento("1 módulo(s) executado(s).")
    gerar_manifesto(pasta)
    return pasta


with tempfile.TemporaryDirectory() as tmp:
    raiz = Path(tmp) / "extracoes"
    primeira = montar_aquisicao(raiz, "CASO_300", datetime(2026, 9, 1, 10, 0, 0), "L-1")
    segunda = montar_aquisicao(raiz, "CASO_300", datetime(2026, 9, 2, 10, 0, 0), "L-2")
    caso = raiz / "CASO_300"

    # -----------------------------------------------------------------------
    print("\n[1] Relatorio de Extracao: fora do selo, com o selo impresso")
    # -----------------------------------------------------------------------
    relatorio = relatorio_extracao_service.gerar(primeira)
    checar("o relatorio e gerado sem erro",
           not relatorio.erro and relatorio.caminho.is_file())
    checar("fica em <caso>/documentos, FORA da aquisicao",
           relatorio.caminho.parent.resolve() == (caso / "documentos").resolve())
    checar("a aquisicao continua integra depois do relatorio",
           conferir_manifesto(primeira).integro)
    texto, paginas = ler_pdf(relatorio.caminho)
    selo = calcular_sha256(primeira / "manifesto_hashes.txt")
    checar("o SHA-256 do manifesto esta no documento", selo in texto)
    checar("em TODA pagina (rodape), alem da secao de integridade",
           texto.count(selo) >= paginas + 1)
    checar("o lacre da peca consta", "L-1" in texto)
    checar("o operador gravado na aquisicao consta", "Fulana Examinadora" in texto)
    checar("o ambiente e o gravado NO DIA (versao do ADB do registro)", "1.0.41" in texto)
    checar("o conteudo interpretado e resumido", "Mensagens SMS" in texto)
    checar("artefato nao coletado e dito como NAO COLETADO", "NÃO COLETADO" in texto)
    checar("as paginas sao numeradas com o total", f"Página 1 de {paginas}" in texto)

    # --- arquivos por categoria
    from core.categorias import CATEGORIAS, categoria_do_arquivo  # noqa: E402
    from services.dossie_service import montar_dossie  # noqa: E402

    por_nome = {c.nome: c for c in montar_dossie(primeira).categorias}
    checar("o relatorio tem a secao de arquivos por categoria",
           "Arquivos adquiridos, por categoria" in texto)
    checar("cada arquivo cai na categoria da sua extensao",
           por_nome["Imagens"].quantidade == 1 and por_nome["PDF"].quantidade == 1
           and por_nome["Áudios"].quantidade == 1)
    checar("arquivo sem extensao vai para Outros, sem palpite",
           [c for c, _ in por_nome["Outros"].arquivos] == ["media/sem_extensao"])
    checar("categoria vazia APARECE, com zero",
           por_nome["Vídeos"].quantidade == 0 and len(por_nome) == len(CATEGORIAS))
    todos = [c for categoria in por_nome.values() for c, _ in categoria.arquivos]
    checar("os registros da propria aquisicao NAO sao contados como arquivo adquirido",
           not any(c.startswith(("metodo/", "desfecho/", "aquisicao/")) or "/" not in c
                   for c in todos)
           and "registro_procedimento.txt" not in todos)
    checar("mas as saidas de comando dos modulos sim, como texto",
           "sms/sms_todas.txt" in [c for c, _ in por_nome["Texto e registros"].arquivos])
    checar("o caminho de origem do arquivo consta do relatorio",
           "media/contrato.pdf" in texto and "media/gravacao.opus" in texto)
    checar("backup do WhatsApp e banco, qualquer que seja o numero do crypt",
           categoria_do_arquivo("msgstore.db.crypt15") == categoria_do_arquivo("wa.db")
           == "Bancos de dados e backups de aplicativo")

    segundo = relatorio_extracao_service.gerar(primeira)
    checar("reemitir NAO apaga a emissao anterior",
           segundo.caminho != relatorio.caminho and relatorio.caminho.is_file())

    # Pasta que nao segue o padrao de nome de aquisicao: `pasta_do_caso`
    # devolve ela mesma, e o relatorio ia parar DENTRO do que foi selado.
    avulsa = raiz / "pasta_fora_do_padrao"
    avulsa.mkdir()
    (avulsa / "dado.txt").write_text("x", encoding="utf-8")
    gerar_manifesto(avulsa)
    documento_avulso = relatorio_extracao_service.gerar(avulsa)
    checar("pasta fora do padrao: o relatorio NAO e gravado dentro dela",
           not documento_avulso.erro
           and avulsa.resolve() not in documento_avulso.caminho.resolve().parents)
    checar("e ela continua integra", conferir_manifesto(avulsa).integro)

    # -----------------------------------------------------------------------
    print("\n[2] Laudo Pericial: tres origens que nao se confundem")
    # -----------------------------------------------------------------------
    protocolos = [(c, p, "Sim", "") for c, p in laudo_service.perguntas_dos_protocolos()]
    laudo = laudo_service.gerar(
        primeira,
        {"numero": "007/2026", "objetivo": "Verificar comunicacoes.", "protocolos": protocolos,
         "tipo_extracao": "Logica", "consideracoes": "Consideracao propria do examinador."},
        {"nome": "Beltrano Subscritor", "funcao": "Perito"},
    )
    checar("o laudo e gerado sem erro", not laudo.erro and laudo.caminho.is_file())
    checar("fica fora da aquisicao, que segue integra",
           laudo.caminho.parent.resolve() == (caso / "documentos").resolve()
           and conferir_manifesto(primeira).integro)
    texto, _ = ler_pdf(laudo.caminho)
    checar("traz o numero e o objetivo declarados",
           "007/2026" in texto and "Verificar comunicacoes." in texto)
    checar("distingue o operador da aquisicao de quem subscreve",
           "Fulana Examinadora" in texto and "Beltrano Subscritor" in texto)
    checar("as consideracoes entram como declaracao do examinador",
           "Considerações do examinador" in texto and "Consideracao propria" in texto)
    checar("o selo consta do laudo", selo in texto)
    checar("o laudo tambem traz os arquivos por categoria",
           "Arquivos adquiridos, por categoria" in texto and "media/contrato.pdf" in texto)
    # A coluna da resposta e estreita, e a frase quebra de linha no PDF.
    checar("item que pede especificacao e veio sem ela e DITO",
           "não especificado" in " ".join(texto.split()))

    sem_dados = laudo_service.gerar(primeira, {}, {})
    texto, _ = ler_pdf(sem_dados.caminho)
    checar("sem objetivo, o laudo DIZ que nao foi informado",
           "não informou o objetivo" in texto)
    checar("sem perfil, o laudo diz que o subscritor nao esta declarado",
           "perfil do examinador não preenchido" in texto)
    checar("sem respostas, os protocolos constam como nao respondidos",
           "não foram respondidos" in texto)

    # -----------------------------------------------------------------------
    print("\n[3] Conversa volumosa: indice no PDF, integra no CSV, PDF das escolhidas")
    # -----------------------------------------------------------------------
    from services.conversas_service import gerar_pdf_conversas, listar_conversas  # noqa: E402
    from services.extraction_service import ExtractionService  # noqa: E402
    from services.relatorio_service import LIMITE_INTEGRA_NO_PDF, RelatorioService  # noqa: E402

    volumosa = criar_pasta_aquisicao(raiz, "CASO_301", "Android", datetime(2026, 9, 5, 10, 0, 0))
    (volumosa / "sms").mkdir()
    linhas_sms = []
    for indice in range(LIMITE_INTEGRA_NO_PDF + 50):
        numero = "11911112222" if indice % 2 else "11933334444"
        linhas_sms.append(
            f"Row: {indice} _id={indice}, address={numero}, date={1756000000000 + indice * 1000}, "
            f"type=1, read=1, body=mensagem numero {indice}"
        )
    linhas_sms.append("Row: 999 _id=999, address=11955556666, date=1756999999000, type=2, "
                      "read=1, body=conversa curta e unica")
    (volumosa / "sms" / "sms_todas.txt").write_text("\n".join(linhas_sms) + "\n", encoding="utf-8")
    gerar_manifesto(volumosa)

    conteudo = RelatorioService.gerar(volumosa)
    texto_pdf, paginas_pdf = ler_pdf(next(
        a for a in conteudo.arquivos_gerados if str(a).endswith(".pdf")))
    checar("acima do limite, o PDF de conteudo traz o INDICE das conversas",
           "ÍNDICE" in texto_pdf and "3 conversa(s)" in " ".join(texto_pdf.split()))
    checar("e nao a integra (a mensagem do meio nao aparece no PDF)",
           "mensagem numero 150" not in texto_pdf)
    checar("o PDF fica curto", paginas_pdf <= 3)
    csv = (conteudo.pasta / "sms.csv").read_text(encoding="utf-8")
    checar("a integra continua na planilha", "mensagem numero 150" in csv)

    conversas, _ = listar_conversas(volumosa)
    checar("a lista de conversas tem as tres, da maior para a menor",
           [c.quantidade for c in conversas] == [175, 175, 1])
    unica = next(c for c in conversas if c.chave == "11955556666")
    escolhido = gerar_pdf_conversas(volumosa, [(unica.artefato, unica.chave)])
    checar("o PDF das conversas escolhidas e gerado",
           not escolhido.erro and escolhido.caminho.is_file())
    texto_escolhido, _ = ler_pdf(escolhido.caminho)
    checar("ele traz a conversa escolhida, com a origem da mensagem",
           "conversa curta e unica" in texto_escolhido and "linha" in texto_escolhido)
    checar("e so ela", "mensagem numero 1" not in texto_escolhido)
    checar("e diz que a escolha foi do examinador",
           "ESCOLHIDAS pelo examinador" in " ".join(texto_escolhido.split()))
    checar("fica fora da aquisicao, que continua integra",
           volumosa.resolve() not in escolhido.caminho.resolve().parents
           and conferir_manifesto(volumosa).integro)
    checar("sem nada selecionado, recusa dizendo por que",
           "Nenhuma conversa" in gerar_pdf_conversas(volumosa, []).erro)

    # -----------------------------------------------------------------------
    print("\n[4] O Relatorio de Extracao so sai pelo botao")
    # -----------------------------------------------------------------------
    checar("a extracao nao emite mais o relatorio sozinha",
           not hasattr(ExtractionService, "_gerar_relatorio_de_extracao"))

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for nome in falhas:
        print("  - " + nome)
    sys.exit(1)
print("Todos os testes passaram.")
