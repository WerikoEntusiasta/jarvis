import os
import sys
import winreg

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "JarvisDesktop"


def _resolve_pythonw():
    """Resolve o pythonw.exe priorizando: ambiente atual > venv do projeto > PATH."""
    exe = sys.executable
    if exe:
        pyw = exe.replace("python.exe", "pythonw.exe")
        if os.path.exists(pyw):
            return pyw
    root = os.path.dirname(os.path.abspath(__file__))
    proj_venv_pyw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(proj_venv_pyw):
        return proj_venv_pyw
    return "pythonw.exe"


def install():
    root = os.path.dirname(os.path.abspath(__file__))
    pythonw = _resolve_pythonw()
    vbs_path = os.path.join(root, "jarvis_autostart.vbs")
    cmd = f'wscript.exe "{vbs_path}"'

    autostart_ok = False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        autostart_ok = True
        print(f"[OK] Jarvis Desktop registrado no Autostart do Windows (HKCU\\...\\Run): {cmd}")
    except Exception as e:
        print(f"[!] Falha ao registrar no Run do Registro ({e}). Usando pasta Inicializar como fallback.")

    if not autostart_ok:
        startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
        os.makedirs(startup_dir, exist_ok=True)
        bat_path = os.path.join(startup_dir, "JarvisDesktop.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\r\nstart "" "{pythonw}" "{app_script}"\r\n')
        print(f"[OK] Atalho de inicialização criado em: {bat_path}")

    print("[OK] Instalação concluída com sucesso.")


if __name__ == "__main__":
    install()
