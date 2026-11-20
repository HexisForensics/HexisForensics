# Validação da ferramenta — Hexis Forensics

## Objeto e método deste documento

A ABNT NBR ISO/IEC 27037 exige que a evidência digital seja tratada de modo
**repetível** e **reprodutível**, e a ISO/IEC 27041 estabelece que a adequação
de um método se demonstra por **validação** — a verificação documentada de que
a ferramenta e o procedimento cumprem os requisitos a que se propõem. Este
documento é o registro dessa validação para a Hexis Forensics.

Para cada módulo declara-se: a **função** a que se propõe, o **procedimento de
teste** empregado, o **resultado** observado e a **configuração** (aparelho e
versão de sistema) em que o caminho foi exercido. Cada linha corresponde a uma
verificação automatizada executável, de modo que o resultado não dependa de
declaração, mas de **reprodução independente**. A suíte reúne 85 arquivos de
teste, executados a cada alteração do código.

A cobertura é **por versão de sistema, não por modelo** (ver
[APARELHOS_TESTADOS.md](APARELHOS_TESTADOS.md)). Onde a validação se limita ao
ensaio automatizado ou ao emulador, isso é declarado: nenhuma afirmação excede
o que foi verificado.

*Executar a suíte completa:* `py tests/rodar_todos.py`.

---

## Fundamentos transversais

### Lacre por hash (integridade)

**Função:** calcular o SHA-256 de cada arquivo no momento da aquisição e
permitir conferir a integridade a qualquer tempo.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Registrar o hash de cada arquivo, com caminho relativo | Ler o manifesto de volta de uma aquisição selada | Os caminhos são relativos e os valores são SHA-256; o cabeçalho não é confundido com entrada |
| Reconhecer material intocado como íntegro | Conferir uma aquisição não alterada | Todos os arquivos constam como intactos; pasta sem manifesto devolve resultado nulo, nunca "íntegro" presumido |

**Configuração:** selado em toda aquisição real (A22/Android 13, A33/Android 16,
iPhone 11/iOS 18.6.2, pendrive/Windows 11) e coberto por ensaio automatizado.
**Reproduzir:** `py tests/test_cadeia_custodia.py`.

### A conferência não altera o lacre

**Função:** verificar a integridade sem tocar no material selado.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Não modificar nenhum arquivo ao conferir | Conferir e comparar antes/depois | Nenhum arquivo selado mudou de conteúdo |
| Não poluir o registro do procedimento | Inspecionar o registro após a conferência | O registro não recebeu anotação da conferência |

**Configuração:** ensaio automatizado. **Reproduzir:**
`py tests/test_conferencia_nao_altera_lacre.py`.

### Protocolos periciais (ISO/IEC 27037)

**Função:** registrar, sob o selo, as respostas aos requisitos periciais da
norma.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Verificar os oito requisitos da norma | Gerar os protocolos de uma aquisição | Auditabilidade (5.3.2), repetibilidade e reprodutibilidade (5.3.3/5.3.4), relógio aferido (6.6), cadeia de custódia (6.1) e integridade selada (5.4.5) são conferidos |
| Nunca omitir um requisito | Gerar os protocolos sem registro prévio | Mesmo sem registro, todos os requisitos aparecem — a ausência de resposta é declarada, não escondida |

**Configuração:** ensaio automatizado; selado em toda aquisição. **Reproduzir:**
`py tests/test_protocolos.py`.

---

## Android

### Estado do aparelho ao ser recebido

**Função:** registrar o aparelho como chegou — captura de tela, energia,
bloqueio, bateria, aplicativo em primeiro plano e perfis.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Registrar o estado e preservar a captura com hash | Rodar o módulo sobre um aparelho de teste | O estado é registrado; a imagem é gravada e o seu SHA-256 fica ao lado |
| Declarar o que não pôde ser obtido | Simular a ausência de `exec-out` | A captura não é tentada, mas o restante do estado continua sendo coletado — a limitação é declarada |

**Configuração:** Samsung A33 (Android 16); ensaio automatizado.
**Reproduzir:** `py tests/test_estado_e_bugreport.py`.

### Características técnicas do dispositivo

**Função:** ler as propriedades do sistema (getprop) e gerar o relatório técnico.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Nunca declarar sucesso sem dado | Rodar com `getprop` vazio | O resultado é **FALHA**, com o motivo devolvido pelo ADB; nenhum relatório em prosa nem ficha estruturada é gravado |
| Preservar a tentativa, mesmo falha | Inspecionar a saída de um módulo que falhou | A tentativa (stderr) fica preservada como evidência |

**Configuração:** Samsung A33 (Android 16), A22 (Android 13).
**Reproduzir:** `py tests/test_caracteristicas_e_mms.py`.

### Mensagens SMS / MMS

**Função:** consultar as mensagens que o Android entrega e, em aparelhos
antigos, a via alternativa de backup.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Ler as mensagens com data e número de origem | Semear mensagens conhecidas e rodar o módulo | Saem com data correta e linha de origem; a data em milissegundos não vai para 1970 |
| Nunca transformar recusa em "não há mensagens" | Simular o Android negando o acesso | Registra **RECUSADO** com o motivo; a explicação fala em *recusa*, não em *ausência* |
| Nunca declarar sucesso sem dado | Rodar o cenário em que tudo foi recusado | O resultado é **FALHA**, nunca "concluído" |

