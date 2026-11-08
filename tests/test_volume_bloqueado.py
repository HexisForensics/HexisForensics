"""
Testes do diagnostico de volume que o Windows nao consegue ler.

Nasceu de uma pergunta de procedimento: se o metodo de aquisicao e retirar
o disco da maquina apreendida e liga-lo a estacao, o que acontece quando
esse disco esta cifrado com BitLocker? A resposta, pelo codigo de entao:
`GetVolumeInformationW` falha, `GetDiskFreeSpaceExW` falha, e as duas
funcoes tratavam falha devolvendo vazio e zero. O examinador via

    E:\\  --  (sem rotulo)  [Fixo (interno)]  0.0 GB livres de 0.0 GB

e nada mais. Nem uma palavra dizendo que o volume esta bloqueado. A pior
leitura possivel dessa tela -- "o pendrive esta com defeito" -- era tambem
a mais natural.

O diagnostico corrige isso, e a linha que estes testes guardam e a de
sempre: **so afirma BitLocker quem leu a assinatura**. Ler o primeiro
setor exige Administrador, e a suite pode estar rodando sem ele; nesse
caso o estado e INDETERMINADO e a tela diz isso, em vez de escolher entre
duas afirmacoes que ela nao pode sustentar.

O leitor de assinatura e injetavel exatamente para estes testes existirem:
sem isso, o caminho do BitLocker so seria exercitado no dia em que um
disco cifrado de verdade fosse periciado -- ou seja, valendo laudo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.computador.disk_client import (  # noqa: E402
    ASSINATURA_BITLOCKER,
    BLOQUEIO_BITLOCKER,
    BLOQUEIO_ILEGIVEL,
    BLOQUEIO_INDETERMINADO,
    BLOQUEIO_NENHUM,
    ERRO_ACESSO_NEGADO,
    UnidadeDisco,
    descrever_bloqueio,
    diagnosticar_bloqueio,
)

falhas = []


def checar(nome, condicao):
    print(("  OK   " if condicao else " FALHA ") + nome)
    if not condicao:
        falhas.append(nome)


def montar(bloqueio, oem_id="", codigo_erro=ERRO_ACESSO_NEGADO):
    return UnidadeDisco(
        letra="E",
        caminho="E:\\",
        tipo_codigo=3,
        tipo_descricao="Fixo (interno)",
        codigo_erro_volume=codigo_erro,
        oem_id=oem_id,
        bloqueio=bloqueio,
    )


print("\n[1] Volume que responde normalmente nao e investigado")

bloqueio, oem = diagnosticar_bloqueio("C", 0, leitor=lambda _: "NAO DEVIA SER LIDO")
checar("sem erro, nao ha bloqueio", bloqueio == BLOQUEIO_NENHUM)
checar("e o volume nao chega a ser aberto em modo bruto", oem == "")


print("\n[2] Assinatura lida: BitLocker afirmado com lastro")

bloqueio, oem = diagnosticar_bloqueio(
    "E", ERRO_ACESSO_NEGADO, leitor=lambda _: ASSINATURA_BITLOCKER
)
checar("assinatura -FVE-FS- e reconhecida", bloqueio == BLOQUEIO_BITLOCKER)
checar("e a assinatura lida fica registrada", oem == ASSINATURA_BITLOCKER)

frase = descrever_bloqueio(montar(BLOQUEIO_BITLOCKER, ASSINATURA_BITLOCKER))
checar("a frase nomeia o BitLocker", "BitLocker" in frase)
checar(
    "diz que a imagem e adquirivel mesmo assim",
    "adquirível" in frase and "íntegra" in frase,
)
checar(
    "e avisa que o TPM ficou na maquina de origem",
    "TPM" in frase and "placa-mãe" in frase,
)


print("\n[3] Sem privilegio, o estado e INDETERMINADO -- nunca 'nao e BitLocker'")

bloqueio, oem = diagnosticar_bloqueio("E", ERRO_ACESSO_NEGADO, leitor=lambda _: None)
checar("leitor que nao abre o volume gera INDETERMINADO", bloqueio == BLOQUEIO_INDETERMINADO)
checar("sem assinatura inventada", oem == "")

frase = descrever_bloqueio(montar(BLOQUEIO_INDETERMINADO))
# A palavra "BitLocker" PODE aparecer -- a frase diz que rodar como
# Administrador permitiria saber SE e BitLocker. O que nao pode aparecer e
# a afirmacao, que e a abertura da frase do estado confirmado.
checar("a frase menciona a hipotese", "BitLocker" in frase)
checar(
    "mas NAO afirma que o volume esta cifrado",
    "Volume cifrado com BitLocker" not in frase,
)
checar("declara que a causa permanece indeterminada", "indeterminado" in frase)
checar("e diz o que fazer para saber", "Administrador" in frase)
checar("o codigo de erro do Windows aparece", str(ERRO_ACESSO_NEGADO) in frase)


print("\n[4] Assinatura lida e diferente: ilegivel, e nao BitLocker")

bloqueio, oem = diagnosticar_bloqueio(
    "E", ERRO_ACESSO_NEGADO, leitor=lambda _: "NTFS    "
)
checar("outra assinatura nao vira BitLocker", bloqueio == BLOQUEIO_ILEGIVEL)

frase = descrever_bloqueio(montar(BLOQUEIO_ILEGIVEL, "NTFS    "))
checar("a frase mostra o que foi lido", "NTFS" in frase)
checar("e nega explicitamente a assinatura do BitLocker", "não é a assinatura" in frase)


print("\n[5] Os quatro estados sao distintos, e o normal e silencioso")

estados = {BLOQUEIO_NENHUM, BLOQUEIO_BITLOCKER, BLOQUEIO_INDETERMINADO, BLOQUEIO_ILEGIVEL}
checar("quatro estados distintos", len(estados) == 4)
checar("volume normal nao gera frase nenhuma", descrever_bloqueio(montar(BLOQUEIO_NENHUM, codigo_erro=0)) == "")


print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S): {falhas}"))
sys.exit(1 if falhas else 0)
