# Hexis Forensics — Manual de uso

Guia curto, na ordem em que as coisas acontecem num exame. Para a
arquitetura e as garantias do código, veja `docs/DESENVOLVIMENTO.md`.

**Uma regra para ler tudo o que a ferramenta diz:** ela nunca afirma o que
não verificou. "Não obteve dado" e "NÃO COLETADO" significam que aquele
material não foi adquirido — nunca que ele não existe no dispositivo.

---

## 1. Antes do primeiro exame

1. Abra a suíte (atalho do instalador, ou `py main.py` no código-fonte).
2. No início de cada extração a suíte pergunta **quem é o examinador**:
   escolha um dos cadastrados na estação ou cadastre um novo (nome,
   registro profissional e instituição). Esses dados entram
   na aquisição como declaração sua. Na emissão do laudo a suíte pergunta
   de novo quem o subscreve.
   A lista de examinadores do computador é mantida em **Examinadores**, na
   barra lateral: criar, editar e ver os cadastrados. Editar um examinador
   não altera as aquisições que ele já fez.
3. Para a **Imagem do Volume** de discos, abra a suíte como Administrador.

## 2. Preparar o aparelho Android

1. Configurações → Sobre o telefone → toque 7 vezes em "Número da versão".
2. Opções do desenvolvedor → ative **Depuração USB** e **Permanecer ativo**.
3. Conecte o cabo. Na tela do aparelho, aceite a depuração marcando
   **Sempre permitir deste computador**.
4. Mantenha a tela **desbloqueada** durante toda a aquisição.

Essas alterações são registradas automaticamente no procedimento.

## 3. Fazer a aquisição

1. Menu **Android** → **Verificar Conexão**. O aparelho deve aparecer
   conectado e autorizado.
2. Marque os módulos. A ordem recomendada já é a da lista; **Estado do
   Aparelho** deve rodar primeiro. Módulos marcados "altera o dispositivo —
   seleção expressa" só rodam se você os marcar um a um.
3. **Iniciar Extração**. Confirme o examinador. Em seguida a suíte mostra o
   que os módulos escolhidos alcançam e o que não alcançam — leia antes de
   confirmar.
4. **Caso:** novo (a suíte sugere o próximo número) ou existente.
5. **Autorização:** anexe o documento que ampara o exame, se o tiver. Sem
   ele a aquisição prossegue e registra que nada foi anexado.
6. **Dispositivo:** descrição, **número do lacre** e **duas fotografias** da
   peça, por exemplo frente e verso (lacre e fotos são obrigatórios).
7. Acompanhe o console, com a tela do aparelho **desbloqueada**. Até o
   Android 11, SMS e chamadas vêm pelo backup do sistema, e a suíte confirma
   sozinha o pedido que aparece na tela (se ele ficar parado, toque em
   "Fazer backup dos meus dados", sem digitar senha).

   **Android 12 em diante:** marque também o módulo **Agenda, Chamadas e SMS
   por aplicativo agente**. Ele instala um pequeno aplicativo de leitura,
   recolhe os dados e o desinstala. Se o aparelho pedir confirmação para
   instalar, aceite.
8. No fim, a pasta é selada (manifesto SHA-256) e o **Relatório de
   Extração** em PDF é emitido no gerenciador de casos, pelo botão.

### Mais de um dispositivo no mesmo caso

Repita a aquisição e, no passo 4, escolha **Caso Existente**. Nada do caso
é perguntado de novo. Cada dispositivo tem a própria pasta, o próprio
lacre e o próprio selo.

### Discos, pendrives e HDs

Menu **Armazenamento** → selecione a unidade → marque os módulos. O disco
de um computador é examinado **fora** dele, ligado à estação por adaptador,
de preferência com bloqueador de escrita — a suíte não o substitui.

## 4. WhatsApp sem root: backup com chave de 64 dígitos

O banco de mensagens fica numa área que só o próprio WhatsApp lê. A via
que funciona em qualquer versão do Android é fazer o WhatsApp gravar um
backup local cifrado com uma chave que você conhece.

**No aparelho, antes da aquisição:**

1. WhatsApp → ⋮ → Configurações → Conversas → **Backup de conversas**.
2. Role até o fim e toque em **Backup criptografado de ponta a ponta**.
   - Se estiver **Ativado** com *chave de acesso* ou *senha*, toque em
     **Desativar** primeiro e confirme: nesses modos a chave não é exibida.
     Desativar não apaga conversas. Depois entre no item de novo.
