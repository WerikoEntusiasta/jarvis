#!/usr/bin/env python3
"""
JARVIS Desktop — Nó Windows
Ponto de entrada único que conecta este PC ao JARVIS Core (Zima):
- Polling HTTPS do Core → CommandBus local (controle total do Windows)
- System Tray com status da ponte e menu tático
- Registro automático no Painel de Nós (heartbeat)
- Inicialização com Windows via VBS (jarvis_autostart.vbs)
- Guard de instância única (mutex + socket) — sem duplicatas
"""

import os
import sys
import time
import threading
import socket
import ctypes
import atexit

# Garante que a raiz do projeto (C:\JARVIS) esteja no sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ============================================================
# GUARD DE INSTÂNCIA ÚNICA (mutex + socket) — sem duplicatas
# ============================================================
_MUTEX = None
_SOCKET = None

def ensure_single_instance() -> bool:
    """Retorna True se esta é a primeira instância; False se já existe uma rodando."""
    global _MUTEX, _SOCKET

    mutex_name = "Global\\JARVIS_Desktop_SingleInstance_Mutex"
    kernel32 = ctypes.windll.kernel32
    _MUTEX = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()

    # ERROR_ALREADY_EXISTS (183) = outra instância já criou o mutex
    if last_error == 183:
        print("[JarvisDesktop] Outra instância já está rodando (mutex). Encerrando.")
        return False

    # Segundo guard: socket local na porta 49152 (só uma instância consegue bind)
    try:
        _SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _SOCKET.bind(("127.0.0.1", 49152))
        _SOCKET.listen(1)
    except OSError as e:
        print(f"[JarvisDesktop] Porta de guarda já em uso ({e}) — outra instância ativa. Encerrando.")
        return False

    # Cleanup ao sair
    def _cleanup():
        try:
            if _SOCKET:
                _SOCKET.close()
        except Exception:
            pass
        try:
            if _MUTEX:
                kernel32.ReleaseMutex(_MUTEX)
                kernel32.CloseHandle(_MUTEX)
        except Exception:
            pass
    atexit.register(_cleanup)
    return True


