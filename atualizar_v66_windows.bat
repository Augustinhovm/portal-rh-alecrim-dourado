@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Correcao Banco de Horas V6.6
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente virtual .venv nao encontrado.
    echo Execute instalar_windows.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" corrigir_banco_v66.py
if errorlevel 1 (
    echo.
    echo ERRO ao aplicar a correcao V6.6.
    pause
    exit /b 1
)

echo.
echo Atualizacao concluida.
echo Agora execute: .\iniciar_windows.bat
echo.
pause