3. Toque em **Mais opções** (e não em "Usar chave de acesso") →
   **Chave de criptografia de 64 dígitos**.
4. O aplicativo mostra a chave em 16 grupos de 4. **Fotografe a tela** e
   toque em **Continuar**.
5. De volta à tela de backup, o item deve mostrar "Ativado · chave de 64
   dígitos". O WhatsApp grava o backup local cifrado com a chave nova na
   hora; se quiser garantir que está atualizado, toque em **Fazer backup**.

Não é preciso ter conta do Google configurada.

**Na suíte:**

6. Faça a aquisição com o módulo **WhatsApp — Mídia e Backups** marcado.
7. Em **Casos e Documentos**, selecione o caso → **Decifrar backup do
   WhatsApp**. A janela tem 16 campos de 4 caracteres, na mesma disposição
   da tela do aparelho: digite grupo a grupo, ou cole a chave inteira.
8. Se a chave estiver certa, o banco é decifrado para fora da pasta selada
   e as mensagens passam a aparecer no Relatório de Conteúdo e no Laudo. Se um dígito estiver errado, **nada** é decifrado — confira a
   anotação.

Ativar o backup com chave é uma alteração no aparelho; ela fica registrada
no caso junto com a chave, para que outro examinador possa repetir a
decifragem.

> O módulo "WhatsApp — Mensagens por substituição temporária do aplicativo"
> é uma via alternativa, mais invasiva, só para Android anterior ao 12.
> Prefira o backup com chave.

## 5. Depois da aquisição

Tudo em **Casos e Documentos**. Selecione o caso; os botões de documento
valem para o dispositivo selecionado na lista "Dispositivos do caso" (o
primeiro já vem selecionado):

| Botão | O que faz |
|---|---|
| **Relatório de Extração (PDF)** | Reemite o relatório técnico da aquisição. |
| **Laudo Pericial (PDF)** | Pede o objetivo do exame, as circunstâncias que só você observou e suas considerações, e emite o laudo. |
| **PDF de conversas selecionadas** | Lista todas as conversas (WhatsApp, SMS, MMS); você marca as relevantes e o PDF traz cada uma completa. |
| **Relatório de Conteúdo** | Cada mensagem, chamada e contato em planilha (CSV), PDF e HTML. |
| **Retificar Dados do Caso** | Corrige os dados do caso e, pela lista de dispositivos da mesma janela, os de cada peça. Nada do que foi selado é reescrito: a correção vira complemento. |
| **Anexar Autorização** | Junta ao caso o documento de autorização que chegou depois. |
| **Decifrar backup do WhatsApp** | Abre o backup com a chave de 64 dígitos e, em seguida, gera e abre o Relatório de Conteúdo. |

Os documentos ficam em `documentos/`, dentro da pasta do caso, **fora** das
pastas seladas. Reemitir não apaga a emissão anterior.

## 6. Conferir a integridade

Menu **Cadeia de Custódia** → selecione a aquisição → **Conferir**. A suíte
recalcula os hashes e aponta o que foi alterado, o que sumiu e o que entrou
depois do selo. Faça isso antes de entregar o material e sempre que ele
mudar de mídia.

## 7. O que a ferramenta não faz

- Não desbloqueia aparelho nem contorna senha.
- Não obtém root. Com o aparelho já em root, aproveita o acesso.
- Sem root, não alcança e-mail. SMS e chamadas saem pelo backup do sistema
  (até o Android 11) ou pelo aplicativo agente (qualquer versão).
- Não recupera arquivo ou mensagem apagados.
- iPhone ainda não é suportado.

## 8. Quando algo dá errado

| Sintoma | O que verificar |
|---|---|
| Aparelho "não autorizado" | Tela desbloqueada; aceite a depuração no aparelho. |
| O aparelho some no meio | Ative "Permanecer ativo"; não troque o modo USB; refaça em nova aquisição. |
| "Não obteve dado" em SMS ou chamadas | Tela bloqueada durante o backup, ou Android 12 ou superior: rode o módulo do aplicativo agente. |
| O agente não instala | Há um pedido de confirmação na tela do aparelho, ou a verificação de aplicativos do aparelho bloqueou a instalação. |
| Decifragem recusada | Chave com dígito errado; backup feito antes de ativar a chave; backup cifrado por senha, não por chave. |
| Conferência acusa arquivo acrescentado | Algum arquivo foi gravado dentro da pasta selada depois da coleta. |

O que aconteceu em cada aquisição está em `registro_procedimento.txt`,
`extracao.log` e `erros/erros.log`, dentro da pasta dela.
