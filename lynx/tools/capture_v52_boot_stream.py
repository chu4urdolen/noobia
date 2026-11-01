#!/usr/bin/env python3
"""Pinned read-only rescue SSH kernel stream across a guarded V52 boot."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command
from lynx_presence import usb_probe


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress

V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
ADDRESS = "192.168.100.107"
V52_IMAGE = PORT / "artifacts/bt-before-wifi-v52-offline/nord3-bt-before-wifi-v52-untested.img"
V53_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
V53_IMAGE = PORT / "artifacts/bt-precal-settle-v53-offline/nord3-bt-precal-settle-v53-untested.img"
CANDIDATES = {"v52": (V52_IMAGE, V52_SHA), "v53": (V53_IMAGE, V53_SHA)}


def beacon_identity(candidate_image, candidate_sha):
    """Read the exact image's expected rescue beacon without exposing its token."""
    image = candidate_image.read_bytes()
    if hashlib.sha256(image).hexdigest() != candidate_sha:
        raise RuntimeError("candidate image hash mismatch")
    primary = read_newc(decompress(read_boot_v4(image)["ramdisk"]))
    size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset = recipe["payload_offset"]
    supplement = read_newc(gzip.decompress(image[offset:offset + size]))
    token = primary["etc/lynx/session-token"]["data"].strip()
    host = supplement["etc/lynx/host-ip"]["data"].strip().decode("ascii")
    if len(token) != 32 or any(byte not in b"0123456789abcdef" for byte in token):
        raise RuntimeError("unexpected V52 beacon token")
    if host != "192.168.100.106":
        raise RuntimeError("unexpected V52 beacon destination")
    return b"LYNX_HELLO " + token, host


def phone(command, port, timeout=7):
    argv = ssh_command(ADDRESS, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--candidate", choices=CANDIDATES, default="v52")
    parser.add_argument("--seconds", type=int, default=420)
    args = parser.parse_args()
    if not 240 <= args.seconds <= 600:
        parser.error("seconds must be 240..600")
    if not args.capture:
        print(json.dumps({"state": "offline-plan", "phone_writes": False,
                          "stream": "pinned rescue SSH port 22 cat /dev/kmsg",
                          "beacon": "passive UDP 5514 before rescue SSH",
                          "seconds": args.seconds}))
        return
    candidate_image, candidate_sha = CANDIDATES[args.candidate]
    expected_beacon, collector_ip = beacon_identity(candidate_image, candidate_sha)
    os.umask(0o077)
    out = ROOT / "logs" / f"{args.candidate}-live-boot-stream-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "waiting-rescue-ssh", "phone_writes": False,
              "expected_boot_sha256": candidate_sha, "seconds": args.seconds,
              "events": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def event(name, **fields):
        record = {"event": name, "elapsed_seconds": round(time.monotonic() - start, 2),
                  **fields}
        report["events"].append(record)
        with (out / "events.jsonl").open("a") as target:
            target.write(json.dumps(record) + "\n")
        save()

    start = time.monotonic()
    deadline = start + args.seconds
    stream = stdout = stderr = listener = None
    beacon_seen = False
    save()
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind((collector_ip, 5514))
        listener.setblocking(False)

        def poll_beacon():
            nonlocal beacon_seen
            while True:
                try:
                    payload, peer = listener.recvfrom(128)
                except BlockingIOError:
                    return
                if not beacon_seen and peer[0] == ADDRESS and \
                        payload.strip() == expected_beacon:
                    beacon_seen = True
                    event("token-matched-wifi-beacon", source_ip=peer[0])

        while time.monotonic() < deadline:
            try:
                proof = phone("cat /proc/sys/kernel/random/boot_id; "
                              "sha256sum /dev/sdc39 | cut -c1-64; "
                              "readlink /proc/1/exe", 22)
            except (OSError, subprocess.TimeoutExpired):
                proof = None
            if proof and proof.returncode == 0:
                lines = proof.stdout.splitlines()
                if len(lines) >= 3 and lines[1] == candidate_sha and \
                        lines[2] == "/bin/busybox":
                    report["boot_id"] = lines[0]
                    event("rescue-identity-confirmed", boot_id=lines[0])
                    break
            poll_beacon()
            if usb_probe()["fastboot_usb"] and time.monotonic() - start > 10:
                event("fastboot-before-rescue")
                report["state"] = "fastboot-before-rescue"
                return
            time.sleep(3)
        else:
            report["state"] = "rescue-ssh-timeout"
            return
        stdout = (out / "kmsg-live.raw").open("wb")
        stderr = (out / "kmsg-live.stderr").open("wb")
        argv = ssh_command(ADDRESS, "cat /dev/kmsg")
        argv[-2:-2] = ["-p", "22"]
        stream = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                                  stderr=stderr, start_new_session=True)
        time.sleep(1)
        if stream.poll() is not None:
            raise RuntimeError("kernel stream exited immediately")
        report["state"] = "streaming"
        event("kernel-stream-started", pid=stream.pid)
        next_snapshot = time.monotonic()
        alpine_seen_at = None
        stream_ended = False
        while time.monotonic() < deadline:
            poll_beacon()
            if time.monotonic() >= next_snapshot:
                try:
                    snapshot = phone("cat /run/lynx/boot.log 2>/dev/null || true", 22)
                    (out / f"boot-{len(report['events'])}.log").write_text(snapshot.stdout)
                    event("boot-log-snapshot", bytes=len(snapshot.stdout),
                          ssh_exit=snapshot.returncode)
                except (OSError, subprocess.TimeoutExpired):
                    event("boot-log-snapshot-unavailable")
                next_snapshot = time.monotonic() + 30
            if (out / "kmsg-live.raw").stat().st_size > 32 * 1024 * 1024:
                report["state"] = "stream-size-limit"
                break
            if usb_probe()["fastboot_usb"]:
                event("usb-fastboot-observed")
                report["state"] = "fastboot-after-rescue"
                break
            try:
                alpine = phone("cat /proc/sys/kernel/random/boot_id; "
                               "/usr/local/bin/lynx-status --assert-ready", 2222, 5)
            except (OSError, subprocess.TimeoutExpired):
                alpine = None
            if alpine and alpine.returncode == 0 and \
                    alpine.stdout.splitlines()[0] == report["boot_id"]:
                if alpine_seen_at is None:
                    alpine_seen_at = time.monotonic()
                    (out / "alpine-health.json").write_text(alpine.stdout.splitlines()[1] + "\n")
                    event("alpine-healthy")
                elif time.monotonic() - alpine_seen_at >= 30:
                    report["state"] = "alpine-stable-30-seconds"
                    break
            if not stream_ended and stream.poll() is not None:
                event("kernel-stream-ended", exit=stream.returncode)
                stream_ended = True
            time.sleep(2)
        else:
            report["state"] = "capture-timeout"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        if stream is not None and stream.poll() is None:
            stream.terminate()
            try:
                stream.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stream.kill()
                stream.wait(timeout=3)
        for handle in (stdout, stderr):
            if handle:
                handle.close()
        if listener is not None:
            listener.close()
        report["token_matched_wifi_beacon_seen"] = beacon_seen
        report["kernel_bytes"] = ((out / "kmsg-live.raw").stat().st_size
                                  if (out / "kmsg-live.raw").exists() else 0)
        save()
        print(json.dumps({"state": report["state"],
                          "receipt": str(out / "result.json"),
                          "kernel_bytes": report["kernel_bytes"]}))


if __name__ == "__main__":
    main()
