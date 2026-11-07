import os
import sys
import subprocess
import shutil

print("==================================================")
print("     COMPILANDO J.A.R.V.I.S. WINDOWS (.EXE)       ")
print("==================================================")

SRC_MAIN = r"c:\JARVIS\jarvis-windows\main.py"
ICON_PATH = r"c:\JARVIS\web\jarvis_hud.ico"
DIST_DIR = r"c:\JARVIS\dist"
BUILD_DIR = r"c:\JARVIS\build"

cmd = [
    sys.executable,
    "-m", "PyInstaller",
    "--noconsole",
    "--noconfirm",
    "--name", "JARVIS",
    "--icon", ICON_PATH,
    "--distpath", DIST_DIR,
    "--workpath", BUILD_DIR,
    "--clean",
    "--paths", r"c:\JARVIS\jarvis-windows",
    "--paths", r"c:\JARVIS",
    "--add-data", r"c:\JARVIS\web;web",
    "--add-data", r"c:\JARVIS\config;config",
    "--hidden-import", "PyQt6.QtWebEngineWidgets",
    "--hidden-import", "PyQt6.QtWebEngineCore",
    "--hidden-import", "PyQt6.QtWidgets",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "websockets",
    "--hidden-import", "tinytuya",
    "--hidden-import", "psutil",
    "--hidden-import", "sounddevice",
    "--hidden-import", "numpy",
    "--hidden-import", "services.tuya_service",
    "--hidden-import", "requests",
    "--hidden-import", "unified_memory",
    "--hidden-import", "mimo_brain",
    "--hidden-import", "core_ai_brain",
    "--hidden-import", "session_manager",
    "--hidden-import", "mimo_tools",
    "--hidden-import", "laya_screen_subagent",
    "--hidden-import", "dynamic_presentation_engine",
    "--hidden-import", "lg_tv_manager",
    "--hidden-import", "mimo_tts",
    "--hidden-import", "stt_engine",
    "--hidden-import", "services.device_api",
    "--hidden-import", "comtypes.client",
    "--hidden-import", "cryptography.hazmat.primitives.ciphers",
    "--hidden-import", "system.win_controls",
    "--hidden-import", "system.hardware_monitor",
    "--hidden-import", "system.pc_automation",
    "--hidden-import", "pyautogui",
    "--hidden-import", "pyperclip",
    "--hidden-import", "PIL",
    "--hidden-import", "PIL.ImageGrab",
    "--hidden-import", "mcp.windows_mcp",
    "--hidden-import", "core.local_server",
    "--hidden-import", "core.network_client",
    "--hidden-import", "voice.voice_engine",
    "--collect-all", "openwakeword",
    "--collect-all", "onnxruntime",
    "--hidden-import", "openwakeword",
    "--hidden-import", "openwakeword.model",
    "--hidden-import", "openwakeword.utils",
    "--hidden-import", "onnxruntime",
    "--add-data", r"C:\Users\werik\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages\openwakeword\resources;openwakeword\resources",
    "--hidden-import", "ui.hud_window",
    "--hidden-import", "config.settings",
    "--hidden-import", "vision",
    "--hidden-import", "vision.engine",
    "--hidden-import", "vision.camera",
    "--hidden-import", "vision.gestures",
    "--hidden-import", "vision.actions",
    "--hidden-import", "vision.events",
    "--hidden-import", "vision.config",
    "--hidden-import", "vision.auth",
    SRC_MAIN
]

print("Executando PyInstaller com caminhos configurados...")
res = subprocess.run(cmd)

if res.returncode == 0:
    exe_path = os.path.join(DIST_DIR, "JARVIS", "JARVIS.exe")
    if not os.path.exists(exe_path):
        exe_path = os.path.join(DIST_DIR, "JARVIS.exe")
    print("\n[SUCESSO] JARVIS.exe gerado com sucesso!")
    print(f"Caminho do executavel: {exe_path}")

    # Criar atalhos no Desktop e Inicializacao do Windows
    print("\nInstalando atalhos no Windows...")
    ps_shortcut = f'''
$WshShell = New-Object -ComObject WScript.Shell

# 1. Atalho na Area de Trabalho (Desktop)
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\\J.A.R.V.I.S..lnk")
$Shortcut.TargetPath = "{exe_path}"
$Shortcut.WorkingDirectory = "{os.path.dirname(exe_path)}"
$Shortcut.IconLocation = "{ICON_PATH}"
$Shortcut.Description = "J.A.R.V.I.S. Artificial Intelligence System"
$Shortcut.Save()
Write-Host "Atalho Desktop criado com sucesso!"

# 2. Atalho na Inicializacao Automatica (Startup)
$StartupPath = [Environment]::GetFolderPath('Startup')
$StartupShortcut = $WshShell.CreateShortcut("$StartupPath\\J.A.R.V.I.S..lnk")
$StartupShortcut.TargetPath = "{exe_path}"
$StartupShortcut.WorkingDirectory = "{os.path.dirname(exe_path)}"
$StartupShortcut.IconLocation = "{ICON_PATH}"
$StartupShortcut.Description = "J.A.R.V.I.S. Auto-Start"
$StartupShortcut.Save()
Write-Host "Atalho Inicializacao criado com sucesso!"
'''
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_shortcut])
    print("[INSTALACAO CONCLUIDA] J.A.R.V.I.S. instalado no Desktop e na Inicializacao do Windows!")
else:
    print(f"\n[ERRO] PyInstaller falhou com codigo {res.returncode}")
    sys.exit(res.returncode)
