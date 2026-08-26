@echo off
cd /d "%~dp0"
echo =============================================
echo  Atualizacao V6.3 - Espelho mensal de ponto
echo =============================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  echo Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
echo Nenhuma dependencia nova e necessaria.
echo Atualizacao V6.3 pronta.
echo Agora execute iniciar_windows.bat
pause
