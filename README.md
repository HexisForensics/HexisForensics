<p align="center"><img src="assets/marca/logo_claro.png" alt="Hexis Forensics" width="420"></p>

<p align="center"><b>Extração e preservação de evidência digital — gratuita e de código aberto</b><br>
Android · iPhone · pendrives e discos · orientada pela ABNT NBR ISO/IEC 27037</p>

<p align="center">
  <a href="https://github.com/HexisForensics/HexisForensics/releases/latest">
    <img src="https://img.shields.io/badge/%E2%AC%87%20Baixar%20para%20Windows-instalador%20%2B%20apostila-1f6feb?style=for-the-badge" alt="Baixar para Windows">
  </a>
</p>

<p align="center">Na página de download estão o <b>instalador</b>, o seu <b>hash SHA-256</b> e a <b>apostila do usuário</b> (PDF).<br>
Não é preciso conta no GitHub.</p>

<p align="center">
  📘 <a href="docs/Apostila_Hexis_Forensics.pdf">Apostila do Usuário</a> ·
  ⚡ <a href="docs/Guia_de_Extracao_Rapida.pdf">Guia de Extração Rápida</a>
</p>

---

## O que é

O **Hexis Forensics** é uma ferramenta para o procedimento de rotina da
perícia em dispositivos: coletar o que responde ao exame, registrar como
cada dado foi obtido e entregar documentos que se sustentam sozinhos.

- **Android** — agenda, chamadas, SMS e MMS, mídias, WhatsApp (pelo backup
  com chave de 64 dígitos), artefatos do sistema, relatório de diagnóstico.
- **iPhone** — backup local comum ou cifrado (que traz o registro de
  chamadas), com decifragem, mensagens, agenda, WhatsApp e fotos.
- **Pendrives e discos** — cópia lógica, artefatos do Windows e imagem do
  volume, com bloqueador de escrita.
- **Lacre por hash** — o SHA-256 de cada arquivo é calculado no momento da
  aquisição, e a integridade pode ser conferida a qualquer tempo.
- **Documentos** — Relatório de Extração, Relatório de Conteúdo (com os
  locais das fotos), PDF de conversas selecionadas e Laudo Pericial.
- **Exame sem extração** — o laudo do aparelho bloqueado ou danificado, com
  a mesma cadeia de custódia.

## Os princípios

1. **Nunca afirmar o que não foi verificado.** Quando um dado não é obtido,
   o documento diz por quê. Ausência de dado no material nunca é
   apresentada como ausência de dado no aparelho.
2. **Toda alteração no aparelho é registrada e justificada.** Os módulos que
   mexem no dispositivo começam desmarcados e deixam o registro do que foi
   feito.
3. **O necessário, bem registrado.** Coletar o que interessa ao exame e
   documentar a procedência de cada dado.

## Como instalar

### Opção 1 — Instalador para Windows (recomendado)

