' J.A.R.V.I.S. - Autostart do Windows sem janela CMD
' Estilo 0 (oculto): o shim do venv uv lanca python.exe de console como filho;
' com estilo 1 esse console APARECE na tela (janela CMD feia no logon).
' O gate PIN continua visivel: pin_pad.py forca ShowWindow(SW_RESTORE) nativo.
Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
ProjRoot = Fso.GetParentFolderName(WScript.ScriptFullName)
PyW = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\hermes\hermes-agent\venv\Scripts\pythonw.exe"
WshShell.Run """" & PyW & """ """ & ProjRoot & "\desktop\app.py""", 0, False
