@echo off
cd /d "%~dp0"
echo ==========================================
echo  Atualizacao V6.5 - Banco de Horas
echo ==========================================
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" migrar_v65.py
if errorlevel 1 (
  echo ERRO na migracao V6.5.
  pause
  exit /b 1
)
echo.
echo Atualizacao V6.5 concluida.
echo Agora execute iniciar_windows.bat
pause
