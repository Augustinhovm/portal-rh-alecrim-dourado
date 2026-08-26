@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backup_local.py
pause
