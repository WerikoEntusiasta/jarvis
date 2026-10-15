"""
Registro do Nó Windows no Painel de Nós do J.A.R.V.I.S. (ZimaOS).
Registra o PC e envia heartbeat periódico para o painel marcar como online.
"""

import os
import json
import time
import socket
import threading
import urllib.request
import urllib.error

NODE_PANEL_URL = os.environ.get("NODE_PANEL_URL", "http://127.0.0.1:8090")
JARVIS_MASTER_KEY = os.environ.get("JARVIS_MASTER_KEY", os.environ.get("MASTER_ACCESS_KEY", ""))
HEARTBEAT_SEC = 60.0


class NodeRegistration:
    """Registra este PC no Painel de Nós (upsert por id) e reenvia como heartbeat a cada HEARTBEAT_SEC."""

    def __init__(self):
        self.node_id = f"jarvis-pc-{socket.gethostname().lower()}"
        self.name = os.environ.get("NODE_NAME", socket.gethostname())
        self.owner = os.environ.get("NODE_OWNER", "Werik")
        self.last_ok = None
        self._running = False
        self._thread = None
        self._announced = False
        self._fail_streak = 0
        self._last_err = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="JarvisNodeRegistration")
        self._thread.start()

    def _loop(self):
        while self._running:
            try:
                # Core primeiro (painel pode estar fora do ar — registro independente)
                core_ok = self._register_core()
                panel_ok = self._register()
                if core_ok or panel_ok:
                    self.last_ok = time.time()
                    if not self._announced:
                        self._announced = True
                        print(f"[NodeRegistration] Nó Windows registrado (core={core_ok} painel={panel_ok}): {self.node_id}")
                    self._fail_streak = 0
                else:
                    self._fail_streak += 1
                    if self._fail_streak == 1:
                        print(f"[NodeRegistration] Nenhum destino aceitou o registro: {self._last_err}")
            except Exception as e:
                self._fail_streak += 1
                if self._fail_streak == 1:
                    print(f"[NodeRegistration] Painel de nós indisponível: {e}")
            # Dorme em fatias de 1s para o stop() valer dentro de um ciclo
            slept = 0.0
            while self._running and slept < HEARTBEAT_SEC:
                time.sleep(1.0)
                slept += 1.0

    def _register(self):
        payload = json.dumps({
            "id": self.node_id,
            "name": self.name,
            "type": "pc",
            "owner": self.owner,
            "meta": {"os": "windows", "app": "jarvis-desktop"}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{NODE_PANEL_URL.rstrip('/')}/api/nodes",
            data=payload,
            headers={"Content-Type": "application/json", "X-Master-Key": JARVIS_MASTER_KEY},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read().decode("utf-8", "replace")
            data = json.loads(body) if body.strip() else {}
            self._last_err = ""
            self._register_core()
            return bool(data.get("ok", True))
        except Exception as e:
            self._last_err = f"{type(e).__name__}: {e}"
            return False

    def _register_core(self):
        """Espelha o registro no Núcleo (melhor esforço; nunca quebra o fluxo)."""
        try:
            base = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz").rstrip("/")
            # Token: env primeiro; se ausente (boot via VBS sem env), usa o config salvo do app
            token = os.environ.get("BRIDGE_SECRET") or os.environ.get("OPENCLAW_GATEWAY_TOKEN") or self._config_token()
            payload = json.dumps({"id": self.node_id, "name": self.name, "type": "pc", "owner": self.owner}).encode("utf-8")
            req = urllib.request.Request(
                base + "/api/nodes/register",
                data=payload,
                headers={"Content-Type": "application/json", "X-Bridge-Secret": token},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8):
                return True
        except Exception:
            return False

    def _config_token(self):
        """Lê o token da ponte do config salvo do app (gateway.token)."""
        try:
            cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "jarvis_desktop_config.json")
            with open(cfg, "r", encoding="utf-8") as f:
                return (json.load(f).get("gateway") or {}).get("token") or ""
        except Exception:
            return ""

    def stop(self):
        self._running = False

    def status(self):
        return {
            "node_id": self.node_id,
            "panel_url": NODE_PANEL_URL,
            "last_ok": self.last_ok
        }


if __name__ == "__main__":
    reg = NodeRegistration()
    if reg._register():
        print(f"[NodeRegistration] Nó Windows registrado no painel: {reg.node_id}")
    else:
        print(f"[NodeRegistration] Painel de nós indisponível: {reg._last_err}")
    print("Status:", reg.status())
