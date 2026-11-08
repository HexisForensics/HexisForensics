# HexisForensics — instruções de projeto

Suíte de extração forense (PySide6) para Android, iOS e Computador.
Contexto normativo: **ISO/IEC 27037** (identificação, coleta, aquisição e
preservação de evidência digital). Operadores são DEFR ou DES — papéis de
competência técnica, não de corporação.

## Arquitetura — regra inviolável

```
ui/  ──chama──▶  services/  ──chama──▶  core/
```

- `core/` — regra de negócio de extração. **Nunca importa PySide6.**
- `services/` — orquestração, QThread, config. Conhece `core` e Qt, nunca widgets.
- `ui/` — apresentação pura. Só fala com `services/`.

Única exceção aceita: `ui/widgets/extraction_panel.py` importa o *tipo*
`core.base_extractor.BaseExtractor` apenas para anotação.

## Convenções

- **Todo código, nome e comentário em português.** Inclusive nomes de
  variáveis, métodos e atributos.
- Extratores se registram sozinhos com `@registrar_extrator` (`core/registry.py`).
  Adicionar um módulo novo não exige tocar em nenhum outro arquivo.
- Todo extrator herda de `AndroidExtractor` / `IOSExtractor` / `ComputadorExtractor`
  e retorna `ResultadoExtracao(sucesso, mensagem, caminho_saida, detalhes)`.
- Ressalvas (sucesso parcial) vão em `detalhes` com uma chave listada em
  `services.extraction_service.CHAVES_RESSALVA`.

## Princípios forenses que o código precisa respeitar

1. **Sucesso só é sucesso se dado foi obtido.** Um módulo que não copiou
   nada NUNCA pode retornar `sucesso=True` — conclusão negativa falsa é o
   pior defeito possível nesta ferramenta.
2. **Hash no momento da aquisição**, não depois (`core/hashing.EscritorComHash`).
3. **Toda saída de comando é evidência** — stdout e stderr nunca são descartados.
4. **Nada de tradução de bytes** em fluxo binário: usar `exec-out`, nunca `adb shell`.
5. **Toda alteração no dispositivo alvo é registrada e justificada.**
6. Comandos ADB são vinculados ao serial do aparelho do caso (`adb -s <serial>`).
7. **Um caso reúne várias aquisições.** A pasta do caso é reaproveitada; a
   pasta da aquisição (`<caso>/<plataforma>_<AAAAMMDD_HHMMSS>/`) nunca é.
   `core/case.py` é a **única** fonte da nomenclatura — manter uma segunda
   implementação em `services/` já causou sugestão de identificador errada.

8. **Dado do caso mora em `caso.json`; dado da peça, em `cadeia_custodia.txt`.**
   O texto da cadeia de custódia tem uma única montagem
   (`core.case.montar_cadeia_custodia`). Retificar nunca reescreve aquisição
   selada: vira complemento.
9. **Documento derivado nunca é gravado dentro de aquisição selada.**
   Relatório de Extração, Laudo, relatório de conteúdo e material
   decifrado ficam no nível do caso (`documentos/`, `relatorios/`,
   `decifrados/`). O relatório
   automático já foi parar dentro da pasta selada uma vez, quando o nome da
   aquisição fugia do padrão — ver `pasta_de_documentos`.
10. **Módulo que altera o dispositivo de forma relevante é de seleção
    expressa** (`selecao_expressa = True`): começa desmarcado e o "Marcar
    todos" não o alcança.

## Identidade e nomenclatura

A suíte é o **Hexis Forensics**, ferramenta de perícia forense
convencional, sem vínculo institucional: não há tela de acesso, brasões nem
termos de procedimento institucional em código, tela ou documento. O operador é
o que o **perfil do examinador** declara (`services/perfil_service.py`).
Todo PDF usa `services/identidade_pdf.py` (logo, rodapé com o SHA-256 do
manifesto e "página N de M") e lê a aquisição por `services/dossie_service.py`.

## Executar

```
pip install -r requirements.txt
py main.py
py tests/rodar_todos.py
py empacotar.py --instalador     # pasta portátil + Setup.exe (Inno Setup 6)
```

Use `py`, não `python`: o do Git Bash não tem PySide6.

`adb.exe` vai em `binario/` (ou no PATH). Resultados em `extracoes/`.
