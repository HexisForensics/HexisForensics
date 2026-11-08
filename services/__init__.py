"""
Camada de serviços do HexisForensics.

Fica entre `core/` (regras de negócio de extração, sem Qt) e `ui/`
(apresentação, sem lógica de negócio): orquestra chamadas ao core,
gerencia execução assíncrona (QThread) e resolve configuração de
aplicação (identidade visual). A UI nunca importa `core.*` diretamente —
sempre passa por um serviço daqui.

Módulos:
    - `branding_service`: carrega o perfil de identidade visual (cores,
      logo, ícone, nome de exibição).
    - `device_service`: fachada única de status/identificação de
      dispositivo, escondendo se é Android ou iOS.
    - `case_service`: sugestão, criação e registro de pastas de caso.
    - `extraction_service`: catálogo de extratores por plataforma e
      execução assíncrona (`ExtractionService`, um QThread).
    - `hash_service`: listagem de pastas de extração e geração do
      manifesto de hashes (`HashService`, um QThread).
"""
