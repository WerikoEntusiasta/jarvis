@echo off
setlocal
cd /d "%~dp0"

echo [*] Criando ambiente virtual proprio do projeto (.venv)...
python -m venv .venv
if errorlevel 1 (
    echo [!] Python nao encontrado no PATH. Instale o Python 3.11+ e rode novamente.
    pause
    exit /b 1
)

echo [*] Atualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [*] Instalando dependencias do J.A.R.V.I.S....
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Falha ao instalar dependencias. Verifique o requirements.txt.
    pause
    exit /b 1
)

echo [+] Ambiente pronto.
echo [+] Para iniciar: execute run_jarvis_desktop.bat
echo [+] Para autoiniciar com o Windows: python install_desktop.py
pause
