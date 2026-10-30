#!/usr/bin/env python3
"""Install Lynx's complete keyboard and console scrollbars with V50 rollback."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
OLD_RENDERER = "3a23bdd1c988d535cd0b8609d90a0a2d4e9de5a6aec9450c54b94e4bdfae11db"
NEW_RENDERER = "2ce7523366c02e2578c5d97a93fc1ae02afa61d081a97975ce8009080ed344df"
OLD_BOOTSTRAP = "15c17155d1d227f6fe96aedb7dc2c03ab1a1b80bf393e9b3a1f7eee367d1a0de"
CANDIDATE = "/var/lib/lynx-devroot/tmp/lynx_drm_console_candidate"


def remote(command, data=None, timeout=20):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    return {"returncode": result.returncode,
            "stdout": result.stdout.decode(errors="replace"),
            "stderr": result.stderr.decode(errors="replace")}


def require(label, command, data=None, timeout=20):
    result = remote(command, data, timeout)
    report["steps"].append({"name": label, **result})
    if result["returncode"]:
        raise RuntimeError(f"{label}: {result['stderr'] or result['stdout']}")
    return result["stdout"].strip()


report = {"started_ns": time.time_ns(), "steps": []}
receipt = ROOT / "logs" / f"v50-screen-console-scroll-fix-{report['started_ns']}" / "result.json"
receipt.parent.mkdir(parents=True, exist_ok=True)
installed = False

try:
    source = (ROOT / "linux-port/lynx-display-bootstrap.sh").read_bytes()
    new_bootstrap = hashlib.sha256(source).hexdigest()
    if NEW_RENDERER.encode() not in source or OLD_RENDERER.encode() in source:
        raise RuntimeError("local bootstrap renderer pin is wrong")
    preflight = require("preflight", "set -eu; "
        "sha256sum /dev/sdc39 /usr/local/bin/lynx-portrait-display "
        "/usr/local/bin/lynx-display-bootstrap " + CANDIDATE + "; "
        "rc-service lynx-display status; /usr/local/bin/lynx-status --assert-ready")
    lines = preflight.splitlines()
    expected = [BOOT, OLD_RENDERER, OLD_BOOTSTRAP, NEW_RENDERER]
    actual = [line.split()[0] for line in lines[:4]]
    if actual != expected:
        raise RuntimeError(f"pinned image/files changed: {actual}")
    health = json.loads(next(line for line in lines if line.startswith('{')))
    battery = health["battery"]
    if (health["issues"] or battery["capacity_percent"] < 25 or
            battery["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("battery, thermal, or Alpine health preflight failed")
    report["boot_id"] = health["boot_id"]
    report["battery_percent"] = battery["capacity_percent"]
    require("stage_bootstrap", "set -eu; "
        "cat > /usr/local/bin/lynx-display-bootstrap.nav.new; "
        "sh -n /usr/local/bin/lynx-display-bootstrap.nav.new; "
        "test \"$(sha256sum /usr/local/bin/lynx-display-bootstrap.nav.new | cut -c1-64)\" = "
        + new_bootstrap, source)
    script = f"""set -eu
test "$(sha256sum /dev/sdc39 | cut -c1-64)" = {BOOT}
test "$(sha256sum /usr/local/bin/lynx-portrait-display | cut -c1-64)" = {OLD_RENDERER}
test "$(sha256sum /usr/local/bin/lynx-display-bootstrap | cut -c1-64)" = {OLD_BOOTSTRAP}
test "$(sha256sum {CANDIDATE} | cut -c1-64)" = {NEW_RENDERER}
test "$(sha256sum /usr/local/bin/lynx-display-bootstrap.nav.new | cut -c1-64)" = {new_bootstrap}
cp -p /usr/local/bin/lynx-portrait-display /usr/local/bin/lynx-portrait-display.before-console-scroll-fix
cp -p /usr/local/bin/lynx-display-bootstrap /usr/local/bin/lynx-display-bootstrap.before-console-scroll-fix
rollback() {{
    cp -p /usr/local/bin/lynx-portrait-display.before-console-scroll-fix /usr/local/bin/lynx-portrait-display
    cp -p /usr/local/bin/lynx-display-bootstrap.before-console-scroll-fix /usr/local/bin/lynx-display-bootstrap
    rc-service lynx-display start || true
}}
trap rollback EXIT
rc-service lynx-display stop
cp {CANDIDATE} /usr/local/bin/lynx-portrait-display.nav.new
chmod 755 /usr/local/bin/lynx-portrait-display.nav.new
mv /usr/local/bin/lynx-portrait-display.nav.new /usr/local/bin/lynx-portrait-display
chmod 755 /usr/local/bin/lynx-display-bootstrap.nav.new
mv /usr/local/bin/lynx-display-bootstrap.nav.new /usr/local/bin/lynx-display-bootstrap
timeout 65 rc-service lynx-display start
rc-service lynx-display status
/usr/local/bin/lynx-status --assert-ready >/dev/null
test "$(sha256sum /usr/local/bin/lynx-portrait-display | cut -c1-64)" = {NEW_RENDERER}
test "$(sha256sum /usr/local/bin/lynx-display-bootstrap | cut -c1-64)" = {new_bootstrap}
trap - EXIT
echo NAV_INSTALLED
"""
    require("install_and_start", script, timeout=110)
    installed = True
    require("postcheck", "set -eu; rc-service lynx-display status; "
            "/usr/local/bin/lynx-displayctl status; "
            "/usr/local/bin/lynx-display-bootstrap --check-files; "
            "/usr/local/bin/lynx-status --assert-ready >/dev/null", timeout=30)
    report["result"] = "installed-and-running"
except Exception as exc:
    report["result"] = "failed-or-rolled-back"
    report["error"] = str(exc)
    if installed:
        report["rollback"] = remote(
            "set -eu; rc-service lynx-display stop; "
            "cp -p /usr/local/bin/lynx-portrait-display.before-console-scroll-fix "
            "/usr/local/bin/lynx-portrait-display; "
            "cp -p /usr/local/bin/lynx-display-bootstrap.before-console-scroll-fix "
            "/usr/local/bin/lynx-display-bootstrap; "
            "rc-service lynx-display start", timeout=95)
finally:
    report["finished_ns"] = time.time_ns()
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "receipt": str(receipt)}))
if report["result"] != "installed-and-running":
    sys.exit(1)
