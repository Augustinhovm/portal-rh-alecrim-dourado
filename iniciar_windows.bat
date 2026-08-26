@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  echo Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
  echo.
  echo O Portal RH foi encerrado com erro.
  pause
)
