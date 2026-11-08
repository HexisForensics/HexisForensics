@echo off
REM Abre o HexisForensics como Administrador.
REM O modulo de Imagem do Volume le o dispositivo bruto e exige elevacao.

REM 'net session' so tem sucesso com privilegio elevado: e o teste padrao.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando privilegios de Administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
py main.py