# ============================================================
# LOG DE BOOT (sob pythonw não há console — arquivo é a única visibilidade)
# ============================================================
def _boot_log(msg):
    try:
        os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)
        with open(os.path.join(ROOT_DIR, "logs", "app_boot.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _excepthook(t, v, tb):
    _boot_log(f"FATAL {t.__name__}: {v}")


sys.excepthook = _excepthook

# Exceções em THREADS (bridge, tray, registro) morriam em silêncio sob pythonw.
try:
    import threading as _th
    def _thread_excepthook(args):
        _boot_log(f"THREAD-ERROR [{args.thread.name if args.thread else '?'}] {args.exc_type.__name__}: {args.exc_value}")
    _th.excepthook = _thread_excepthook
except Exception:
    pass

# Crashes NATIVOS (access violation etc.) viram traceback no arquivo.
try:
    import faulthandler
    faulthandler.enable(open(os.path.join(ROOT_DIR, "logs", "faulthandler.log"), "a", encoding="utf-8"))
except Exception:
    pass


def _session_already_unlocked():
    """PIN já validado nesta sessão do Windows (mesmo boot)? Evita re-PIN em restart automático."""
    try:
        import psutil
        marker = os.path.join(ROOT_DIR, "config", "node_session.json")
        with open(marker, "r", encoding="utf-8") as f:
            data = json.load(f)
        return abs(float(data.get("boot_epoch", 0)) - psutil.boot_time()) < 5
    except Exception:
        return False


def _mark_session_unlocked():
    try:
        import psutil
        os.makedirs(os.path.join(ROOT_DIR, "config"), exist_ok=True)
        with open(os.path.join(ROOT_DIR, "config", "node_session.json"), "w", encoding="utf-8") as f:
            json.dump({"boot_epoch": psutil.boot_time(), "ts": time.time()}, f)
    except Exception:
        pass


# ============================================================
# MAIN APP
# ============================================================
def main():
    _boot_log("=== main() iniciado ===")
    print("=== JARVIS Desktop — Iniciando Nó Windows ===")

    if not ensure_single_instance():
        _boot_log("instância duplicada — encerrando")
        sys.exit(0)

    # PORTÃO PIN (1x POR SESSÃO DO WINDOWS): roda em PROCESSO SEPARADO.
    # Na mesma sessão (app reiniciado pelo keeper), pula direto — sem travar sozinho.
    # Escape-hatch: JARVIS_SKIP_AUTH=1, ou apagar config/pin_auth.json.
    if os.environ.get("JARVIS_SKIP_AUTH") != "1" and not _session_already_unlocked():
        import subprocess
        gate_py = os.path.join(ROOT_DIR, "desktop", "pin_gate_proc.py")
        try:
            rc = subprocess.call([sys.executable, gate_py], cwd=ROOT_DIR)
        except Exception as e:
            _boot_log(f"falha ao lançar portão PIN: {e}")
            print(f"[JarvisDesktop] Falha ao lançar portão PIN ({e}) — encerrando por segurança.")
            return
        if rc != 0:
            _boot_log(f"PIN não confirmado (rc={rc}) — encerrando")
            print("[JarvisDesktop] PIN não confirmado — encerrando.")
            return
        _mark_session_unlocked()
        _boot_log("PIN OK — iniciando node")
    elif _session_already_unlocked():
        _boot_log("sessão já desbloqueada — PIN pulado (restart automático)")

    # SERVIDOR LOCAL (controles do nó: /node, permissões, testes, mic, screenshot)
    # O painel http://127.0.0.1:8080/node depende dele — sem ele a Central do Nó morre.
    def _ensure_local_server():
        try:
            s = socket.create_connection(("127.0.0.1", 8080), timeout=1.0)
            s.close()
            _boot_log("servidor local já ativo (8080)")
            return
        except Exception:
            pass
        try:
            import subprocess
            subprocess.Popen(
                [sys.executable, os.path.join(ROOT_DIR, "server.py")],
                cwd=ROOT_DIR,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            _boot_log("servidor local lançado (server.py, porta 8080)")
        except Exception as e:
            _boot_log(f"falha ao lançar servidor local: {e}")

    _ensure_local_server()

    # Imports pesados depois do guard
    from desktop.config import DesktopConfig
    from desktop.events import EventBus
    from desktop.commands import CommandBus
    from desktop.remote_bridge import RemoteCommandBridge
    from desktop.tray import SystemTrayApp
    from desktop.node_registration import NodeRegistration

    # 1. Configuração
    config = DesktopConfig()
    print(f"[Config] Node ID: {config.get('node', 'node_id')}")
    print(f"[Config] Core URL: {config.get('gateway', 'bridge_url')}")

    # 2. Barramento de eventos interno
    event_bus = EventBus()

    # 3. CommandBus — executa ações locais no Windows
    command_bus = CommandBus(config=config, event_bus=event_bus)

    # 4. Remote Bridge — polling HTTPS do Core → CommandBus
    remote_bridge = RemoteCommandBridge(
        config=config,
        command_bus=command_bus,
        event_bus=event_bus
    )

    # 5. Registro no Painel de Nós (heartbeat a cada 60s)
    node_reg = NodeRegistration()

    # 6. System Tray — ícone + menu + status da ponte
    class CoreRef:
        """Wrapper mínimo para o SystemTrayApp acessar o que precisa."""
        def __init__(self, bridge, ev_bus, reg):
            self.remote_bridge = bridge
            self.event_bus = ev_bus
            self.node_registration = reg
            self.vision_enabled = False

        def stop(self):
            print("[JarvisDesktop] Parando...")
            remote_bridge.stop()
            node_reg.stop()
            if self.event_bus:
                self.event_bus.emit("app.shutdown", {})

        def toggle_vision(self):
            self.vision_enabled = not self.vision_enabled
            print(f"[JarvisDesktop] Visão {'ativada' if self.vision_enabled else 'desativada'}")

        def open_hud_window(self):
            # Abre o HUD web no navegador
            import webbrowser
            url = config.get("gateway", "bridge_url", default="https://jarvis.werikspace.xyz")
            webbrowser.open(url.rstrip("/") + "/hud")

        def open_memory_window(self):
            import webbrowser
            url = config.get("gateway", "bridge_url", default="https://jarvis.werikspace.xyz")
            webbrowser.open(url.rstrip("/") + "/memory")

        def open_node_center(self):
            # Painel de Controle UNIFICADO (saúde + nós + esta máquina) no servidor local.
            import webbrowser
            webbrowser.open("http://127.0.0.1:8080/painel")

    core_ref = CoreRef(remote_bridge, event_bus, node_reg)
    tray = SystemTrayApp(core_ref)

    # 7. Iniciar threads
    print("[JarvisDesktop] Iniciando ponte remota (polling Core)...")
    remote_bridge.start()

    print("[JarvisDesktop] Iniciando registro no Painel de Nós...")
    node_reg.start()

    print("[JarvisDesktop] Iniciando System Tray...")
    tray.start()

    print("[JarvisDesktop] [OK] No Windows ATIVO - aguardando comandos do JARVIS Core")
    print("[JarvisDesktop] Pressione Ctrl+C no console (se houver) ou use o Tray para sair.")

    # 8. Loop principal — mantém o processo vivo
    try:
        while True:
            time.sleep(1)
            # Watchdog: se a ponte cair, o Tray mostra status DISCONNECTED
    except KeyboardInterrupt:
        print("\n[JarvisDesktop] Ctrl+C recebido — encerrando...")
    finally:
        core_ref.stop()
        # O tray.icon.run() bloqueia; stop() é chamado pelo menu "Sair"
        sys.exit(0)


if __name__ == "__main__":
    main()