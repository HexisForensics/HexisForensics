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

## Estado atual (2026-11-15)

- **Guia de Extração Rápida (PT/ES/EN):** atualizado com a **Ficha do Aparelho**;
  o PT recebeu também o aviso legal e a seção de instalação (alinhado ao ES/EN).
  Os três em 2 páginas. **Feito.**
- **Apostila / Manual (PT/ES/EN):** atualizada com a Ficha do Aparelho (cap. 1, 9,
  10 e glossário), **nos três idiomas**. **Feito.**
- **Guia de Prática com Emulador (PT/ES/EN):** sem alteração pendente conhecida.
- **Publicação na Release:** **completa** em `v1.0.0` (15/11). Os **9 documentos
  de produto (3 documentos × 3 idiomas)** estão publicados, **cada um com seu
  `.sha256`** — apostila/manual, guia de extração rápida e guia de prática com
  emulador, nos três idiomas. Publicado via `gh release upload ... --clobber`
  (o `gh` foi instalado e autenticado nesta estação).
