"""
Extração física (clonagem bit-a-bit) da partição `userdata` via `dd`.

Migrado de `7_extracao_fisica.py` e revisado quanto a três pontos que
comprometiam a validade pericial do resultado:

1. **Canal binário.** A versão anterior transmitia a imagem por
   `adb shell`, que é um canal de texto: em várias combinações de versão
   de ADB e sistema operacional, ele traduz quebras de linha no fluxo de
   saída (0x0A vira 0x0D 0x0A). Numa imagem bit-a-bit isso é corrupção
   silenciosa — o arquivo fica com tamanho plausível e conteúdo alterado.
   Agora a transmissão usa `adb exec-out`, que não faz tradução alguma.

2. **Verificação real do resultado.** A versão anterior devolvia sucesso
   sempre que o stderr não continha "Permission denied" — inclusive com
   imagem de zero byte. Agora o resultado depende do código de saída do
   processo, da quantidade de bytes efetivamente gravados e, quando o
   tamanho da partição é conhecido, da comparação com o esperado.

3. **Hash no ato da aquisição.** O SHA-256 é calculado sobre os bytes no
   momento em que chegam do dispositivo, e não numa releitura posterior
   do arquivo. O valor é gravado em `<imagem>.sha256`, ao lado da imagem,
   antes de qualquer outro processamento.

Uma limitação permanece e é registrada de propósito: sem root não há
acesso de leitura à partição, e nenhuma técnica deste módulo contorna
isso — o resultado, nesse caso, é uma falha explícita, não uma imagem
parcial apresentada como completa.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from core.base_extractor import Perfil, ResultadoExtracao
from core.hashing import EscritorComHash, gravar_hash_avulso
from core.registry import registrar_extrator

from .base import AndroidExtractor

# Caminhos onde a partição `userdata` costuma estar exposta, em ordem de
# probabilidade. Varia por fabricante e por geração de chipset, por isso a
# resolução é feita no dispositivo, e não presumida pelo código.
CAMINHOS_USERDATA = (
    "/dev/block/bootdevice/by-name/userdata",
    "/dev/block/by-name/userdata",
    "/dev/block/platform/*/by-name/userdata",
    "/dev/block/mapper/userdata",
)

NOME_IMAGEM = "imagem_fisica_userdata.img"
TAMANHO_BLOCO_DD = 4096
MARGEM_TOLERANCIA = 0.99  # imagem aceitável a partir de 99% do tamanho esperado


@registrar_extrator
class ExtracaoFisicaExtractor(AndroidExtractor):
    id = "android_extracao_fisica"
    nome_exibicao = "Extração Física (Bit-a-Bit)"
    ordem = 70
    descricao = (
        "Clonagem bit-a-bit da partição 'userdata' via 'dd', transmitida por canal "
        "binário e com SHA-256 calculado durante a aquisição. Requer privilégios de "
        "root ou hardware legado vulnerável."
    )
    requer_privilegio_root = True

    # ------------------------------------------------------------------
    # Resolução da partição no dispositivo
    # ------------------------------------------------------------------
    limitacoes_conhecidas = (
        "Exige privilégio elevado no aparelho. Sem ele não há leitura da "
        "partição, e o resultado é falha explícita — nunca uma imagem parcial "
        "apresentada como completa.",
        "A imagem é da partição de dados do usuário, não do armazenamento "
        "inteiro do aparelho.",
        "A imagem preserva o que a partição continha no momento da coleta. "
        "Extração física não é sinônimo de recuperação integral: dado que o "
        "sistema de arquivos já sobrescreveu não é recuperado por ela.",
    )
    perfil_minimo = Perfil.DES

    def _resolver_particao(self) -> Optional[str]:
        """
        Descobre, no próprio dispositivo, qual dos caminhos conhecidos de
        `userdata` existe de fato. Retorna None se nenhum for encontrado.
        """
        for caminho in CAMINHOS_USERDATA:
            saida = self.adb.executar(["shell", f"ls {caminho} 2>/dev/null"])
            if not saida or "No such file" in saida or "not found" in saida.lower():
                continue
            # Com curinga, `ls` pode devolver mais de uma linha; a primeira serve.
            resolvido = saida.strip().splitlines()[0].strip()
            if resolvido:
                return resolvido
        return None

    def _obter_tamanho_particao(self, caminho_particao: str) -> Optional[int]:
        """
        Tenta obter o tamanho da partição em bytes, para permitir barra de
        progresso real e conferência do tamanho final. Best effort: em
        dispositivo sem root a leitura pode ser negada, e nesse caso a
        extração prossegue sem verificação de tamanho (registrada como
        ressalva no resultado).
        """
        for comando in (
            f"blockdev --getsize64 {caminho_particao}",
            f"stat -c %s {caminho_particao}",
        ):
            saida = (self.adb.executar(["shell", comando]) or "").strip()
            if not saida:
                continue
            # A saída válida é apenas o número. Qualquer outra coisa (stack
            # trace, "Permission denied", mensagem de uso) é descartada em
            # vez de garimpada por regex: um número extraído do meio de uma
            # mensagem de erro seria pior que não ter número nenhum.
            primeira_linha = saida.splitlines()[0].strip()
            if primeira_linha.isdigit():
                valor = int(primeira_linha)
                if valor > 0:
                    return valor
        return None

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    def executar(self, pasta_caso: Path) -> ResultadoExtracao:
        self.definir_idioma_do_selo(pasta_caso)
        pasta_fisica = pasta_caso / "physical"
        pasta_fisica.mkdir(parents=True, exist_ok=True)
        caminho_imagem = pasta_fisica / NOME_IMAGEM

        self.log(self._t("lg_px_localizando"))
        caminho_particao = self._resolver_particao()
        if not caminho_particao:
            self.log(self._t("lg_falha", valor=self._t("lg_px_sem_particao_log")))
            return ResultadoExtracao(
                False,
                self._t("lg_px_sem_particao_msg"),
            )
        self.log(self._t("lg_px_localizada", caminho=caminho_particao))

        tamanho_esperado = self._obter_tamanho_particao(caminho_particao)
        if tamanho_esperado:
            self.log(self._t("lg_px_tamanho", valor=self._formatar(tamanho_esperado)))
        else:
            self.log(self._t("lg_ressalva", valor=self._t("lg_px_sem_tamanho")))

        if not self.adb.suporta_exec_out():
            self.log(self._t("lg_falha", valor=self._t("lg_px_sem_execout_log")))
            return ResultadoExtracao(
                False,
                self._t("lg_px_sem_execout_msg"),
            )

        # Sonda antes de transmitir gigabytes: um bloco de 512 bytes diz se
        # há acesso à partição e, quando não há, traz o motivo por extenso.
        # Aqui o stderr é bem-vindo no fluxo — é diagnóstico, não evidência.
        acessivel, diagnostico = self._sondar_particao(caminho_particao)
        if not acessivel:
            self.log(self._t("lg_falha",
                             valor=self._t("lg_px_nao_lida_log", diagnostico=diagnostico)))
            if "Permission denied" in diagnostico or "not permitted" in diagnostico:
                self.log(self._t("lg_px_bloqueio"))
                return ResultadoExtracao(
                    False,
                    self._t("lg_px_negada_msg"),
                    caminho_saida=pasta_fisica,
                    detalhes={"stderr": diagnostico},
                )
            return ResultadoExtracao(
                False,
                self._t("lg_px_nao_lida_msg", caminho=caminho_particao,
                        diagnostico=diagnostico or self._t("lg_px_sem_mensagem")),
                caminho_saida=pasta_fisica,
                detalhes={"stderr": diagnostico},
            )

        self.log(self._t("lg_px_iniciando"))
        self.log(self._t("lg_px_sha_calculando"))

        # `2>/dev/null` NO APARELHO é o que mantém a imagem limpa. O
        # `exec-out` funde o stderr do comando remoto no fluxo binário, e o
        # `dd` escreve seu resumo ("N records in/out, X bytes copied") ao
        # terminar — 97 bytes de texto que ficavam colados no fim da imagem,
        # arruinando a cópia bit-a-bit e o hash junto com ela.
        #
        # Nada de evidência se perde: o resumo do `dd` é diagnóstico do
        # próprio comando, e os fatos que importam — bytes transmitidos e
        # código de saída — são apurados pela ferramenta, não lidos daquele
        # texto. O motivo de uma falha de acesso vem da sonda acima.
        comando_dd = f"dd if={caminho_particao} bs={TAMANHO_BLOCO_DD} 2>/dev/null"

        try:
            with open(caminho_imagem, "wb") as arquivo_saida:
                escritor = EscritorComHash(arquivo_saida)
                ultimo_percentual = -1

                def ao_receber_bloco(bloco: bytes) -> None:
                    nonlocal ultimo_percentual
                    escritor.escrever(bloco)
                    if tamanho_esperado:
                        percentual = min(99, int(escritor.bytes_gravados / tamanho_esperado * 100))
                        if percentual != ultimo_percentual:
                            ultimo_percentual = percentual
                            self.progresso(percentual)

                resultado_stream = self.adb.stream_binario(
                    ["exec-out", comando_dd],
                    ao_receber_bloco,
                    cancelado=lambda: self.cancelado,
                )
        except OSError as exc:
            return ResultadoExtracao(
                False, self._t("lg_px_falha_escrita", exc=exc)
            )

        bytes_gravados = escritor.bytes_gravados
        hash_imagem = escritor.hash_hex

        # --- Cancelamento pelo operador -------------------------------
        if resultado_stream.cancelado:
            self.log(self._t("lg_px_cancelado_log", valor=self._formatar(bytes_gravados)))
            return ResultadoExtracao(
                False,
                self._t("lg_px_cancelado_msg", valor=self._formatar(bytes_gravados)),
                caminho_saida=caminho_imagem,
                detalhes={"incompleta": True, "bytes": bytes_gravados},
            )

        # A recusa de acesso é detectada pela sonda, ANTES da transmissão:
        # com o stderr do `dd` silenciado, ela não chegaria mais até aqui.
        stderr = resultado_stream.stderr

        # --- Nenhum byte gravado --------------------------------------
        if bytes_gravados == 0:
            self.log(self._t("lg_falha", valor=self._t(
                "lg_px_zero_log", valor=stderr or self._t("lg_px_vazia"))))
            return ResultadoExtracao(
                False,
                self._t("lg_px_zero_msg", valor=stderr or self._t("lg_px_sem_erro")),
                caminho_saida=caminho_imagem,
                detalhes={"bytes": 0, "stderr": stderr},
            )

        # --- Erro reportado pelo processo -----------------------------
        if resultado_stream.codigo_saida != 0:
            self.log(self._t("lg_falha", valor=self._t(
                "lg_px_codigo_log", codigo=resultado_stream.codigo_saida,
                valor=self._formatar(bytes_gravados))))
            return ResultadoExtracao(
                False,
                self._t("lg_px_codigo_msg", codigo=resultado_stream.codigo_saida,
                        valor=self._formatar(bytes_gravados),
                        stderr=stderr or self._t("lg_px_sem_mensagem")),
                caminho_saida=caminho_imagem,
                detalhes={"incompleta": True, "bytes": bytes_gravados, "stderr": stderr},
            )

        # --- Hash gravado antes de qualquer conclusão -----------------
        caminho_hash = gravar_hash_avulso(caminho_imagem, hash_imagem)
        self.log(self._t("lg_px_sha_imagem", hash=hash_imagem))
        self.log(self._t("lg_px_hash_gravado", nome=caminho_hash.name))

        # --- Conferência de completude --------------------------------
        completa, ressalva = self._conferir_tamanho(bytes_gravados, tamanho_esperado)
        self.progresso(100)

        if not completa:
            self.log(self._t("lg_ressalva", valor=ressalva))
            return ResultadoExtracao(
                False,
                ressalva,
                caminho_saida=caminho_imagem,
                detalhes={
                    "incompleta": True,
                    "bytes": bytes_gravados,
                    "esperado": tamanho_esperado,
                    "sha256": hash_imagem,
                },
            )

        mensagem = self._t("lg_px_msg_ok", valor=self._formatar(bytes_gravados), hash=hash_imagem)
        if ressalva:
            mensagem += self._t("lg_px_ress_sep", ressalva=ressalva)
            self.log(self._t("lg_ressalva", valor=ressalva))

        self.log(self._t("lg_concluido", valor=self._t("lg_px_concluido")))
        return ResultadoExtracao(
            True,
            mensagem,
            caminho_saida=caminho_imagem,
            detalhes={
                "bytes": bytes_gravados,
                "esperado": tamanho_esperado,
                "sha256": hash_imagem,
                "particao": caminho_particao,
            },
        )

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------
    def _sondar_particao(self, caminho_particao: str) -> Tuple[bool, str]:
        """
        Lê um único bloco de 512 bytes para saber se a partição é legível.

        Existe por dois motivos. O primeiro é não descobrir só depois de
        horas de transmissão que o acesso estava negado. O segundo é o
        diagnóstico: como a cópia real silencia o stderr do `dd` para não
        contaminar a imagem, é aqui que o motivo de uma recusa é capturado
        — em 512 bytes que nunca entram na evidência.
        """
        pedacos: list = []
        try:
            resultado = self.adb.stream_binario(
                ["exec-out", f"dd if={caminho_particao} bs=512 count=1"],
                pedacos.append,
            )
        except OSError as exc:
            return False, str(exc)

        recebido = b"".join(pedacos)
        # Com o stderr fundido no fluxo, uma recusa vem como texto no lugar
        # dos bytes da partição.
        texto = recebido.decode("utf-8", errors="replace")
        if resultado.codigo_saida != 0 or len(recebido) < 512:
            return False, (texto + " " + (resultado.stderr or "")).strip()
        return True, ""

    def _conferir_tamanho(self, gravados: int, esperado: Optional[int]) -> Tuple[bool, str]:
        """
        Compara o que foi gravado com o tamanho declarado da partição.

        Retorna (completa, ressalva). Sem tamanho esperado, a aquisição não
        pode ser declarada completa nem incompleta — segue como completa
        com ressalva explícita, para que o operador saiba exatamente o que
        foi e o que não foi verificado.
        """
        if not esperado:
            return True, self._t("lg_px_tam_nao_obtido")

        if gravados == esperado:
            return True, ""

        # Excesso é sempre fatal, e a assimetria com a falta é deliberada:
        # imagem MENOR pode vir de um tamanho declarado impreciso pelo
        # dispositivo, mas imagem MAIOR só pode vir de bytes que não são da
        # partição.
        if gravados > esperado:
            excedente = gravados - esperado
            return False, self._t("lg_px_tam_maior", gravados=self._formatar(gravados),
                                   esperado=self._formatar(esperado), excedente=excedente)

        proporcao = gravados / esperado
        if proporcao >= MARGEM_TOLERANCIA:
            return True, self._t("lg_px_tam_margem", proporcao=f"{proporcao:.2%}")

        return False, self._t("lg_px_tam_incompleta", proporcao=f"{proporcao:.2%}",
                              gravados=self._formatar(gravados), esperado=self._formatar(esperado))

    @staticmethod
    def _formatar(bytes_totais: int) -> str:
        """Converte bytes para a maior unidade legível (KB, MB, GB)."""
        valor = float(bytes_totais)
        for unidade in ("B", "KB", "MB", "GB", "TB"):
            if valor < 1024:
                return f"{int(valor)} B" if unidade == "B" else f"{valor:.2f} {unidade}"
            valor /= 1024
        return f"{valor:.2f} PB"
