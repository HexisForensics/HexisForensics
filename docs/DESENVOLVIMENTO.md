<p align="center"><img src="../assets/marca/logo_claro.png" alt="Hexis Forensics" width="420"></p>

# Hexis Forensics — documentação técnica

> Para quem vai **programar** ou auditar a ferramenta. Para baixar e usar, veja o [README](../README.md) e a apostila.

Ferramenta com interface gráfica (PySide6) para **aquisição e preservação
de evidência digital** de dispositivos **Android**, de **mídias de
armazenamento** (discos, pendrives) e, futuramente, **iOS**, orientada
pela ABNT NBR ISO/IEC 27037.

O que ela faz, em uma frase cada:

- **adquire** o material com hash calculado na aquisição e sela a pasta
  com um manifesto SHA-256;
- **registra** quem executou, em que estação, com que método, o que foi
  alterado no dispositivo e o que cada módulo obteve ou deixou de obter;
- **interpreta** agenda, chamadas, SMS/MMS, WhatsApp e e-mail, sempre
  sobre cópia, com a procedência de cada registro;
- **documenta**: Relatório de Extração e Laudo Pericial em PDF.

A regra que organiza tudo: **a ferramenta nunca afirma o que não
verificou.** Ausência de dado no material adquirido não autoriza concluir
ausência do dado no dispositivo, e um módulo que não obteve nada nunca
declara sucesso.

O projeto é dividido em três camadas — `core/`, `services/` e `ui/` — e a
identidade visual é configurável por perfil.

ÍNDICE
1. AS TRÊS CAMADAS: CORE, SERVICES, UI
2. REQUISITOS E INSTALAÇÃO
3. ESTRUTURA DO PROJETO
4. IDENTIDADE VISUAL (BRANDING)
5. PREPARAÇÃO DO DISPOSITIVO ALVO (ANDROID)
6. USANDO A INTERFACE GRÁFICA
7. IDENTIFICAÇÃO DO CASO E NOMENCLATURA DAS PASTAS
8. TIPOS DE EXTRAÇÃO DISPONÍVEIS (ANDROID)
9. SUPORTE A iOS (STATUS ATUAL)
10. COMO ADICIONAR UM NOVO TIPO DE EXTRAÇÃO
11. CADEIA DE CUSTÓDIA (MANIFESTO DE HASHES)
12. INTEGRIDADE E AUDITABILIDADE (ISO/IEC 27037)
13. TESTES AUTOMATIZADOS
14. DOCUMENTOS: RELATÓRIO DE EXTRAÇÃO, LAUDO PERICIAL, RELATÓRIO DE CONTEÚDO
15. INSTALADOR E PASTA PORTÁTIL

-------------------------------------------------------------------------------
## 1. AS TRÊS CAMADAS: CORE, SERVICES, UI
-------------------------------------------------------------------------------
A regra é simples e vale para qualquer código novo que for adicionado:
**a UI nunca importa `core` diretamente** (com uma única exceção
documentada, ver seção 10). Toda comunicação passa por `services/`.

```
 ui/  ──chama──▶  services/  ──chama──▶  core/
(PySide6,        (orquestração,        (regras de negócio de
 sem regra de     QThread, config)      extração, sem Qt)
 negócio)
```

- **`core/`** — o que é comum à extração (contrato `BaseExtractor`,
  registro automático de extratores, gestão de pastas de caso, geração de
  hashes, log em arquivo) e o que é específico de cada plataforma
  (`core/android/`, `core/ios/`). Nenhum arquivo aqui importa PySide6.
  Pode, no futuro, virar a base de uma CLI ou de testes automatizados sem
  arrastar nenhuma dependência de interface.
- **`services/`** — a camada de orquestração. É aqui que mora tudo que
  não é "regra de negócio pura" nem "widget": execução em `QThread`
  (`ExtractionService`, `HashService`), fachadas que escondem detalhes
  internos do core da UI (`DeviceService`, `CaseService`), e resolução de
  configuração de aplicação (`branding_service`, que carrega a identidade
  visual). É a única camada que conhece tanto `core` quanto conceitos de
  execução assíncrona do Qt (`QThread`), mas não conhece nenhum widget.
- **`ui/`** — apresentação pura (PySide6): janelas, diálogos, painéis.
  Só fala com `services/`. A cor, o logo e o nome exibidos vêm de fora
  (`BrandConfig`), nunca hardcoded nos widgets.

-------------------------------------------------------------------------------
## 2. REQUISITOS E INSTALAÇÃO
-------------------------------------------------------------------------------
**Para usar**, há o instalador e a pasta portátil — ver a seção 15. Nenhum
dos dois exige Python instalado na máquina.

**Para rodar do código-fonte:**

