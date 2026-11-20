# Documentos PDF do Hexis Forensics — mapa oficial

Este arquivo é a **referência única** de quais documentos existem, quem é dono
de cada um, qual é a fonte e onde é publicado. Na dúvida de "de quem é isso?"
ou "qual vale?", a resposta está aqui.

## A regra

> **Todo PDF pertence a UM mundo, tem UMA fonte e UM dono.**
> Documento de **produto** nasce do **gerador no repositório** — o material de
> texto pode vir de fora, mas só vira PDF passando pelo gerador. Nunca se
> publica um PDF "avulso" montado por fora: isso cria duas versões do mesmo
> documento, que é a origem da confusão. Material de **curso** é do curso, e o
> repositório não o toca.

---

## Mundo A — Documentos do PRODUTO

O usuário baixa para instalar e operar a ferramenta.

- **Fonte única:** os geradores em `ferramentas/apostila/`.
- **Dono da publicação:** o mantenedor do repositório (via Code).
- **Publicação:** assets da **Release** no GitHub, cada PDF com seu `.sha256` ao
  lado, e os links no site (`docs/`).
- **Idiomas:** PT, ES e EN para todos.

| Documento | Idioma | Gerador | Arquivo gerado (`ferramentas/apostila/saida/`) |
|---|---|---|---|
| **Apostila / Manual do Usuário** | PT | `gerar_apostila.py` | `Apostila_Hexis_Forensics.pdf` |
| | ES | `gerar_apostila_es.py` | `Manual_Usuario_Hexis_Forensics_ES.pdf` |
| | EN | `gerar_apostila_en.py` | `User_Manual_Hexis_Forensics_EN.pdf` |
| **Guia de Extração Rápida** | PT | `gerar_guia_rapido.py` | `Guia_de_Extracao_Rapida.pdf` |
| | ES | `gerar_guia_rapido_es.py` | `Guia_Extraccion_Rapida_Hexis_Forensics_ES.pdf` |
| | EN | `gerar_guia_rapido_en.py` | `Quick_Extraction_Guide_Hexis_Forensics_EN.pdf` |
| **Guia de Prática com Emulador** | PT | `gerar_guia_emulador.py` | `Guia_de_Pratica_com_Emulador.pdf` |
| | ES | `gerar_guia_emulador_es.py` | `Guia_Practica_Emulador_Hexis_Forensics_ES.pdf` |
| | EN | `gerar_guia_emulador_en.py` | `Practice_Guide_Emulator_Hexis_Forensics_EN.pdf` |

Os PDFs ficam em `ferramentas/apostila/saida/`, que é **ignorada pelo Git**: o
repositório guarda os **geradores**, não os PDFs. Para o usuário, o que vale é
o PDF **gerado a partir do gerador** e publicado na Release.

Gerar um documento (exemplos):

```
py ferramentas/apostila/gerar_apostila.py
py ferramentas/apostila/gerar_guia_rapido.py
py ferramentas/apostila/gerar_guia_emulador.py
```

(troque pelo `_es` / `_en` para os outros idiomas.)

---

## Mundo B — Material do CURSO

Material de ensino, **não** é documento de produto.

| Material | Dono | Fonte | Entra no repositório? | Entra na Release do produto? |
|---|---|---|---|---|
| **Livro (Treinamento Oficial)** | Curso | Arquivos do curso | Não | Não |
| **Slides do curso** | Curso | Arquivos do curso | Não | Não |

O Code **não gera, não edita e não publica** material de curso. Ele é
distribuído pelo canal do curso.

---

## Mundo C — Documentação do repositório (Markdown)

Não são PDFs de produto nem material de curso: é documentação versionada no
próprio repositório, em Markdown, para leitura direta no GitHub. **Fonte e
publicação** são o próprio arquivo no repositório (sem gerador, sem Release).

| Documento | O que é | Local |
|---|---|---|
| **Relatório de Validação** | Aferição por módulo (função, procedimento de teste, resultado, aparelho/versão), no sentido da ISO/IEC 27041; cada linha lastreada num teste automatizado | `docs/VALIDACAO.md` |
| **Aparelhos Testados** | Registro exaustivo dos aparelhos e versões em que a ferramenta foi provada | `docs/APARELHOS_TESTADOS.md` |
| **Documentação de Desenvolvimento** | Arquitetura em três camadas e guia para quem programa | `docs/DESENVOLVIMENTO.md` |

Esses documentos estão em **português** e são linkados pelos READMEs.

---

## Fluxo de atualização de um documento de produto

1. O texto novo (de quem escreve o conteúdo) chega **como texto**, nos idiomas
   aplicáveis — nunca como PDF pronto.
2. O Code aplica no **gerador** correspondente (`ferramentas/apostila/*.py`),
   nos três idiomas.
3. O Code **gera** os PDFs e confere (ex.: contagem de páginas, termos-chave).
4. Commit das **fontes** (os geradores) no repositório.
5. Publicação dos **PDFs** como assets da **Release**, cada um com `.sha256`.

A versão de cada documento acompanha a da ferramenta (`core/versao.py`).

---

## Estado atual (2026-11-20)

- **Interface em espanhol (es.json):** **concluída** (2291/2291) e validada no
  emulador. Isso tornou possível a correção abaixo das capturas de tela.
- **Capturas de tela por idioma:** `capturas.py` passou a receber o idioma
  (`py capturas.py pt|es|en`) e gravar em `capturas/<idioma>/`, com a INTERFACE
  no idioma pedido. Cada manual embute os seus próprios prints — o ES/EN
  deixaram de mostrar telas em português. O conteúdo fictício (mensagens,
  contatos) é dado e permanece como está. Os 6 guias são texto puro, sem prints.
- **Apostila / Manual (PT/ES/EN):** regerada 20/11 com as capturas no idioma de
  cada um. Os três são equivalentes: mesmo conteúdo, mesmo layout, tudo (texto e
  telas) no idioma do documento. **Feito.**
- **Guia de Extração Rápida (PT/ES/EN) e Guia de Prática com Emulador (PT/ES/EN):**
  texto puro, já equivalentes; sem alteração nesta rodada.
- **Publicação na Release:** `v1.0.0`. Os **9 documentos de produto (3 × 3
  idiomas)** seguem publicados, cada um com seu `.sha256`. Os **3 manuais** foram
  republicados em 20/11 (capturas por idioma) via `gh release upload ... --clobber`;
  os 6 guias permanecem como em 15/11. O instalador foi reconstruído (PT/ES/EN) e
  o ZIP de código-fonte refeito, ambos republicados.
- **Relatório de Validação:** criado `docs/VALIDACAO.md` (Mundo C), 18 módulos no
  formato ISO/IEC 27041, linkado nos READMEs.
