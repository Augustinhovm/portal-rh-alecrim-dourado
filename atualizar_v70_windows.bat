@echo off
cd /d "%~dp0"
echo ==========================================
echo  Portal RH - Nucleo RH V7.0
echo ==========================================
if not exist ".venv\Scripts\python.exe" (echo ERRO: .venv nao encontrado.&pause&exit /b 1)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo ERRO nas dependencias.&pause&exit /b 1)
".venv\Scripts\python.exe" migrar_v70.py
if errorlevel 1 (echo ERRO na migracao.&pause&exit /b 1)
echo.
echo V7.0 atualizada com sucesso. Execute .\iniciar_windows.bat
pause
