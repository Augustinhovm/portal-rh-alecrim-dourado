@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Ciencia Mensal V7.2
echo ==========================================
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO ao atualizar dependencias.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" migrar_v72.py
if errorlevel 1 (
  echo ERRO ao atualizar banco.
  pause
  exit /b 1
)
echo.
echo V7.2 atualizada com sucesso.
echo Execute: .\iniciar_windows.bat
pause
