"""
Jarvis Desktop - Remote Command Bridge
Ponte de comandos do J.A.R.V.I.S. (Zima) para este PC Windows:
- Faz polling HTTP do Core Server (https://jarvis.werikspace.xyz/api/remote/poll)
- Executa os comandos recebidos no CommandBus local (controle total do Windows)
- Devolve o resultado para /api/remote/result, que envia ao agente
- Publica status da conexão Windows → JARVIS Core na EventBus.
Autenticação via header X-Bridge-Secret (via env, sem padrão embutido).
"""

import os
import json
import time
import urllib.request
import urllib.error
import threading


def _log(msg: str):
    try:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(os.path.join(app_dir, "logs"), exist_ok=True)
        with open(os.path.join(app_dir, "logs", "remote_bridge.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _http_json(url, method="GET", payload=None, secret="", timeout=10):
    headers = {"X-Bridge-Secret": secret}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class RemoteCommandBridge(threading.Thread):
    def __init__(self, config=None, command_bus=None, event_bus=None):
        super().__init__(daemon=True, name="JarvisRemoteBridge")
        self.config = config
        self.command_bus = command_bus
        self.event_bus = event_bus
        self.status = "DISCONNECTED"
        self._running = True
        url = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz")
        if config:
            url = config.get("gateway", "bridge_url", default=url)
            self._secret = config.get("gateway", "token")
        else:
            self._secret = None  # sem segredo: ponte fica DISCONNECTED até configurar
        raw = (url or "").strip()
        if raw.startswith("wss://"):
            raw = "https://" + raw.split("wss://", 1)[1]
        elif raw.startswith("ws://"):
            raw = "http://" + raw.split("ws://", 1)[1]
        raw = raw.rstrip("/")
        if not raw:
            raw = "https://jarvis.werikspace.xyz"
        self.base_url = raw
        self.poll_interval = 0.25
        self.fails = 0
        self._in_flight = False
        self.node_id = ""
        if config:
            self.node_id = (config.get("node", "node_id", default="") or "").strip().lower()

    def set_status(self, new_status):
        if self.status != new_status:
            self.status = new_status
            _log(f"Status da ponte: {new_status}")
            if self.event_bus:
                payload = {"status": new_status, "url": self.base_url, "ts": time.time()}
                self.event_bus.emit("bridge.status", payload)

    def run(self):
        print(f"[RemoteBridge] Polling de comandos em {self.base_url}/api/remote/poll (intervalo {self.poll_interval}s)")
        _log(f"Poller iniciado -> {self.base_url} (segredo ok={bool(self._secret)})")
        while self._running:
            # Cada ciclo roda em thread própria com PRazo duro (9s):
            # travamento de rede (DNS/TCP) não trava o poller — o loop segue.
            if not self._in_flight:
                self._in_flight = True
                t = threading.Thread(target=self._cycle, daemon=True, name="JarvisBridgeCycle")
                t.start()
                # Watchdog: se o ciclo não terminar em 9s, libera a trava mesmo assim
                def _watchdog(thread=t):
                    thread.join(timeout=9)
                    if self._in_flight and thread.is_alive():
                        _log("cycle travado >9s — liberando trava (ciclo abandonado)")
                        self._in_flight = False
                threading.Thread(target=_watchdog, daemon=True).start()
            time.sleep(self.poll_interval)

    def _cycle(self):
        try:
            res = _http_json(f"{self.base_url}/api/remote/poll", method="POST",
                             payload={"node": "windows", "node_id": self.node_id},
                             secret=self._secret, timeout=6)
            commands = res.get("commands") or []
            if self.fails > 0 or self.status != "CONNECTED":
                _log(f"Poll OK após {self.fails} falha(s) — ponte reconectada")
            self.fails = 0
            self.set_status("CONNECTED")
            if commands:
                _log(f"cycle FETCH {len(commands)} comandos")
            for cmd in commands:
                self._execute_and_report(cmd)
        except Exception as e:
            self.fails += 1
            if self.fails >= 3:
                self.set_status("DISCONNECTED")
            _log(f"cycle fail {self.fails}: {type(e).__name__}: {str(e)[:120]}")
        finally:
            self._in_flight = False

    def _execute_and_report(self, cmd):
        cmd_id = str(cmd.get("id", ""))
        action = str(cmd.get("action", "")).strip()
        params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
        print(f"[RemoteBridge] Comando do J.A.R.V.I.S. (Zima): '{action}' (id {cmd_id})")
        _log(f"Comando recebido: '{action}' (id {cmd_id})")
        try:
            result = self.command_bus.execute(action, params, origin="jarvis-zima")
        except Exception as e:
            result = {"success": False, "error": str(e)}
        _log(f"Resultado de '{action}': {json.dumps(result, ensure_ascii=False)[:300]}")
        try:
            _http_json(f"{self.base_url}/api/remote/result", method="POST",
                       payload={"id": cmd_id, "ok": bool(result.get("success", False)), "result": result},
                       secret=self._secret, timeout=8)
        except Exception as e:
            print(f"[RemoteBridge] Falha ao reportar resultado do comando {cmd_id}: {e}")
            _log(f"Falha ao reportar resultado {cmd_id}: {e}")

    def stop(self):
        self._running = False
