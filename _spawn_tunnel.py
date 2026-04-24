"""Lanza cloudflared en segundo plano, captura stdout+stderr y sobrevive a este proceso."""
import subprocess
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
cf = ROOT / "cloudflared.exe"
log = ROOT / "tunnel.log"

# Sobrescribir log limpio
log.write_text("", encoding="utf-8")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS

with open(log, "a", encoding="utf-8", buffering=1) as f:
    p = subprocess.Popen(
        [str(cf), "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"],
        stdout=f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        cwd=str(ROOT),
    )
print(f"Spawned cloudflared PID={p.pid}")
