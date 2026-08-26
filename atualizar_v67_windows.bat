@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Primeiro Acesso V6.7
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" migrar_v67.py
if errorlevel 1 (
  echo ERRO ao atualizar o banco.
  pause
  exit /b 1
)
echo.
echo Atualizacao V6.7 concluida.
echo Agora execute: .\iniciar_windows.bat
pause
