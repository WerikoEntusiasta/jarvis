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
    "--add-data", r"c:\JARVIS\jarvis-windows\system;system",
    "--add-data", r"c:\JARVIS\jarvis-windows\core;core",
    "--add-data", r"c:\JARVIS\jarvis-windows\ui;ui",
    "--add-data", r"c:\JARVIS\jarvis-windows\voice;voice",
    "--add-data", r"c:\JARVIS\mimo_tts.py;.",
    "--add-binary", r"c:\JARVIS\ffmpeg.exe;.",
    "--collect-all", "edge_tts",
    "--hidden-import", "edge_tts",
    "--hidden-import", "obsidian_manager",
    "--hidden-import", "task_tracker",
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
    print(f"\n[SUCESSO] JARVIS.exe gerado com sucesso!")
    print(f"Caminho do executavel: {exe_path}")

    # Cria ou atualiza os atalhos no Windows
    print("\nInstalando atalhos oficiais no Windows...")
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")

        # 1. Desktop do Usuário
        desktop_user = shell.SpecialFolders("Desktop")
        lnk_user = os.path.join(desktop_user, "JARVIS.lnk")
        s = shell.CreateShortcut(lnk_user)
        s.TargetPath = exe_path
        s.WorkingDirectory = os.path.dirname(exe_path)
        s.IconLocation = ICON_PATH
        s.Description = "J.A.R.V.I.S. Mark VII - Stark Sovereign AI"
        s.Save()
        print("Atalho Desktop criado com sucesso!")

        # 2. Menu Iniciar
        programs_dir = shell.SpecialFolders("Programs")
        lnk_start = os.path.join(programs_dir, "JARVIS.lnk")
        s2 = shell.CreateShortcut(lnk_start)
        s2.TargetPath = exe_path
        s2.WorkingDirectory = os.path.dirname(exe_path)
        s2.IconLocation = ICON_PATH
        s2.Description = "J.A.R.V.I.S. Mark VII - Stark Sovereign AI"
        s2.Save()
        print("Atalho no Menu Iniciar criado com sucesso!")

        # 3. Startup (Inicialização do Windows)
        startup_dir = shell.SpecialFolders("Startup")
        lnk_startup = os.path.join(startup_dir, "JARVIS.lnk")
        s3 = shell.CreateShortcut(lnk_startup)
        s3.TargetPath = exe_path
        s3.WorkingDirectory = os.path.dirname(exe_path)
        s3.IconLocation = ICON_PATH
        s3.Description = "J.A.R.V.I.S. Mark VII - Inicializacao Automatica"
        s3.Save()
        print("Atalho Inicializacao criado com sucesso!")

        print("\n[INSTALACAO CONCLUIDA] J.A.R.V.I.S. instalado no Desktop, Menu Iniciar e Inicializacao do Windows!")
    except Exception as e:
        print(f"[Aviso] Nao foi possivel registrar os atalhos automaticamente: {e}")
else:
    print(f"\n[ERRO] Falha na compilacao PyInstaller (Codigo {res.returncode})")
    sys.exit(res.returncode)
