@echo off
cd /d "C:\JARVIS\jarvis-windows"
set "PYW=C:\Users\werik\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
start "" "%PYW%" "C:\JARVIS\jarvis-windows\main.py"
exit
