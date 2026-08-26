@echo off
cd /d "%~dp0"
echo ==========================================
echo   Portal RH - Servidor de Producao Windows
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
set APP_ENV=production
".venv\Scripts\python.exe" -m waitress --listen=0.0.0.0:8000 wsgi:app
