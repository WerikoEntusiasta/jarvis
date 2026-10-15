@echo off
rem ============================================================
rem  J.A.R.V.I.S. ??? Autostart do Windows
rem  Sobe o servidor local e o app (gate facial + node). Sem console
rem  (pythonw ?? GUI, ent??o 'start ""' n??o abre janela e desanexa o processo).
rem ============================================================
cd /d "%~dp0"
if not exist "logs" mkdir "logs"

set "PYW=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

rem Espera a sess??o/??rea de trabalho estabilizar ap??s o logon
timeout /t 12 /nobreak >nul

rem Servidor local (HUD, gate facial, fila de comandos)
start "" "%PYW%" "%~dp0server.py"
timeout /t 45 /nobreak >nul

rem App do n?? (pede a verifica????o facial e conecta como node do n??cleo)
start "" "%PYW%" "%~dp0desktop\app.py"
exit

