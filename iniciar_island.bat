@echo off
title JARVIS Apple Dynamic Island
cd /d "%~dp0"

rem Prioridade: venv do projeto (.venv) > venv do hermes > pythonw do PATH
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

start "" "%PYW%" "%~dp0desktop\apple_island.py"
exit

