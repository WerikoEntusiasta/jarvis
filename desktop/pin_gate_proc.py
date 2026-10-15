"""Portão PIN em PROCESSO SEPARADO.

O node (app.py) chama isto como subprocesso e espera o exit code:
  0 = PIN ok (ou criado agora)  -> node sobe
  2 = cancelado / falha        -> node encerra

Motivo da separação: o teardown do Qt sob pythonw no mesmo processo do
node derrubava tudo em silêncio. Aqui o Qt vive e morre sozinho, sem
levar o node junto.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Sob pythonw não há stdout/stderr: garante registro do que acontecer aqui
try:
    if sys.stdout is None or sys.stderr is None:
        log_dir = os.path.join(ROOT, "logs")
        os.makedirs(log_dir, exist_ok=True)
        fh = open(os.path.join(log_dir, "pin_gate.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = fh
        if sys.stderr is None:
            sys.stderr = fh
except Exception:
    pass

from desktop.pin_pad import run_pin_gate

try:
    ok = run_pin_gate()
except Exception as e:
    print(f"[PinGate] exceção: {type(e).__name__}: {e}")
    ok = False

print(f"[PinGate] resultado: {ok}")
sys.exit(0 if ok else 2)
