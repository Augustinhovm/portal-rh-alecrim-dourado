@echo off
cd /d "%~dp0"
echo ==========================================
echo   Atualizacao V6.1 - Relatorio PDF de Ponto
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  echo Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
echo Instalando/atualizando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERRO ao instalar dependencias.
  pause
  exit /b 1
)
echo.
echo Atualizacao V6.1 concluida com sucesso.
echo Agora execute iniciar_windows.bat
pause
