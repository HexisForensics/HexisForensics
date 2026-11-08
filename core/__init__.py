"""
Núcleo do HexisForensics.

Este pacote concentra TUDO relacionado à extração — tanto o que é comum a
qualquer plataforma (`base_extractor.py`, `registry.py`, `case.py`,
`hashing.py`, `logger.py`) quanto o que é específico de cada uma
(`core.android`, `core.ios`). Nada aqui importa PySide6 de propósito.

A aplicação é dividida em três camadas:
    - `core/` (este pacote): regras de negócio de extração, sem I/O de UI.
    - `services/`: orquestra o core, executa em background (QThread) e
      resolve configuração de aplicação (ex.: identidade visual).
    - `ui/`: apresentação (PySide6). Nunca importa `core` diretamente —
      só fala com `services/`.

Essa separação é o que permite o núcleo ser reutilizado no futuro por uma
CLI, testes automatizados etc., sem arrastar dependências de interface.

Subpacotes:
    - `core.android`: plataforma Android (adb, device, extractors/).
    - `core.ios`: plataforma iOS (arquitetura pronta; extractors/ ainda
      como stubs, aguardando integração real via pymobiledevice3/libimobiledevice).
"""
