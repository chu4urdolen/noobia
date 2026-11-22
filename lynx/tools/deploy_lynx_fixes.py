#!/usr/bin/env python3
"""
Deploy Lynx fixes to Alpine userspace once Port 2222 becomes available.
1. Copies lynx-flow to /usr/local/bin/lynx-flow
2. Copies lynx_sense_touch.py to /usr/local/lib/noobia/senses/touch/lynx_sense_touch.py
3. Copies lynx_portrait_display_static to /usr/local/bin/lynx-portrait-display
4. Restarts lynx-senses and lynx-display
5. Runs /usr/local/bin/lynx-flow to verify
"""

import os
import socket
import subprocess
import sys
import time

IP = "192.168.100.107"
PORT = 2222
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "ConnectTimeout=3",
    "-p", str(PORT),
]

def wait_for_port(timeout=600):
    start = time.time()
    print(f"Waiting for {IP}:{PORT}...")
    while time.time() - start < timeout:
        s = socket.socket()
        s.settimeout(2.0)
        try:
            s.connect((IP, PORT))
            s.close()
            print(f"Port {PORT} is OPEN!")
            return True
        except Exception:
            time.sleep(2.0)
    print(f"Timed out waiting for port {PORT}")
    return False

def scp_file(local_path, remote_path):
    cmd = ["scp", "-P", str(PORT), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", local_path, f"root@{IP}:{remote_path}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Failed to scp {local_path} -> {remote_path}: {res.stderr}")
        return False
    print(f"Copied {local_path} -> {remote_path}")
    return True

def ssh_cmd(cmd_str):
    cmd = ["ssh"] + SSH_OPTS + [f"root@{IP}", cmd_str]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Remote command: {cmd_str}\nExit: {res.returncode}\n{res.stdout}\n{res.stderr}")
    return res.returncode == 0

def main():
    if not wait_for_port():
        sys.exit(1)

    # 1. Deploy lynx_flow.py
    if not scp_file("/noobia/lynx/tools/lynx_flow.py", "/usr/local/bin/lynx-flow"):
        sys.exit(2)
    ssh_cmd("chmod +x /usr/local/bin/lynx-flow")

    # 2. Deploy lynx_sense_touch.py
    if not scp_file("/noobia/lynx/senses/touch/lynx_sense_touch.py", "/usr/local/lib/noobia/senses/touch/lynx_sense_touch.py"):
        sys.exit(3)

    # 3. Deploy lynx_portrait_display
    if not scp_file("/tmp/lynx_portrait_display_static", "/usr/local/bin/lynx-portrait-display"):
        sys.exit(4)
    ssh_cmd("chmod +x /usr/local/bin/lynx-portrait-display")

    # 4. Initialize Aigel mode file
    ssh_cmd("mkdir -p /var/lib/noobia && echo normal > /var/lib/noobia/aigel_mode.txt")

    # 5. Deploy anti-reboot safety scripts to replace poweroff-based watchers
    scp_file("/noobia/lynx/linux-port/lynx-battery-reserve.sh", "/usr/libexec/lynx-battery-reserve.sh")
    scp_file("/noobia/lynx/linux-port/lynx-health-supervisor.sh", "/usr/libexec/lynx-health-supervisor.sh")
    scp_file("/noobia/lynx/linux-port/battery-watch.sh", "/run/lynx/battery-watch.sh")
    scp_file("/noobia/lynx/linux-port/thermal-watch.sh", "/run/lynx/thermal-watch.sh")
    scp_file("/noobia/lynx/linux-port/thermal-cooling-watch.sh", "/run/lynx/thermal-cooling-watch.sh")
    ssh_cmd("chmod 755 /usr/libexec/lynx-battery-reserve.sh /usr/libexec/lynx-health-supervisor.sh /run/lynx/*.sh 2>/dev/null || true")

    # 6. Restart services with safe watchers
    ssh_cmd("rc-service lynx-battery-reserve restart || true")
    ssh_cmd("rc-service lynx-health restart || true")
    ssh_cmd("rc-service lynx-senses restart && rc-service lynx-display restart")

    # 7. Run lynx-flow
    print("Running lynx-flow...")
    ssh_cmd("/usr/local/bin/lynx-flow")

if __name__ == "__main__":
    main()
