"""
Jarvis Desktop - Background Watchers
Monitores contínuos de baixo consumo no Windows:
1. ClipboardWatcher: Detecta alterações na área de transferência (Ctrl+C).
2. ActiveWindowWatcher: Detecta mudanças na janela em primeiro plano.
3. SystemMonitorWatcher: Monitora CPU, GPU, RAM, Disco e Uptime.
"""

import time
import threading
import psutil
import pyperclip
import win32gui
import win32process

import hardware_control as hc

class ClipboardWatcher:
    def __init__(self, event_bus, poll_interval: float = 1.0):
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._last_content = ""
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            self._last_content = pyperclip.paste()
        except Exception:
            self._last_content = ""
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ClipboardWatcher")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                current = pyperclip.paste()
                if current and current != self._last_content:
                    self._last_content = current
                    # Emite evento se o texto for razoável (até 2000 chars)
                    summary = current[:100] + "..." if len(current) > 100 else current
                    self.event_bus.emit("clipboard.changed", {
                        "text": current[:2000],
                        "summary": summary,
                        "length": len(current)
                    })
            except Exception:
                pass
            time.sleep(self.poll_interval)

class ActiveWindowWatcher:
    def __init__(self, event_bus, poll_interval: float = 1.5):
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._last_hwnd = None
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ActiveWindowWatcher")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd and hwnd != self._last_hwnd:
                    self._last_hwnd = hwnd
                    title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    p_name = ""
                    try:
                        p_name = psutil.Process(pid).name()
                    except Exception:
                        pass
                    if title:
                        self.event_bus.emit("window.changed", {
                            "hwnd": hwnd,
                            "title": title,
                            "process_id": pid,
                            "application": p_name
                        })
            except Exception:
                pass
            time.sleep(self.poll_interval)

class SystemMonitorWatcher:
    def __init__(self, event_bus, poll_interval: float = 4.0):
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SystemMonitorWatcher")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                telemetry = hc.get_hardware_telemetry()
                self.event_bus.emit("system.telemetry", telemetry)
            except Exception:
                pass
            time.sleep(self.poll_interval)
