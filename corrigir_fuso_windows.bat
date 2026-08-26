@echo off
cd /d "%~dp0"
echo ==========================================
echo   Portal RH - Correcao de fuso horario
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente virtual nao encontrado.
    echo Execute instalar_windows.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" corrigir_fuso_existente.py
echo.
echo Agora execute iniciar_windows.bat.
pause
