Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\JARVIS\jarvis-windows"
pyw = "C:\Users\werik\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
WshShell.Run """" & pyw & """ ""C:\JARVIS\jarvis-windows\main.py""", 0, False
