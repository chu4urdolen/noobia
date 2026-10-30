#!/usr/bin/env python3
"""Stage the verified August GNSS userspace bundle into Lynx RAM only."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

from lynx_wifi_v19_contact import ssh_command
from prepare_august_gnss_bundle import OUT

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "/run/lynx-gnss-static"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def phone(command, data=None, timeout=25):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((OUT / "manifest.json").read_text())
    if manifest["source_build"] != "CPH2493GDPR_11_13.1.0.561EX01_2023081414430000":
        raise SystemExit("GNSS source build changed")
    for source, info in manifest["files"].items():
        name = Path(source).name
        target = OUT / ("bin" if name == "mnld" else "lib64") / name
        if digest(target) != info["sha256"]:
            raise SystemExit("GNSS bundle file changed: " + name)
    for name, info in manifest["dynamic_libraries"].items():
        if digest(OUT / "lib64" / name) != info["sha256"]:
            raise SystemExit("dynamic GNSS library changed: " + name)
    if digest(OUT / "bin/linker64") != manifest["linker_sha256"] or \
            digest(OUT / "etc/MNL_Config.xml") != manifest["config_sha256"]:
        raise SystemExit("GNSS linker or config changed")
    shim_sha = digest(OUT / "lib64/liblynx_props.so")
    mnld_sha = digest(OUT / "bin/mnld")
    custom_sha = digest(OUT / "lib64/libcustom_nvram.so")
    out = ROOT / "logs" / f"v52-gnss-bundle-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "remote": REMOTE,
              "partition_writes": False, "source_build": manifest["source_build"],
              "mnld_sha256": mnld_sha, "property_shim_sha256": shim_sha,
              "custom_nvram_sha256": custom_sha}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    identity = phone("cat /proc/sys/kernel/random/boot_id; sha256sum /dev/sdc39 | cut -c1-64")
    if identity.returncode or identity.stdout.decode().splitlines()[1:] != [V52_SHA]:
        raise SystemExit("not exact V52 boot")
    report["boot_id"] = identity.stdout.decode().splitlines()[0]
    reuse = phone(f"test -f {REMOTE}/bin/mnld && "
                  f'test "$(sha256sum {REMOTE}/bin/mnld | cut -c1-64)" = {mnld_sha} && '
                  f'test "$(sha256sum {REMOTE}/lib64/liblynx_props.so | cut -c1-64)" = {shim_sha} && '
                  f'test "$(sha256sum {REMOTE}/lib64/libcustom_nvram.so | cut -c1-64)" = {custom_sha}')
    if reuse.returncode == 0:
        report["state"] = "verified-existing-ram-stage"
        save()
        print(json.dumps({"state": report["state"], "receipt": str(out / "result.json")}))
        return
    health = phone("/usr/local/bin/lynx-status --assert-ready")
    if health.returncode or json.loads(health.stdout)["issues"]:
        raise SystemExit("phone health preflight failed")
    free = phone("df -k /run | tail -1 | awk '{print $4}'")
    if free.returncode or int(free.stdout) < 45000:
        raise SystemExit("insufficient RAM staging space")
    if phone(f"test -e {REMOTE}").returncode == 0:
        raise SystemExit("refuse to overwrite existing RAM stage")
    checksums = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and not path.is_symlink():
            checksums.append(f"{digest(path)}  {path.relative_to(OUT)}")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.add(path, arcname=str(path.relative_to(OUT)), recursive=False)
        checksum_data = ("\n".join(checksums) + "\n").encode()
        checksum_info = tarfile.TarInfo("SHA256SUMS")
        checksum_info.mode = 0o600
        checksum_info.size = len(checksum_data)
        archive.addfile(checksum_info, io.BytesIO(checksum_data))
    payload = buffer.getvalue()
    report["tar_bytes"] = len(payload)
    save()
    stage = phone(f"set -eu; mkdir -m 700 {REMOTE}; tar -xf - -C {REMOTE}; "
                  f"cd {REMOTE}; sha256sum -c SHA256SUMS >/dev/null",
                  payload, timeout=60)
    (out / "stage.stderr").write_bytes(stage.stderr)
    if stage.returncode:
        report["state"] = "stage-failed"
        save()
        raise SystemExit("GNSS RAM bundle stage failed")
    report["state"] = "verified-ram-stage"
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json")}))


if __name__ == "__main__":
    main()
