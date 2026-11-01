import subprocess
import sys
import os

python_exe = sys.executable
main_py = r"c:\JARVIS\jarvis-windows\main.py"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

p = subprocess.Popen(
    [python_exe, main_py],
    cwd=r"c:\JARVIS\jarvis-windows",
    creationflags=flags,
    close_fds=True
)

print(f"J.A.R.V.I.S. launched live with PID: {p.pid}")
