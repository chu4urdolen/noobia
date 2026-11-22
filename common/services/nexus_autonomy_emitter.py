#!/usr/bin/env python3
"""Nexus Host Autonomy & Health Emitter for Aigel.

Continuously reports Nexus health and liveness to Aigel's intake service (:112)
so Nexus is permanently monitored, active, and never silent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
AUTONOMY_DIR = REPO / "common" / "autonomy"
AIGEL_DIR = REPO / "aigel"

if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

try:
    from aigel_client import AigelClient
except ImportError:
    AigelClient = None

HOSTS_FILE = AIGEL_DIR / "private" / "intake_hosts.json"
ENDPOINT_URL = "http://127.0.0.1:112/api/v1/chunk"
INTERVAL_S = 600.0  # 10 minutes (well within 1800s silence threshold)


def get_nexus_hmac_secret() -> str | None:
    if not HOSTS_FILE.is_file():
        return None
    try:
        data = json.loads(HOSTS_FILE.read_text())
        return data.get("nexus", {}).get("hmac_secret")
    except Exception:
        return None


def get_nexus_metrics() -> dict:
    metrics = {"load": 0.0, "mem_pct": 0, "gpu_temp_c": 0, "gpu_power_w": 0}
    try:
        load = os.getloadavg()[0]
        metrics["load"] = round(load, 2)
    except Exception:
        pass

    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = 0
        mem_avail = 0
        for l in lines:
            if l.startswith("MemTotal:"):
                mem_total = int(l.split()[1])
            elif l.startswith("MemAvailable:"):
                mem_avail = int(l.split()[1])
        if mem_total > 0:
            metrics["mem_pct"] = round((1 - (mem_avail / mem_total)) * 100)
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split(",")
            if len(parts) >= 2:
                metrics["gpu_temp_c"] = int(float(parts[0].strip()))
                metrics["gpu_power_w"] = int(float(parts[1].strip()))
    except Exception:
        pass

    return metrics


def main():
    print("[nexus_autonomy] Starting Nexus autonomy heartbeat emitter...", flush=True)
    secret = get_nexus_hmac_secret()
    if not secret:
        print("[nexus_autonomy] Error: nexus hmac_secret not found in intake_hosts.json", file=sys.stderr)
        return 1

    client = AigelClient(
        endpoint_url=ENDPOINT_URL,
        hmac_secret=secret,
        host_id="nexus",
        timeout_s=10.0,
    )

    while True:
        try:
            metrics = get_nexus_metrics()
            line = (
                f"NOOBIA P0 nexus.health "
                f"gpu_temp={metrics['gpu_temp_c']} "
                f"gpu_power_w={metrics['gpu_power_w']} "
                f"mem_pct={metrics['mem_pct']} "
                f"load={metrics['load']} | "
                f"Nexus heartbeat: load {metrics['load']}, GPU {metrics['gpu_temp_c']}C"
            )
            chunk = {
                "host": "nexus",
                "reason": "heartbeat",
                "lines": [line],
            }
            resp = client.send_chunk(chunk)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Emitted heartbeat -> Aigel decision: {resp.get('decision')}", flush=True)
        except Exception as exc:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] warning: emit failed: {exc}", file=sys.stderr, flush=True)

        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    sys.exit(main())
