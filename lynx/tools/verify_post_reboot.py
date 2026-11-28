#!/usr/bin/env python3
"""Wait for Lynx to enter Alpine userspace on port 2222 and verify health."""

import subprocess
import time

HOST = "192.168.100.107"
PORT = "2222"


def main():
    print("Waiting for Alpine userspace on port 2222...")
    start = time.time()
    while time.time() - start < 360:
        res = subprocess.run([
            "ssh", "-p", PORT, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=3", f"root@{HOST}", "uptime"
        ], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"Alpine OpenRC is LIVE on port 2222! Uptime: {res.stdout.strip()}")
            break
        time.sleep(5)
    else:
        raise RuntimeError("Timed out waiting for port 2222")

    def run(c):
        r = subprocess.run([
            "ssh", "-p", PORT, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            f"root@{HOST}", c
        ], capture_output=True, text=True, timeout=20)
        return r.stdout.strip()

    print("\n=== OPENRC SERVICES ===")
    for s in ["lynx-display", "lynx-agent-worker", "noobia-autonomyd", "lynx-cellular"]:
        status = run(f"rc-service {s} status")
        print(f"{s}: {status}")

    print("\n=== CELLULAR DATA ===")
    print("ccmni0 addr:", run("ip -4 addr show ccmni0 || true"))
    print("ccmni0 ping 8.8.8.8:", run("ping -I ccmni0 -c 1 8.8.8.8 || echo PING_FAILED"))

    print("\n=== BATTERY & THERMALS ===")
    print(run("cat /sys/bus/i2c/devices/7-0055/battery_snapshot"))

    print("\n=== VERIFIED TOOL ALIAS RUN ===")
    print("read_light_sensor test:", run("printf '{}' | /usr/local/share/lynx/agent-tools/read_light_sensor.sh || true"))
    print("scan_cellular test:", run("printf '{\"action\":\"sim-check\"}' | /usr/local/share/lynx/agent-tools/scan_cellular.sh || true"))


if __name__ == "__main__":
    main()
