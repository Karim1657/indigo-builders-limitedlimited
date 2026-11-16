@echo off
REM Windows - double click to run
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if not exist venv (python -m venv venv)
call venv\Scripts\activate
pip install -r requirements.txt -q
:loop
python main.py
echo Bot exited. Restarting in 5 seconds...
timeout /t 5 >nul
goto loop
