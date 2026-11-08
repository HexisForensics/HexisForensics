"""
Camada de UI (PySide6) do HexisForensics.

Responsável só por apresentação: janelas, diálogos e widgets. Não conhece
regras de negócio de extração (`core/`) — tudo o que precisa de lógica ou
execução assíncrona é pedido a `services/`. A identidade visual (cores,
logo, ícone, nome de exibição) vem de fora, via `BrandConfig`
(`services.branding_service`), e é aplicada por `ui.style.aplicar_tema`.
"""
