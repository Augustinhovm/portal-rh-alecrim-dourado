@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Retorno de Ferias V7.3.2
echo ==========================================
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" corrigir_banco_v732.py
if errorlevel 1 (
  echo ERRO ao corrigir banco.
  pause
  exit /b 1
)
echo.
echo V7.3.2 atualizada com sucesso.
echo Execute: .\iniciar_windows.bat
pause
