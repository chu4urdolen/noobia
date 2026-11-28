#!/usr/bin/env python3
"""Deploy intuitive tool aliases, autonomy triggers, and updated UI to Lynx."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

TOOLS_LOCAL = Path("/noobia/lynx/tools/local_calls")
AGENT_PY = Path("/noobia/lynx/tools/agent/lynx_agent.py")
TRIGGER_PY = Path("/noobia/common/autonomy/trigger.py")
PROFILE_PY = Path("/noobia/common/autonomy/profile.py")
DEBUG_HELPER_PY = Path("/noobia/lynx/tools/lynx_debug_helper.py")
PATTERNS_JSON = Path("/noobia/lynx/autonomy/patterns-lynx.json")
DISPLAY_C = Path("/noobia/lynx/tools/lynx_drm_dmabuf_pattern.c")

HOST = "192.168.100.107"
PORT = "2222"


def ssh(cmd, stdin_data=None, timeout=60):
    argv = [
        "ssh", "-p", PORT,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{HOST}", cmd
    ]
    res = subprocess.run(argv, input=stdin_data, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        err = res.stderr.decode(errors="replace")
        raise RuntimeError(f"SSH failed ({res.returncode}): {err}")
    return res.stdout.decode("utf-8")


def main():
    print("1. Packing files into tar archive...")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # All local tool wrappers & manifests
        for f in TOOLS_LOCAL.iterdir():
            if f.is_file() and (f.suffix in [".sh", ".json"]):
                ti = tarfile.TarInfo(name=f"agent-tools/{f.name}")
                data = f.read_bytes()
                ti.size = len(data)
                ti.mode = 0o755 if f.suffix == ".sh" else 0o644
                tar.addfile(ti, io.BytesIO(data))

        # lynx-agent
        data = AGENT_PY.read_bytes()
        ti = tarfile.TarInfo(name="bin/lynx-agent")
        ti.size = len(data)
        ti.mode = 0o755
        tar.addfile(ti, io.BytesIO(data))

        # trigger.py & profile.py & patterns-lynx.json
        for src, name in [
            (TRIGGER_PY, "autonomy/trigger.py"),
            (PROFILE_PY, "autonomy/profile.py"),
            (PATTERNS_JSON, "autonomy/patterns-lynx.json"),
        ]:
            data = src.read_bytes()
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))

        # debug helper
        data = DEBUG_HELPER_PY.read_bytes()
        ti = tarfile.TarInfo(name="bin/lynx-debug-helper")
        ti.size = len(data)
        ti.mode = 0o755
        tar.addfile(ti, io.BytesIO(data))

        # display C source
        data = DISPLAY_C.read_bytes()
        ti = tarfile.TarInfo(name="tmp/lynx-status-hardware.c")
        ti.size = len(data)
        ti.mode = 0o644
        tar.addfile(ti, io.BytesIO(data))

    archive_bytes = buf.getvalue()
    print(f"Archive ready: {len(archive_bytes)} bytes.")

    print("2. Uploading archive to Lynx /tmp/deploy.tar.gz...")
    ssh("cat > /tmp/deploy.tar.gz", stdin_data=archive_bytes)

    print("3. Unpacking files on Lynx...")
    unpack_cmd = (
        "tar -xzf /tmp/deploy.tar.gz -C /tmp/ && "
        "cp -p /tmp/agent-tools/* /usr/local/share/lynx/agent-tools/ && "
        "chmod 755 /usr/local/share/lynx/agent-tools/*.sh && "
        "chmod 644 /usr/local/share/lynx/agent-tools/*.json && "
        "cp -p /tmp/bin/lynx-agent /usr/local/bin/lynx-agent && "
        "chmod 755 /usr/local/bin/lynx-agent && "
        "cp -p /tmp/bin/lynx-debug-helper /usr/local/bin/lynx-debug-helper && "
        "chmod 755 /usr/local/bin/lynx-debug-helper && "
        "cp -p /tmp/autonomy/trigger.py /usr/local/lib/noobia/autonomy/trigger.py && "
        "cp -p /tmp/autonomy/profile.py /usr/local/lib/noobia/autonomy/profile.py && "
        "cp -p /tmp/autonomy/patterns-lynx.json /usr/local/lib/noobia/autonomy/patterns-lynx.json && "
        "cp -p /tmp/tmp/lynx-status-hardware.c /var/lib/lynx-devroot/tmp/lynx-status-hardware.c"
    )
    ssh(unpack_cmd)
    print("Files unpacked and installed.")

    print("4. Updating /etc/noobia/noob.json on Lynx...")
    update_profile_py = (
        "import json; from pathlib import Path; "
        "p = Path('/etc/noobia/noob.json'); "
        "d = json.loads(p.read_text()) if p.is_file() else {'name': 'lynx'}; "
        "win = d.setdefault('window', {}); "
        "win['priority_mode'] = 'sum'; "
        "win['priority_threshold'] = 20; "
        "win['window_s'] = 60.0; "
        "win['max_lines'] = 15; "
        "p.write_text(json.dumps(d, indent=2) + '\\n'); "
        "print('noob.json window:', json.dumps(win))"
    )
    print(ssh(f"python3 -c \"{update_profile_py}\"").strip())

    print("5. Merging patterns into /var/lib/noobia/autonomy/patterns.json...")
    merge_py = """
