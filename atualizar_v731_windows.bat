@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Correcao Cumulativa V7.3.1
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente virtual .venv nao encontrado.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" corrigir_banco_v731.py
if errorlevel 1 (
    echo.
    echo ERRO ao corrigir o banco.
    pause
    exit /b 1
)

echo.
echo Banco corrigido com sucesso.
echo Agora execute: .\iniciar_windows.bat
pause
