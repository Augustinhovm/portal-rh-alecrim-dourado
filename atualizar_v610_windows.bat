@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Impressao de Atestados V6.10
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
echo Instalando dependencias da impressao em lote...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO ao instalar dependencias.
  pause
  exit /b 1
)
echo.
echo Atualizacao V6.10 concluida.
echo Agora execute: .\iniciar_windows.bat
pause
