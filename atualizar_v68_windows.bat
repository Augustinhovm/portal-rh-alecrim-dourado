@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Senha de Ponto V6.8
echo ==========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: ambiente virtual .venv nao encontrado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" migrar_v68.py
if errorlevel 1 (
  echo ERRO ao atualizar o banco.
  pause
  exit /b 1
)
echo.
echo Atualizacao V6.8 concluida.
echo Para colaboradores antigos, entre como RH e defina a senha de ponto no perfil.
echo Depois execute: .\iniciar_windows.bat
pause