1. Instale o Python 3.10 ou superior (Windows: marque "Add python.exe to
   PATH" durante a instalação — https://www.python.org/downloads/).
2. Instale as dependências do projeto:
   ```
   pip install -r requirements.txt
   ```
3. Baixe o **Android SDK Platform Tools** (contém `adb.exe`) em
   https://developer.android.com/tools/releases/platform-tools e copie o
   conteúdo extraído para a pasta `binario/`. Alternativamente, se o
   `adb` já estiver no PATH do sistema, a suíte o localiza automaticamente.
4. Execute a aplicação:
   ```
   python main.py
   ```

-------------------------------------------------------------------------------
## 3. ESTRUTURA DO PROJETO
-------------------------------------------------------------------------------
```text
HexisForensics/
├── main.py                        # Carrega o branding, aplica o tema e abre a MainWindow
├── requirements.txt
├── .gitignore
├── empacotar.py                   # Gera a pasta portátil e o instalador
├── agente_android/                # Código-fonte do aplicativo agente (Java) e sua compilação
├── assets/agente/                 # O APK do agente, com o SHA-256 ao lado
├── instalador/                    # Script do Inno Setup
├── assets/marca/                  # Logo e ícone (SVG é a fonte; PNG/ICO derivados)
├── ferramentas/gerar_marca.py     # Regenera PNG/ICO a partir dos SVG
├── binario/                       # adb.exe e DLLs de vínculo USB (Windows)
├── extracoes/                     # Criada automaticamente com os resultados
├── branding/                      # IDENTIDADE VISUAL — um perfil por cliente/empresa
│   ├── active.json                # Qual perfil está em uso: {"perfil": "default"}
│   ├── default/
│   │   └── branding.json          # nome, cores, logo/ícone (opcionais)
│   └── exemplo_empresa/
│       └── branding.json          # exemplo de uma paleta diferente
├── core/                          # CORE: regras de negócio de extração, sem Qt
│   ├── base_extractor.py          # Contrato comum (BaseExtractor)
│   ├── registry.py                # Registro + descoberta automática de extratores
│   ├── case.py                    # Nomenclatura, registro do caso (caso.json) e cadeia de custódia
│   ├── operador.py                # Perfil do examinador e operador de cada aquisição
│   ├── hashing.py                 # SHA-256: manifesto do caso e hash durante a gravação
│   ├── logger.py                  # Logs por caso: extracao.log (tudo) e erros/erros.log (só falhas/ressalvas)
│   ├── versao.py                  # Versão da suíte e ambiente da estação (repetibilidade)
│   ├── procedimento.py            # registro_procedimento.txt: ambiente, relógio, decisões, alterações
│   ├── android/                   # adb_client.py, device.py, extractors/ (11 módulos)
│   ├── computador/                # disk_client.py, device.py, extractors/ (4 módulos)
│   └── ios/                       # client.py, device.py, extractors/ (4 stubs)
├── services/                      # SERVICE: orquestração entre core e ui
│   ├── branding_service.py        # BrandConfig + carregar_branding() + obter_perfil_ativo()
│   ├── device_service.py          # DeviceService (fachada única sobre AndroidDevice/IOSDevice)
│   ├── case_service.py            # CaseService (sugerir/abrir caso, sanitização p/ preview)
│   ├── extraction_service.py      # listar_extratores() + ExtractionService (QThread)
│   ├── hash_service.py            # listar_pastas_extracao() + HashService (QThread)
│   ├── perfil_service.py          # Perfil do examinador gravado na estação
│   ├── dossie_service.py          # Leitura única dos registros de uma aquisição
│   ├── identidade_pdf.py          # Logo, estilos, tabelas e rodapé de todo PDF
│   ├── blocos_pdf.py              # Blocos comuns ao relatório e ao laudo
│   ├── relatorio_extracao_service.py  # Relatório de Extração (PDF, automático)
│   ├── laudo_service.py           # Laudo Pericial (PDF)
│   ├── relatorio_service.py       # Relatório de Conteúdo (CSV + PDF + HTML)
│   └── decifragem_service.py      # Decifragem do backup do WhatsApp (crypt15)
├── ui/                            # UI: apresentação pura (PySide6)
│   ├── style.py                   # Constrói QPalette/stylesheet a partir de um BrandConfig
│   ├── main_window.py             # Janela principal (sidebar + páginas Android/Armazenamento)
│   └── widgets/
│       ├── sidebar.py             # Menu lateral: logo/nome da marca + navegação
│       ├── case_dialog.py         # Diálogo de identificação do caso
│       ├── device_panel.py        # Painel de status de conexão
│       ├── extraction_panel.py    # Checkboxes + coluna de status (sucesso/parcial/falha) por módulo
│       ├── log_console.py         # Console de log em tempo real
│       └── hash_dialog.py         # Diálogo de geração do manifesto de hashes
└── tests/                         # Testes automatizados (ver seção 13)
    └── rodar_todos.py             # Executa a suíte inteira
```

Nenhum artefato de cache (`__pycache__/`, `*.pyc`) é versionado ou
distribuído — veja `.gitignore`. Dois logs são persistidos por caso,
propositalmente, para reforçar a cadeia de custódia:
`<pasta_do_caso>/extracao.log` (tudo — todo módulo, sucesso ou falha) e
`<pasta_do_caso>/erros/erros.log` (só os módulos que falharam ou tiveram
alguma ressalva, ex.: acesso negado a um provider).

-------------------------------------------------------------------------------
## 4. IDENTIDADE VISUAL (BRANDING)
-------------------------------------------------------------------------------
Cada cliente/empresa pode ter sua própria identidade visual sem duplicar
nenhum código de UI. Um perfil de marca é uma pasta em `branding/<nome>/`
com um `branding.json`:

```json
{
  "nome_exibicao": "Nome da Empresa",
  "modo": "dark",
  "cores": {
    "fundo": "#1b1e23",
    "fundo_alt": "#22262d",
    "fundo_entrada": "#12151a",
    "texto": "#e2e6ea",
    "texto_secundario": "#9aa4af",
    "destaque": "#3f8dfd",
    "borda": "#333a42",
    "texto_sobre_destaque": "#0b0d10"
  },
  "logo": "logo.png",
  "icone": "icone.ico"
}
```

- `logo` e `icone` são opcionais e relativos à própria pasta do perfil
  (ex.: coloque `logo.png` dentro de `branding/minha_empresa/` junto do
  `branding.json`). Se o arquivo não existir, a UI simplesmente não
  mostra logo/ícone — nunca quebra a inicialização.
- `destaque` é a cor de ênfase (botões em foco, item da sidebar
  selecionado, barra de progresso). As demais definem o esquema de
  fundo/texto.
- Cores de status (verde = conectado, âmbar = aguardando autorização,
  vermelho = erro) são propositalmente fixas e não fazem parte do
  branding — comunicam estado, não identidade de marca.

**Para trocar de identidade visual**, edite `branding/active.json` e
aponte o campo `"perfil"` para o nome da pasta desejada:

```json
{
  "perfil": "exemplo_empresa"
}
```

Salve o arquivo e reabra a aplicação — não é necessário definir nenhuma
variável de ambiente, nem reinstalar nada. Se o perfil indicado não
existir, ou se `branding/active.json` estiver ausente/malformado, a
aplicação cai de volta para `default` automaticamente — a inicialização
nunca falha por causa de branding ausente ou malformado.

Para gerar uma build de marca branca para um novo cliente: crie
`branding/<nome_do_cliente>/branding.json` (copie o de `default` como
ponto de partida), coloque `logo.png`/`icone.ico` na mesma pasta se
quiser, e aponte `branding/active.json` para esse nome.

-------------------------------------------------------------------------------
## 5. PREPARAÇÃO DO DISPOSITIVO ALVO (ANDROID)
-------------------------------------------------------------------------------
1. Vá em Configurações > Sobre o Telefone.
2. Pressione "Número da Versão" (ou "Número de Compilação") 7 vezes até
   ativar o modo de desenvolvedor.
3. Volte ao menu anterior, acesse "Opções do Desenvolvedor".
4. Ative a chave "Depuração USB".
5. Conecte o dispositivo ao computador via cabo de dados homologado.
6. Na UI, clique em "Verificar Conexão" na página Android (menu lateral);
   se o status for "unauthorized", olhe a tela do celular e autorize a
   depuração USB marcando "Sempre permitir deste computador".

-------------------------------------------------------------------------------
## 6. USANDO A INTERFACE GRÁFICA
-------------------------------------------------------------------------------
A navegação é por **menu lateral** (sidebar), com o logo e o nome do
perfil de marca ativo no topo esquerdo: "MENU PRINCIPAL" leva às páginas
de plataforma (Android e Armazenamento) e "FERRAMENTAS" reúne as ações auxiliares
(cadeia de custódia, abrir pasta de extrações, sobre).

1. Execute `python main.py` (ou abra pelo atalho, na cópia instalada).
   A suíte não tem tela de acesso. No início de **cada extração** ela
   pergunta quem é o examinador: escolhe-se um dos cadastrados na estação
   ou cadastra-se um novo (nome, registro profissional e
   instituição). O escolhido é gravado na aquisição, sob o selo, como
   *declaração* do operador, ao lado da conta do Windows em uso.
2. Na sidebar, clique em "🤖 Android" ou "💾 Armazenamento" para abrir a página da
   plataforma desejada.
3. Clique em "Verificar Conexão" e confirme que o dispositivo está
   conectado e autorizado.
4. Marque os tipos de extração desejados na lista (todos vêm marcados por
   padrão, exceto os que exigem root). Cada linha tem, à direita, uma
   coluna de **status** (· Pendente / ⏳ Em execução / ✔ Sucesso /
   ⚠ Parcial / ✖ Falha) — passe o mouse sobre o status para ver a
   mensagem completa daquele módulo.
5. Clique em "▶ Iniciar Extração". A suíte mostra o alcance e as
   limitações dos módulos escolhidos, pede o **caso** (novo, já sugerindo o
   próximo número, ou existente, para mais um dispositivo), o documento de
   **autorização** (opcional; a ausência fica registrada) e os dados da
   **peça**, com o número do lacre.
6. O console mostra o andamento de cada módulo em tempo real; a barra de
   progresso reflete o módulo em execução, e a coluna de status de cada
   módulo é atualizada ao vivo. Esse painel de execução fica sempre
   visível, abaixo da página de plataforma selecionada.
   "⚠ Parcial" indica sucesso com ressalva (ex.: o provider negou acesso
   a uma parte dos dados, mas a tentativa foi preservada como evidência) —
   vale a pena checar o console ou `erros/erros.log` nesse caso.
7. Ao final, os arquivos ficam em
   `extracoes/<identificador_caso>/<plataforma>_<timestamp>/`, incluindo a
   subpasta `erros/` com o resumo de qualquer módulo que não teve sucesso
   pleno. Cada nova extração do mesmo caso cria uma pasta de aquisição
   própria, e nunca sobrescreve a anterior.
8. Ao fim de cada aquisição a pasta é selada com o manifesto de hashes e
   o **Relatório de Extração** em PDF é emitido no gerenciador de casos (seção 14).
9. Na sidebar, em **FERRAMENTAS**: **🔐 Cadeia de Custódia** confere ou
   gera manifestos; **📂 Casos e Documentos** abre o gerenciador de casos,
   de onde saem o Laudo Pericial, o Relatório de Conteúdo, a decifragem
   do backup do WhatsApp e as retificações.

-------------------------------------------------------------------------------
## 7. IDENTIFICAÇÃO DO CASO E NOMENCLATURA DAS PASTAS
-------------------------------------------------------------------------------
Um **caso é um projeto** e reúne várias aquisições — dois telefones e um
disco do mesmo exame, ou o mesmo aparelho coletado em datas diferentes.
Por isso a estrutura tem dois níveis:

```text
extracoes/
└── CASO_001/                       <- o caso (projeto)
    ├── caso.json                   <- registro do caso: referência, descrição, solicitante
    ├── android_20260822_152249/    <- uma aquisição (um dispositivo, um lacre)
    ├── android_20260823_094010/    <- outro telefone, no mesmo caso
    ├── computador_20260823_101500/ <- aquisição de outra plataforma
    ├── fundamento/                 <- documentos de autorização, com hash
    ├── complementos/               <- retificações e juntadas posteriores
    ├── documentos/                 <- PDFs gerados (fora das pastas seladas)
    ├── relatorios/                 <- relatórios de conteúdo
    └── decifrados/                 <- banco do WhatsApp decifrado (fora do selo)
```

**Dados do caso e dados do dispositivo moram em lugares diferentes.** O
que descreve o caso é preenchido uma vez, na abertura, e fica em
`caso.json`; o que descreve a peça — equipamento, cor, estado e o
**número do lacre** — fica em `cadeia_custodia.txt`, dentro de cada
aquisição. São exigidos o lacre e **duas fotografias da peça**. Para acrescentar um
segundo dispositivo, escolha **Caso Existente** ao iniciar a extração:
nada do caso é perguntado de novo, e a nova aquisição herda o que já está
gravado. Retificar um dado depois nunca reescreve aquisição selada: entra
como complemento, com o valor anterior.

A pasta do **caso** é reaproveitada; a pasta da **aquisição**, nunca. Se
duas coletas caírem no mesmo segundo, um sufixo numérico garante destinos
distintos.

Isso não é organização estética. Duas coletas gravadas na mesma pasta
sobrescrevem arquivos, misturam evidência de origens possivelmente
distintas e produzem um manifesto de hashes que cobre a mistura sem que
nada indique que houve duas aquisições.

A sugestão automática (`CaseService.sugerir_identificador`, que usa
`core.case.sugerir_proximo_identificador`) varre as pastas já existentes
em `extracoes/`, identifica o maior número usado no padrão `CASO_NNN_` e
sugere `NNN + 1`. O identificador é livre — pode ser substituído por
qualquer texto (ex.: número do processo, nome do solicitante). O
identificador do dispositivo (serial ADB, UDID) não entra no nome da
pasta, mas é registrado em `informacoes_caso.txt`, dentro da própria
pasta do caso.

-------------------------------------------------------------------------------
## 8. TIPOS DE EXTRAÇÃO DISPONÍVEIS (ANDROID)
-------------------------------------------------------------------------------
- **Estado do Aparelho ao Ser Recebido** — captura de tela, estado de
  energia e de bloqueio, bateria, aplicativo em primeiro plano e perfis de
  usuário. **Execute primeiro**: qualquer outra coleta pode acender a tela
  ou trazer um aplicativo para frente, e o estado registrado depois disso já
  não é o estado em que o dispositivo chegou.
- **Características Técnicas** — fabricante, modelo, versão do Android,
  patch de segurança, status da bateria.
- **Identificação do Aparelho e Contas** — IMEI (por várias vias, com
  validação do dígito verificador pelo algoritmo de Luhn) e contas
  cadastradas no aparelho (Google, WhatsApp, Telegram). É o que vincula o
  dispositivo físico a uma pessoa. A partir do Android 10 o sistema pode
  recusar a leitura do IMEI ao shell; nesse caso a recusa é registrada como
  ressalva, com a saída bruta de cada tentativa preservada.
- **Artefatos de Atividade do Sistema** — linha do tempo de uso por
  aplicativo (`usagestats`), redes Wi-Fi conhecidas, notificações, histórico
  de bateria, processos e permissões concedidas. Responde *quando* o
  aparelho foi usado e *por qual* aplicativo. **São dados voláteis**:
  execute este módulo no início do exame, pois reiniciar o aparelho descarta
  parte do conteúdo.
- **Backup Lógico** — DCIM, Download, Pictures, Movies, Music + getprop e
  lista de pacotes instalados.
- **Relatório de Diagnóstico (bugreport)** — histórico de energia com
  marcações de tela ligada, estatísticas de uso, eventos do sistema,
  conectividade, pacotes com data de instalação e `logcat` retido. É o
  artefato mais denso disponível sem root e o que melhor sustenta uma linha
  do tempo de uso. Leva de um a vários minutos.
- **Contatos e Histórico de Chamadas** — via content providers nativos.
- **SMS/MMS** — via `content://sms` (todas, recebidas, enviadas,
  rascunhos). Em versões recentes do Android sem root, o provider pode
  negar o acesso (`Permission Denial`); isso fica registrado nos arquivos
  gerados como evidência da tentativa.
- **Agenda, Chamadas e SMS por aplicativo agente** *(sem root, qualquer
  versão do Android; altera o dispositivo; seleção expressa)* — a via do
  **Android 12 em diante**, onde o backup do sistema não existe. Instala no
  aparelho o agente da suíte (`agente_android/`, cerca de 12 KB), que pede
  só permissões de LEITURA e nenhuma de rede, lê agenda, chamadas, SMS e
  MMS, e é desinstalado ao final. Regras que o código sustenta: o APK
  empregado entra na aquisição com o SHA-256; a desinstalação é tentada
  sempre; agente que ficou instalado é **falha**, mesmo com os dados em
  mãos; e fonte que o sistema recusou ao agente vira ressalva, nunca
  "nenhum registro". O código-fonte do agente está no repositório e é
  recompilável com `py agente_android/compilar.py`. **Provado em hardware**:
  moto x4 (Android 9) e emulador com Android 13.
- **WhatsApp** *(best effort sem root)* — mídia e backups locais
  criptografados (`.crypt12/14/15`) acessíveis no armazenamento externo.
  O banco de mensagens ativo (`msgstore.db`) e a chave de criptografia
  ficam em área privada do app e exigem root — não são extraídos por
  este módulo.
- **WhatsApp — backup com chave de 64 dígitos** *(sem root, qualquer versão
  do Android)* — não é um módulo de aquisição, e sim um procedimento: o
  examinador ativa no WhatsApp do aparelho o backup criptografado de ponta
  a ponta **com chave de 64 dígitos** e manda fazer o backup; o módulo acima
  copia o `msgstore.db.crypt15`; e, no gerenciador de casos, **Decifrar
  backup do WhatsApp** o abre com a chave (`core/whatsapp_crypt15.py`,
  AES-256-GCM). A conferência de autenticidade é o que sustenta o resultado:
  chave errada ou arquivo alterado não devolvem nada. O banco em claro fica
  em `<caso>/decifrados/`, fora do selo, com a procedência que o liga ao
  arquivo cifrado, e a decifragem é registrada como complemento, com a
  chave. Passo a passo no `MANUAL.md`. **Provado contra backup real** em
  12/10/2026: moto x4, Android 9, WhatsApp 2.26.39.79 — decifrado e
  autenticado na primeira tentativa, e lido pelo leitor de mensagens. Falta
  repetir em outros fabricantes e versões.
- **WhatsApp — Mensagens por substituição temporária do aplicativo**
  *(sem root; altera o dispositivo; seleção expressa)* — o `adb backup` do
  WhatsApp atual devolve só o manifesto do pacote. Este módulo desinstala o
  aplicativo **preservando os dados**, instala uma versão antiga que entrega
  a área privada ao backup, tira o backup e reinstala o original. Regras que
  o código sustenta: nada é tocado antes de os APKs originais estarem
  copiados e conferidos na estação; a reinstalação é tentada sempre; e
  aparelho que não voltou à versão original é **falha**, mesmo com o banco
  em mãos. O APK antigo não acompanha a suíte: o examinador o coloca em
  `binario/whatsapp_legado.apk`, e o SHA-256 dele entra na aquisição. Só
  vale abaixo do Android 12. **Ainda não foi executado contra aparelho
  real** — os testes usam um aparelho simulado.
- **Outros Mensageiros** *(best effort sem root)* — Telegram, TelegramX,
  Signal, Instagram, Messenger, Facebook, Snapchat e Threema. Mesma
  limitação do WhatsApp: alcança apenas o que o aplicativo grava em
  armazenamento externo. O relatório gerado separa três situações que não
  podem ser confundidas — não instalado, instalado sem mídia externa, e
  acesso recusado pelo sistema.
- **Dump do Sistema de Arquivos** — `/data/data` e `/sdcard` via `adb pull`.
  Sem root, `/data/data` é recusado pelo Android: isso é registrado como
  ressalva e como decisão metodológica fundamentada, nunca como sucesso.
- **APKs dos Aplicativos Instalados** — copia o `.apk` de cada aplicativo
  instalado pelo usuário, com SHA-256, permitindo identificar aplicativo
  adulterado ou malicioso e submetê-lo a análise posterior.
- **Extração Física** *(requer root)* — clonagem bit-a-bit da partição
  `userdata` via `dd`.

-------------------------------------------------------------------------------
## 9. SUPORTE A iOS (STATUS ATUAL)
-------------------------------------------------------------------------------
O pacote `core/ios/` já possui a mesma estrutura hierárquica do
`core/android/`, mas ainda **não implementa comunicação real** com o
dispositivo. A página iOS aparece na sidebar normalmente, porém qualquer
tentativa de extração retorna uma mensagem explicando que o módulo está
em desenvolvimento.

A implementação futura deve envolver `pymobiledevice3` (biblioteca Python
pura) e/ou `libimobiledevice` (`idevice_id`, `ideviceinfo`,
`idevicebackup2`) para detectar/confiar no dispositivo e gerar um backup
local (protocolo `mobilebackup2`), de onde a maioria dos dados pode ser
extraída. Como `core/` e `services/`/`ui/` já são agnósticos de
plataforma, essa implementação fica inteiramente dentro de `core/ios/`.

-------------------------------------------------------------------------------
## 10. COMO ADICIONAR UM NOVO TIPO DE EXTRAÇÃO
-------------------------------------------------------------------------------
1. Crie um arquivo em `core/android/extractors/` (ou `core/ios/extractors/`),
   com uma classe que herde de `AndroidExtractor` (ou `IOSExtractor`).
2. Decore a classe com `@registrar_extrator` (de `core.registry`), defina
   `id`, `nome_exibicao`, `descricao`, `ordem` e implemente `executar()`.
3. Pronto — nenhum outro arquivo precisa ser tocado. `services.extraction_service.listar_extratores()`
   descobre o módulo automaticamente e a UI passa a exibi-lo como um novo
   checkbox.

Exemplo mínimo (`core/android/extractors/telegram.py`):
```python
from core.base_extractor import ResultadoExtracao
from core.registry import registrar_extrator
from .base import AndroidExtractor

@registrar_extrator
class TelegramExtractor(AndroidExtractor):
    id = "android_telegram"
    nome_exibicao = "Telegram"
    descricao = "Extração de dados do Telegram (best effort, sem root)."
    ordem = 55

    def executar(self, pasta_caso):
        ...
        return ResultadoExtracao(True, "Concluído.")
```

Nota de arquitetura: `ui/widgets/extraction_panel.py` importa o tipo
`core.base_extractor.BaseExtractor` apenas para anotação (id,
nome_exibicao, descricao, ordem) — é a única exceção aceita à regra "UI
não importa core", pois criar um DTO à parte só para isso agregaria
complexidade sem benefício real.

-------------------------------------------------------------------------------
## 11. CADEIA DE CUSTÓDIA (MANIFESTO DE HASHES)
-------------------------------------------------------------------------------
O manifesto `manifesto_hashes.txt` é gerado **automaticamente ao final de
toda extração**, como último ato — depois dele, nada mais é escrito na pasta
do caso, nem o log nem o registro do procedimento. Essa ordem é parte da
cadeia de custódia: qualquer linha gravada após o cálculo tornaria o próprio
caso divergente do seu selo.

### Conferir é mais importante do que gerar

Gerar um hash prova pouco. O que sustenta a cadeia de custódia é poder
demonstrar, **depois**, que o material não mudou entre a coleta e o exame.
Em **FERRAMENTAS → 🔐 Cadeia de Custódia**, a ação principal é **Conferir**:
recalcula tudo e confronta com o manifesto, separando quatro situações que
sustentam afirmações diferentes no exame:

| Situação | O que significa |
|---|---|
| **Íntegro** | o arquivo é idêntico ao que foi selado |
| **ALTERADO** | o conteúdo mudou depois da coleta |
| **AUSENTE** | constava do manifesto e não está mais na pasta |
| **ACRESCENTADO** | está na pasta e não constava do manifesto |

Cada conferência grava seu próprio relatório datado na pasta e uma entrada
no registro do procedimento. Nenhuma apaga a anterior — o histórico de
conferências é parte do registro.

**Gerar nunca sobrescreve.** Se a pasta já tem manifesto, o original é
preservado e o novo é gravado com data e hora no nome. A razão é direta: se
um arquivo tiver sido alterado, regravar por cima faria o manifesto passar a
refletir o estado adulterado, e a prova da alteração seria destruída pelo
próprio ato de "reforçar a cadeia de custódia".

Além disso, cada módulo calcula o SHA-256 dos arquivos **no momento da
aquisição** e grava o resultado em `<pasta_do_caso>/aquisicao/`, junto do
relatório de reconciliação (ver seção 12).

A geração manual continua disponível, para regerar o manifesto ou gerá-lo
sobre uma pasta antiga: na sidebar, em **FERRAMENTAS → 🔐 Cadeia de
Custódia**, selecione a pasta e clique em "Gerar Manifesto".

Qualquer alteração posterior em qualquer arquivo extraído quebrará a
validação com o manifesto, garantindo o controle rigoroso da cadeia de
custódia.

-------------------------------------------------------------------------------
## 12. INTEGRIDADE E AUDITABILIDADE (ISO/IEC 27037)
-------------------------------------------------------------------------------
A suíte segue a **ISO/IEC 27037** (identificação, coleta, aquisição e
preservação de evidência digital). A norma impõe quatro requisitos de
processo, e cada um tem uma contrapartida concreta no que a ferramenta
grava dentro da pasta do caso:

| Requisito | O que a ferramenta grava |
|---|---|
| **Auditabilidade** | `extracao.log` (tudo) e `erros/erros.log` (falhas e ressalvas) |
| **Repetibilidade** | `registro_procedimento.txt`: versão da suíte, do Python, do ADB, sistema e estação |
| **Reprodutibilidade** | `manifesto_hashes.txt` e os hashes por módulo em `aquisicao/` |
| **Justificabilidade** | decisões metodológicas e alterações no aparelho, em `registro_procedimento.txt` |

### O que cada arquivo do caso significa

```text
CASO_001/android_20260822_143012/
├── informacoes_caso.txt        # Caso, plataforma, dispositivo, abertura
├── registro_procedimento.txt   # Diário de bordo (ver abaixo)
├── extracao.log                # Toda linha de execução de todo módulo
├── manifesto_hashes.txt        # SHA-256 de cada arquivo do caso (automático)
├── erros/erros.log             # Só o que falhou ou teve ressalva
├── aquisicao/                  # Prova de integridade e completude por módulo
│   ├── midia_Camera.sha256              # Hash no momento da aquisição
│   └── midia_Camera_reconciliacao.txt   # Origem × destino, e o que faltou
└── <pastas de evidência>       # O material extraído do aparelho
```

O `registro_procedimento.txt` é **append-only** e responde às perguntas que
nenhum log técnico cobre:

- **Ambiente** — em que condições o exame foi feito.
- **Aferição de relógio** — o relógio do aparelho confrontado com o da
  estação, com o desvio medido. Sem isso, os carimbos de tempo dos
  artefatos extraídos ficam sem âncora.
- **Decisões metodológicas** — por que este método foi adotado e não outro.
  Ex.: *"extração de /data/data não realizada; o Android recusou o acesso
  sem privilégio elevado"*. Registrada como decisão fundamentada, e não
  como uma falha perdida no log.
- **Alterações no dispositivo examinado** — ativar a Depuração USB,
  autorizar a chave RSA da estação e confirmar um `adb backup` na tela
  **modificam o aparelho periciado**. A norma admite a alteração quando
  inevitável para a aquisição, mas exige que seja registrada e justificada.

### Garantias que o código sustenta

- **Sucesso só é sucesso se dado foi obtido.** Nenhum módulo pode retornar
  sucesso sem ter adquirido nada — conclusão negativa falsa ("os bancos dos
  aplicativos foram examinados e estavam vazios") é o pior defeito possível
  numa ferramenta pericial.
- **Completude é verificável, não presumida.** A origem é inventariada
  antes da cópia e reconciliada depois. O inventário usa `find` quando o
  aparelho o possui e cai para `ls -R` quando não (Android 5.x e anteriores
  usam toolbox, sem `find`); o relatório informa qual via foi usada. Quando
  nenhuma funciona, a completude é reportada como **NÃO VERIFICÁVEL** —
  nunca como completa.
- **Todo comando fala com o aparelho do caso.** Os comandos são vinculados
  ao serial (`adb -s`), e mais de um aparelho conectado **bloqueia** a
  extração em vez de o sistema escolher um por conta própria.
- **Datas originais são preservadas** (`adb pull -a`): sem essa flag, todo
  arquivo seria carimbado com a data da cópia, destruindo um dado que é
  prova.
- **Erro nunca chega disfarçado de dado.** Falha de comando e resposta do
  aparelho trafegam por canais separados.
- **A cópia é conferida contra o aparelho.** O SHA-256 é calculado também
  *dentro* do dispositivo (`sha256sum`) e confrontado com o do destino —
  hashear apenas o arquivo que chegou provaria que ele não mudou desde que
  chegou, não que a transferência foi fiel. Onde isso não é possível, a não
  verificação fica declarada.
- **A aquisição é interrompível.** Cancelamento surte efeito durante a
  cópia, e um ADB que parou de responder é abandonado após 5 minutos sem
  sinal, em vez de pendurar a aplicação.
- **O espaço é conferido antes.** Cópia truncada por disco cheio na estação
  não pode chegar ao exame como se fosse limitação do aparelho.

### Limites conhecidos — o que a suíte NÃO alcança

Declarados aqui de propósito: uma ferramenta pericial vale pelo que informa
sobre seus próprios limites tanto quanto pelo que extrai.

| Limite | Consequência |
|---|---|
| **Apenas o perfil principal** (usuário 0) | Perfil de trabalho e segundo usuário mantêm dados em `/data/user/<n>/`, não adquiridos. Detectado e declarado quando há mais de um perfil. |
| **`/sdcard/Android/data` em Android 11+** | O sistema não o expõe ao ADB. O `adb pull` de `/sdcard` não traz essa subárvore, **sem erro e sem aviso**. Detectado pela versão e declarado. |
| **Áreas privadas de aplicativo** (`/data/data`) | Exigem root. Bancos de mensagens de WhatsApp, Telegram e demais não são adquiridos sem ele. |
| **Extração física** | Exige root. **Nunca executada em aparelho real** — sem validação de campo. |
| **Comportamento em Android 11+** | Não validado: os aparelhos usados nos testes são API 21 e API 28. |
| **Módulo de Mensageiros** | Validado com estrutura sintética, não com aplicativos reais instalados. |

Em todos esses casos vale a mesma regra que orienta o projeto inteiro:
**ausência de dado no material extraído nunca autoriza concluir ausência do
dado no aparelho.**

-------------------------------------------------------------------------------
## 13. TESTES AUTOMATIZADOS
-------------------------------------------------------------------------------
A suíte de testes cobre justamente os cenários de falha — que é onde uma
ferramenta pericial precisa ser confiável:

```
python tests/rodar_todos.py
```

| Arquivo | O que trava |
|---|---|
| `test_extracao_fisica.py` | Imagem de 0 byte, truncada, código de saída ≠ 0, acesso negado, ADB sem `exec-out`, hash real |
| `test_pull_auditavel.py` | Classificação do desfecho da cópia, captura de saída, uso do `-a`, reconciliação origem × destino, erro que não vira dado |
| `test_serial_e_procedimento.py` | Vinculação ao serial, bloqueio com múltiplos aparelhos, aferição de relógio, registro do procedimento |
| `test_modulos_novos.py` | Validação do IMEI por Luhn, leitura do Parcel em UTF-16, artefatos do sistema, mensageiros, APKs |
| `test_estrutura_caso.py` | Caso × aquisição, colisão de timestamp, sugestão de identificador, destinos do manifesto |
| `test_controle_aquisicao.py` | Espaço em disco, cancelamento, teto de inatividade, progresso por faixa |
| `test_verificacao_origem.py` | Hash na origem, restrição do Android 11+, sobreposição de módulos, conferência do aparelho |
| `test_estado_e_bugreport.py` | Captura de tela por `exec-out`, perfis de usuário, formatos do bugreport |
| `test_cadeia_custodia.py` | Conferência de integridade, proteção do selo, caso que passa na própria verificação |
| `test_android_antigo.py` | Shell sem `find`, motivo real da recusa do IMEI, aparelho perdido no meio, provider sem retorno |

Os testes não dependem de aparelho conectado: o ADB é substituído por
dublês que reproduzem os desfechos reais, inclusive materializando arquivos
em disco para exercitar a reconciliação de verdade.

-------------------------------------------------------------------------------
## 14. DOCUMENTOS: RELATÓRIO DE EXTRAÇÃO, LAUDO PERICIAL, RELATÓRIO DE CONTEÚDO
-------------------------------------------------------------------------------
Todos saem com a identidade do Hexis Forensics e com o mesmo rodapé em
**cada página**: versão da ferramenta, data de emissão, `Página N de M` e
o **SHA-256 do manifesto** da aquisição. Uma página solta continua dizendo
de que coleta saiu e contra qual selo pode ser conferida.

Todos ficam **fora da aquisição selada** (`<caso>/documentos/` e
`<caso>/relatorios/`): são emitidos depois do manifesto, e gravá-los dentro
faria a conferência acusar o próprio documento como arquivo acrescentado.
Reemitir não apaga a emissão anterior.

| Documento | Quando | O que traz |
|---|---|---|
| **Relatório de Extração** | Sob demanda, no gerenciador de casos | Identificação, peça (declarado × apurado), fotos, ambiente e relógio gravados no dia, autorização com hash, método e limitações, alterações e decisões registradas, desfecho por módulo, resumo do conteúdo, **arquivos adquiridos por categoria** (imagens, vídeos, áudios, PDF, documentos…), inventário, integridade, requisitos da norma verificados, linha do tempo do procedimento e reprodução do manifesto |
| **Laudo Pericial** | Sob demanda, no gerenciador de casos | Preâmbulo, objetivo do exame, material examinado, metodologia, limitações, exames e resultados (com volume e interlocutores das comunicações), cadeia de custódia, conclusão derivada do desfecho, e o bloco de assinatura |
| **Relatório de Conteúdo** | Sob demanda | Cada mensagem, chamada e contato, em CSV por artefato e HTML, com arquivo e linha de origem. No PDF, conversas acima de 300 mensagens saem como índice |
| **Conversas selecionadas** | Sob demanda | O PDF completo só das conversas que o examinador escolher |

O laudo separa três origens que não podem se confundir: o que a
**ferramenta** registrou e sustenta com arquivo selado; o que o
**examinador** declara no ato (objetivo, circunstâncias do exame,
considerações); e o que foi **digitado** no cadastro. O operador da
aquisição e o examinador que subscreve aparecem os dois — podem não ser a
mesma pessoa.

-------------------------------------------------------------------------------
## 15. INSTALADOR E PASTA PORTÁTIL
-------------------------------------------------------------------------------
```
py empacotar.py --portatil      # dist/HexisForensics-portatil/
py empacotar.py --instalador    # dist/HexisForensics-Setup-<versão>.exe
```

Os dois entregam a mesma coisa: o interpretador Python ao lado do código
da suíte, **legível**, com `HASHES_DO_CODIGO.sha256` para conferir o que
está rodando. O build só termina depois de **executar** o resultado: a
suíte de testes inteira roda com o interpretador que vai dentro, e a
janela principal precisa abrir.

- **Pasta portátil** — copie a pasta e abra `HexisForensics.bat`. Os
  casos ficam em `extracoes/`, dentro dela.
- **Instalador** (requer o Inno Setup 6 para ser gerado) — instala por
  usuário, sem pedir Administrador, com atalhos no Menu Iniciar. Na cópia
  instalada os casos ficam em `%USERPROFILE%\HexisForensics-Casos`,
  **fora da pasta do programa** e fora de pasta sincronizada com nuvem; a
  desinstalação não toca neles.

**Assinatura digital.** O `Setup.exe` sai sem assinatura. Em máquina com o
Controle Inteligente de Aplicativos do Windows 11 ligado ele é bloqueado;
nas demais, o SmartScreen avisa e permite prosseguir. A pasta portátil não
tem esse problema, porque o executável que roda é o do próprio Python,
assinado pelo fabricante. Resolver de vez exige um certificado de
assinatura de código.

O `adb.exe` que estiver em `binario/` no momento do build vai junto.

Licença: GPL-3.0 — ver o [README](../README.md#licença) e o [LICENSE](../LICENSE).
