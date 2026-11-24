# Aparelhos testados — Hexis Forensics

Este é o **registro completo** dos aparelhos em que a ferramenta foi
efetivamente provada. A apostila e o README trazem apenas uma **amostra**
de âncoras; a lista exaustiva vive aqui, para crescer sem inchar a
documentação.

Um princípio orienta a leitura desta tabela: **a cobertura é por versão de
sistema, não por modelo.** O caminho de aquisição depende do Android/iOS e
do nível de API, não da marca do aparelho — um modelo bem escolhido por
faixa de versão prova mais que uma dezena de modelos da mesma faixa. Por
isso, *"outros modelos tendem a funcionar pelo mesmo caminho, mas não foram
verificados"*: a ausência de um modelo aqui **não** significa que ele não
funcione, apenas que não foi conferido.

Nada nesta tabela é afirmado além do que foi verificado. A coluna **O que
foi verificado** diz o alcance de cada teste — um aparelho pode ter passado
só pelo caminho ADB não-interativo, e não por todos os módulos.

## Android

| Aparelho | Sistema | Quando | O que foi verificado |
|---|---|---|---|
| Motorola moto x4 | Android 9 | validação v1.0 | Fluxo de extração de rotina por ADB |
| Samsung Galaxy A22 | Android 13 (One UI 5.1) | validação v1.0 | Extração completa, aplicativo agente e WhatsApp |
| Samsung Galaxy A33 (SM-A336M) | Android 16 (One UI 8) | 14/11/2026 | Caminho ADB não-interativo: estado inicial, características técnicas, identificação/contas, contatos e chamadas, SMS/MMS. Selado com manifesto. IMEI restrito pelo shell e 1 parte de anexo MMS não lida — ambos **declarados** (não é falha). WhatsApp, dump de arquivos e físico não foram exercidos neste teste. |
| Xiaomi Redmi 12C (2212ARNC4L) | Android 14 | 24/11/2026 | Primeiro Xiaomi. Aquisição por ADB: estado inicial, características técnicas, backup lógico de mídia, artefatos do sistema, bugreport, contatos/chamadas, SMS/MMS, APKs e dump de arquivos. Selado com manifesto. Aparelho **sem chip e sem conta**: SIM ausente e nenhuma conta foram **verificados** (achado, não falha). IMEI restrito pelo shell (Android 14) — **declarado**. Sem root: WhatsApp e conteúdo de `/data` fora de alcance. Este primeiro Xiaomi **revelou e corrigiu um defeito da Identificação** (ausência verificada de SIM/conta era reportada como "acesso negado"); a correção (`dbefa4a`) foi **reexercida em nova aquisição no mesmo aparelho**, com a Identificação saindo como ressalva honesta (SIM ausente e nenhuma conta como achados; IMEI como campo não apurado) e a Ficha do Aparelho gerada a partir dela. **Aplicativo agente: instalação bloqueada pelo MIUI** (`INSTALL_FAILED_USER_RESTRICTED` mesmo com todos os interruptores e chip; ROM nega `-g`/`pm grant`) — ver Limitações. |
| Emulador Android (privilégio elevado) | Android 13 | validação v1.0 | Módulos que exigem privilégio elevado e WhatsApp |

## iPhone

| Aparelho | Sistema | Quando | O que foi verificado |
|---|---|---|---|
| iPhone 11 | iOS 18.6.2 | validação v1.0 | Backup local comum e cifrado (com decifragem), mensagens, agenda, WhatsApp e fotos |

## Mídias de armazenamento

| Mídia | Sistema | Quando | O que foi verificado |
|---|---|---|---|
| Pendrive USB | Windows 11 | validação v1.0 | Cópia lógica, artefatos do Windows e imagem do volume, com bloqueador de escrita |

## Limitações conhecidas

- **Xiaomi, Redmi e POCO** — o caminho de aquisição por ADB foi verificado
  no **Redmi 12C (Android 14)** em 24/11/2026. O **aplicativo agente** (a via
  para contatos/SMS/chamadas em Android 12+) **não instala** nesses aparelhos
  pelo caminho ADB sancionado: o MIUI/HyperOS recusa a instalação por USB com
  `INSTALL_FAILED_USER_RESTRICTED` **mesmo** com "Instalar via USB" e
  "Depuração USB (configurações de segurança)" ligadas, conta Mi logada e chip
  inserido; a ROM ainda nega o flag `-g` (conceder permissões) e o `pm grant`.
  Instalar só seria possível **burlando o guard de segurança do aparelho** — o
  que a ferramenta **não** faz. É **limitação declarada** do agente em Xiaomi
  moderno; nesses aparelhos, usa-se o **caminho ADB padrão** (que foi validado).
- **Android 8 ou anterior** — fora do escopo desta versão.

---

*Como ler:* a presença de um aparelho aqui é prova de que aquele caminho foi
exercido naquele sistema; a ausência é só ausência de teste. O método da
ferramenta e as limitações de cada módulo estão na
[Apostila do Usuário](Apostila_Hexis_Forensics.pdf).
