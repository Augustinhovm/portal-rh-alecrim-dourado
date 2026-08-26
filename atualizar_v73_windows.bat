@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Ferias V7.3
echo ==========================================
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO nas dependencias.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" migrar_v73.py
if errorlevel 1 (
  echo ERRO na migracao V7.3.
  pause
  exit /b 1
)
echo.
echo V7.3 atualizada com sucesso.
echo Execute: .\iniciar_windows.bat
pause
