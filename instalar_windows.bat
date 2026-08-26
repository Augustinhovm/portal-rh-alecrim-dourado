@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
python seed.py
echo.
echo Instalacao concluida. Execute iniciar_windows.bat
pause