import json
from pathlib import Path

live_p = Path('/var/lib/noobia/autonomy/patterns.json')
repo_p = Path('/usr/local/lib/noobia/autonomy/patterns-lynx.json')

live = json.loads(live_p.read_text()) if live_p.is_file() else {'store': [], 'archive': []}
repo = json.loads(repo_p.read_text())

live_store = {p.get('id', p.get('name')): p for p in live.get('store', [])}
merged_store = []

for p in repo.get('store', []):
    pid = p.get('id', p.get('name'))
    if pid in live_store:
        existing = live_store.pop(pid)
        p['hits'] = existing.get('hits', 0)
        p['last_hit'] = existing.get('last_hit', 0)
    merged_store.append(p)

for remaining in live_store.values():
    merged_store.append(remaining)

live['store'] = merged_store
live['store_capacity'] = max(live.get('store_capacity', 200), len(merged_store) + 50)
live_p.write_text(json.dumps(live, indent=2) + '\\n')
print(f'Patterns merged: {len(merged_store)} active patterns.')
"""
    print(ssh("python3 -", stdin_data=merge_py.encode("utf-8")).strip())

    print("6. Compiling UI binary in devroot chroot...")
    compile_cmd = (
        "chroot /var/lib/lynx-devroot /usr/bin/gcc -std=c11 -O2 -Wall -Wextra -Werror "
        "-I/usr/include/libdrm /tmp/lynx-status-hardware.c -ldrm -l:libz.so.1 -o /tmp/lynx-status-hardware"
    )
    ssh(compile_cmd)
    print("Compilation successful.")

    print("7. Running UI self-tests in devroot chroot...")
    test_out1 = ssh("chroot /var/lib/lynx-devroot /tmp/lynx-status-hardware --self-test-touch")
    print("Self-test touch:", test_out1.strip())
    test_out2 = ssh("chroot /var/lib/lynx-devroot /tmp/lynx-status-hardware --self-test-console-keys")
    print("Self-test console keys:", test_out2.strip())

    print("8. Installing binary to /usr/local/bin/lynx-portrait-display...")
    install_ui_cmd = (
        "cp /usr/local/bin/lynx-portrait-display /usr/local/bin/lynx-portrait-display.bak-pre-status-merge 2>/dev/null || true; "
        "cp /var/lib/lynx-devroot/tmp/lynx-status-hardware /usr/local/bin/lynx-portrait-display && "
        "chmod 755 /usr/local/bin/lynx-portrait-display"
    )
    ssh(install_ui_cmd)

    print("9. Restarting lynx-display service...")
    restart_out = ssh("rc-service lynx-display restart && rc-service lynx-display status")
    print(restart_out.strip())

    print("10. Restarting noobia-autonomyd service...")
    autonomyd_out = ssh("rc-service noobia-autonomyd restart && rc-service noobia-autonomyd status")
    print(autonomyd_out.strip())

    print("Deployment completed successfully!")


if __name__ == "__main__":
    main()
