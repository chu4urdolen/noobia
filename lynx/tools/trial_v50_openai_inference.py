#!/usr/bin/env python3
"""Run one keyless-on-disk OpenAI inference probe from Lynx using Rose's key."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_inference_probe.py"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
REMOTE = "/run/lynx-inference-probe.py"


def phone(command, data=None, timeout=40):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def rose_settings():
    # stdout is held only in this process; never print the credential or log it.
    source = ("import json,pathlib\n"
              "p=pathlib.Path.home()/'.config/rose-chat/settings.json'\n"
              "d=json.loads(p.read_text())\n"
              "print(json.dumps({'key':d.get('api_key',''),'model':d.get('model','')}))\n")
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                             "rose", "python3 -"], input=source.encode(),
                            capture_output=True, timeout=12)
    if result.returncode:
        raise RuntimeError("Rose's Syra host or private settings are unavailable")
    data = json.loads(result.stdout)
    key = data.get("key", "")
    model = data.get("model") or "gpt-5.4-mini"
    if not isinstance(key, str) or not key or len(key) > 512:
        raise RuntimeError("Rose's API credential is unavailable")
    if not isinstance(model, str) or not model.isascii() or not model.replace("-", "").replace(".", "").isalnum():
        raise RuntimeError("Rose's model setting is invalid")
    return key, model


def main():
    receipt = ROOT / "logs" / f"v50-openai-inference-{time.time_ns()}.json"
    report = {"state": "preflight", "api_calls_requested": 0,
              "credential_written_to_disk": False, "boot_partition_writes": False,
              "phone_script_removed": False}
    staged = False
    try:
        identity = phone("uname -r; sha256sum /dev/sdc39; "
                         "/usr/local/bin/lynx-status --assert-ready", timeout=20)
        if identity.returncode:
            raise RuntimeError("Lynx identity or health check failed")
        lines = identity.stdout.decode().splitlines()
        if (lines[0] != "5.10.149-android12-9-o-g311738fbb5a8" or
            lines[1].split()[0] != BOOT):
            raise RuntimeError("Lynx is not on verified V50")
        health = json.loads(next(line for line in lines if line.startswith("{")))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("Lynx health guard failed")
        report["boot_id"] = health["boot_id"]
        key, model = rose_settings()
        report["model_requested"] = model
        source = SOURCE.read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        staged = True
        stage = phone(f"umask 077; cat > {REMOTE}; "
                      f'test "$(sha256sum {REMOTE} | cut -c1-64)" = {digest}; '
                      f"/usr/bin/python3 -m py_compile {REMOTE}", source, timeout=25)
        if stage.returncode:
            raise RuntimeError("Lynx probe staging failed")
        report["api_calls_requested"] = 1
        run = phone(f"/usr/bin/python3 {REMOTE} --model {model}",
                    (key + "\n").encode(), timeout=45)
        key = None
        try:
            answer = json.loads(run.stdout)
        except ValueError:
            raise RuntimeError("Lynx probe returned invalid JSON") from None
        if run.returncode or answer.get("ok") is not True:
            raise RuntimeError(answer.get("error", "Lynx inference request failed"))
        report["response"] = answer
        report["state"] = "inference-confirmed"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        if staged:
            cleanup = phone(f"rm -f {REMOTE} /run/__pycache__/lynx-inference-probe.*.pyc; "
                            f"test ! -e {REMOTE}", timeout=15)
            report["phone_script_removed"] = cleanup.returncode == 0
        receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "answer": report.get("response", {}).get("answer"),
                      "error": report.get("error")}))
    if report["state"] != "inference-confirmed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
