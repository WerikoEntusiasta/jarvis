@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"

set "PYW=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

start "" "%PYW%" "%~dp0desktop\app.py"
exit