**Configuração:** A22 (Android 13), A33 (Android 16), Emulador Android 13.
**Reproduzir:** `py tests/test_agente_android.py`,
`py tests/test_backup_do_sistema.py`.

### Contatos e histórico de chamadas

**Função:** obter agenda e chamadas pelos provedores do Android ou pelo
aplicativo agente.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Dizer o que veio de cada fonte, sem inventar | Rodar o agente e ler a saída | A mensagem conta o que veio de cada fonte; chamada sem nome diz que o nome não consta, sem inventá-lo; sentido e duração são interpretados |
| Registrar e justificar a alteração no aparelho | Instalar e desinstalar o agente | Instalar e desinstalar são registrados como **ALTERAÇÃO**; a desinstalação é conferida; o SHA-256 do APK empregado entra na aquisição |

**Configuração:** A22 (Android 13, agente), A33 (Android 16, contatos e chamadas).
**Reproduzir:** `py tests/test_agente_android.py`.

### Backup lógico (cópia de mídias)

**Função:** copiar pastas de mídia e metadados do armazenamento compartilhado,
com hash por arquivo.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Só declarar sucesso se copiou algo | Simular ADB respondendo "código 0" sem nenhum arquivo | **Não** é sucesso — pasta vazia com código 0 nunca vira "concluído" |
| Preservar a data original e relatar o progresso fielmente | Copiar com acompanhamento | A flag `-a` preserva a data de modificação; o progresso é repassado, não retrocede e termina em 100% |

**Configuração:** A22 (Android 13), Emulador Android 13. **Reproduzir:**
`py tests/test_pull_auditavel.py`.

### WhatsApp — decifragem do backup (.crypt15)

**Função:** decifrar o backup local do WhatsApp com a chave de 64 dígitos,
autenticando o resultado.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Aceitar a chave em formatos usuais e recusar entradas inválidas com clareza | Informar a chave com espaços, hífens e quebras; depois com um dígito a menos e com caractere inválido | Formatos usuais aceitos; um dígito a menos é recusado **dizendo quantos** foram digitados; caractere fora de 0-9/a-f é recusado **nomeando** o caractere |
| Entregar exatamente o banco original e nada mais | Decifrar com a chave certa | Devolve exatamente o banco original |
| Recusar qualquer alteração (chave ou arquivo) | Trocar um dígito da chave; depois alterar um byte do arquivo | Em ambos os casos **nada** é devolvido, e a recusa fala em conferência de autenticidade |

**Configuração:** A22 (Android 13), Emulador Android 13, iPhone 11 (WhatsApp);
ensaio automatizado sobre banco real. **Reproduzir:**
`py tests/test_whatsapp_crypt15.py`.

### Extração física (bit a bit)

**Função:** clonar a partição de dados por `dd`, com SHA-256 durante a aquisição.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Nunca apresentar imagem parcial como completa | Simular imagem de 0 byte e imagem truncada | Ambas são **FALHA** explícita, com a mensagem explicando que nada foi transmitido ou que a imagem está incompleta |
| Produzir uma imagem fiel e autenticada | Executar a clonagem completa | Retorna sucesso; o hash confere com o SHA-256 real, o sidecar `.sha256` é gravado e os bytes são idênticos à origem, sem corrupção |
| Tratar a falta de privilégio como falha, não como vazio | Simular acesso negado | É **FALHA** explícita — nunca uma imagem silenciosamente incompleta |

**Configuração:** Emulador Android 13 (privilégio elevado); ensaio automatizado.
**Reproduzir:** `py tests/test_extracao_fisica.py`.

---

## iPhone

### Backup, decifragem e leitura (iOS)

**Função:** fazer o backup local (comum ou cifrado), decifrá-lo quando houver
senha e interpretar mensagens, agenda, WhatsApp e fotos.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Converter datas do iOS corretamente | Ler datas em segundos (base 2001) e nanossegundos | Ambas viram a data certa; o valor zero **não** vira 01/01/2001 |
| Recuperar o texto real da mensagem | Ler mensagens armazenadas em `attributedBody` | O texto é recuperado, inclusive texto longo |
| Identificar a origem sem confundir plataformas | Ler uma aquisição de iPhone | É reconhecida como de iPhone; saem os quatro artefatos do iPhone e os locais das fotos, e nenhum do Android |

**Configuração:** iPhone 11 (iOS 18.6.2) — backup comum e cifrado com decifragem,
mensagens, agenda, WhatsApp e fotos. **Reproduzir:** `py tests/test_ios.py`.

---

## Computador

### Imagem do volume (bit a bit)

**Função:** gerar imagem bit a bit do volume, com SHA-256 e conferência de
tamanho.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Nunca apresentar leitura incompleta como imagem | Simular 0 byte, imagem maior que o volume e imagem com metade do volume | Todas são **FALHA**, com o motivo (inclusive: byte a mais não pertence ao volume) |
| Aceitar a margem real do dispositivo, declarando-a | Imagem dentro da margem de 99% | É sucesso, porém **com ressalva declarada** |