1. Baixe o instalador na [página de download](https://github.com/HexisForensics/HexisForensics/releases/latest).
2. **Confira o hash.** Na pasta do arquivo, abra o Terminal e digite
   `Get-FileHash .\HexisForensics-Setup-1.0.0.exe`. O valor tem de ser
   idêntico ao publicado na página de download.
3. Execute o instalador. Como ele não tem assinatura digital paga, o Windows
   mostra **“O Windows protegeu o computador”**: clique em **Mais
   informações** e em **Executar assim mesmo**.
4. Na primeira abertura, cadastre o seu perfil de examinador e guarde o
   **código de recuperação** da senha.

> Em alguns computadores o **Controle Inteligente de Aplicativos** do Windows 11
> bloqueia o instalador **sem** oferecer o botão “Executar assim mesmo”, por ele
> não ter assinatura digital. Nesse caso, instale em outro computador, peça ao
> setor de TI que libere o programa, ou use a **Opção 2** abaixo.

### Opção 2 — Rodar do código-fonte

Quando o instalador é bloqueado e não há como liberá-lo, a ferramenta roda
direto do código-fonte, como qualquer projeto de código aberto. Exige alguns
passos a mais, mas não depende de assinatura digital.

1. Instale o **Python 3.13** ([na página de downloads](https://www.python.org/downloads/),
   escolha a versão **3.13** — **não** a 3.14, que ainda não tem uma das
   bibliotecas do iPhone). Na primeira tela do instalador do Python, marque
   **Add python.exe to PATH**.
2. Baixe o **Fonte (ZIP)** da versão marcada, na
   [página de versões](https://github.com/HexisForensics/HexisForensics/releases)
   — **não** o “Code → Download ZIP” da página principal, que traz a versão em
   desenvolvimento. Confira o hash do ZIP (`Get-FileHash .\HexisForensics-1.0.0-fonte.zip`),
   idêntico ao publicado na Release, e extraia a pasta.
3. Abra a pasta extraída, clique com o botão direito num espaço vazio e escolha
   **Abrir no Terminal**.
4. Instale as bibliotecas e abra a ferramenta:

   ```
   py -m pip install -r requirements.txt
   py main.py
   ```

O `adb.exe` já vem no ZIP, então a extração de Android funciona sem passo
extra. Os casos ficam em **HexisForensics-Casos**, na sua pasta de usuário do
Windows — a mesma da versão instalada, **fora** da pasta do programa, para que
atualizar (baixar o ZIP novo) nunca alcance as aquisições.

A [apostila](docs/Apostila_Hexis_Forensics.pdf) explica cada passo, com as
telas.

**Requisitos:** Windows 10 ou 11 e cabo USB de dados. Para iPhone, o
aplicativo **Dispositivos Apple** (Microsoft Store) ou o iTunes.

## Onde a versão 1.0 foi provada

| Aparelho | Sistema |
|---|---|
| Motorola moto x4 | Android 9 |
| Samsung Galaxy A22 | Android 13 (One UI 5.1) |
| Emulador Android, com privilégio elevado | Android 13 |
| iPhone 11 | iOS 18.6.2 |
| Pendrive | Windows 11 |

Outros modelos tendem a funcionar pelo mesmo caminho, mas não foram
verificados. **Limitação conhecida:** o aplicativo agente ainda não foi
verificado em aparelhos **Xiaomi, Redmi e POCO**. A lista completa de
limitações está na apostila.

## O que a ferramenta não faz

Não desbloqueia aparelho, não contorna senha, não faz extração física de
celular sem privilégio elevado e não recupera dado apagado. Para esses casos
existem ferramentas especializadas.

## Para quem programa

O código está organizado em três camadas (`core` → `services` → `ui`), com
uma suíte de testes automatizados. Para executar a suíte, veja a **Opção 2**
acima e rode a ferramenta do código-fonte. A documentação técnica está em
[docs/DESENVOLVIMENTO.md](docs/DESENVOLVIMENTO.md).

```
py tests/rodar_todos.py
```

## Contato

Dúvidas e comentários: **contatohexisforensics@gmail.com**

LinkedIn: [Hexis Forensics](https://www.linkedin.com/in/hexis-forensics-75779344a)

## Licença

Copyright (C) 2026 Hexis Forensics.

O Hexis Forensics é software livre: pode ser redistribuído e modificado
nos termos da **GNU General Public License, versão 3** (GPL-3.0), publicada
pela Free Software Foundation. Quem distribuir uma versão modificada deve
distribuí-la também sob a GPL-3.0, com o código-fonte.

É distribuído na expectativa de ser útil, mas **sem nenhuma garantia** —
nem mesmo a implícita de comerciabilidade ou de adequação a uma finalidade
específica. O texto integral está no arquivo [LICENSE](LICENSE).

As bibliotecas de terceiros que acompanham o instalador mantêm as próprias
licenças: pymobiledevice3 e pyiosbackup (GPL-3.0), PySide6 (LGPL-3.0),
reportlab (BSD), cryptography e packaging (Apache-2.0/BSD) e o ADB do
Android (Apache-2.0).