**Configuração:** Pendrive (Windows 11); ensaio automatizado. **Reproduzir:**
`py tests/test_computador_conclusoes.py`.

### Volume bloqueado (BitLocker)

**Função:** reconhecer um volume cifrado por BitLocker antes de tentar lê-lo em
modo bruto.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Reconhecer o BitLocker pela assinatura, sem inventar | Ler a assinatura `-FVE-FS-` | É reconhecida, registrada e a frase nomeia o BitLocker; sem assinatura, nada é inventado |
| Declarar incerteza quando não consegue abrir | Simular leitor que não abre o volume | Gera **INDETERMINADO** e a frase menciona a hipótese, sem afirmar além do verificado |

**Configuração:** ensaio automatizado. **Pendência honesta:** ainda não
exercido sobre um volume BitLocker real. **Reproduzir:**
`py tests/test_volume_bloqueado.py`.

---

## Leitura, relatórios e documentos

### Ficha do Aparelho

**Função:** gerar a capa de leitura rápida da aquisição, cada campo citando a
fonte selada.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Mostrar o obtido, citando a fonte selada | Gerar a ficha de uma aquisição de teste | Bloqueio, IMEI, número e ICCID aparecem apontando o arquivo selado de origem |
| Declarar o não obtido, sem presumir | Deixar campos que a coleta não alcançou | Saem como **NÃO APURADO**, e a ficha diz que NÃO APURADO ≠ ausência no aparelho |
| Ser documento lacrado e não reescrever emissão anterior | Gerar a ficha e reemiti-la | Cada página leva o SHA-256 do manifesto no rodapé; fica fora da aquisição, que permanece íntegra; a reemissão não apaga a anterior |

**Configuração:** os dados que a ficha lê foram exercidos no A33 (Android 16) e
A22 (Android 13). **Pendência honesta:** a validação visual da ficha em
**aparelho real** ainda não foi feita. **Reproduzir:**
`py tests/test_ficha_do_aparelho.py`.

### Localização das fotos

**Função:** ler as coordenadas GPS do EXIF das imagens e situá-las, sem inventar
precisão.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Ler coordenadas com o sinal correto e a hora na origem certa | Ler o EXIF de um JPEG e de um HEIC | Latitude/longitude com sinal (sul e oeste negativos); a hora do GPS em UTC e a data pelo relógio do aparelho, sem fuso inventado; link para o mapa |
| Não inventar localização onde não há | Ler foto sem GPS e foto com coordenada 0,0 | Foto sem GPS fica sem localização e sem problema; a coordenada 0,0 (GPS sem sinal) não vira local |

**Configuração:** prática no emulador e ensaio automatizado. **Pendência
honesta:** validação em aparelho real ainda não registrada. **Reproduzir:**
`py tests/test_locais_das_fotos.py`.

### Relatório de conteúdo

**Função:** interpretar o material adquirido em planilhas e PDF, com a
procedência de cada registro.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Interpretar todo o material, registrando a procedência | Gerar o relatório de uma aquisição de teste | Gera sem erro, com os totais corretos e nada por interpretar; planilhas de SMS e chamadas e o PDF são produzidos, cada registro com a procedência gravada |
| Não produzir conteúdo para o que foi recusado | Incluir um artefato recusado | Não há planilha para o artefato recusado — o vazio não é apresentado como dado |

**Configuração:** ensaio automatizado e prática no emulador. **Reproduzir:**
`py tests/test_relatorio_conteudo.py`.

### Entrega de material

**Função:** exportar material selecionado com recibo, preservando a integridade.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Entregar cópia idêntica, conferida contra o lacre | Entregar uma pasta e comparar | Cada cópia tem o mesmo SHA-256 do original e o material diz que confere com o lacre, preservando o caminho |
| Documentar a entrega sem tocar na aquisição | Gerar os recibos | Recibo em texto (finalidade, examinador e hashes) e em PDF (lista e assinaturas); a entrega vira complemento do caso e a aquisição não é tocada |

**Configuração:** ensaio automatizado. **Reproduzir:**
`py tests/test_entrega.py`.

### Relógio do aparelho

**Função:** medir e registrar o desvio do relógio do aparelho em relação à
estação, sob o selo.

| O que promete | Procedimento de teste | Resultado |
|---|---|---|
| Medir o desvio e lê-lo de volta do registro selado | Registrar e reler o desvio | O desvio é medido, descrito por extenso e lido de volta do registro; grande desvio gera alerta de que as datas estão deslocadas |

**Configuração:** Samsung Galaxy A22 real (desvio de 539 dias observado em caso
concreto) e ensaio automatizado. **Reproduzir:**
`py tests/test_relogio_do_aparelho.py`.

---

*A lista completa de aparelhos provados está em*
[APARELHOS_TESTADOS.md](APARELHOS_TESTADOS.md).
*O método de cada módulo e suas limitações estão na*
[Apostila do Usuário](Apostila_Hexis_Forensics.pdf).
