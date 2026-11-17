#!/usr/bin/env python3
"""Run stock mnld briefly inside an empty RAM chroot and fresh namespaces.

This is a dependency audit, not a GNSS hardware trial. No device nodes,
factory storage, network interface, or persistent writable path is exposed.
"""

import json
import os
from pathlib import Path
import argparse
import stat
import shlex
import socket
import threading
import shutil
import signal
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--audit-hal", action="store_true")
    parser.add_argument("--gpsdl0", action="store_true",
                        help="expose only the already loaded GPS data-link node")
    parser.add_argument("--gps-power-nodes", action="store_true",
                        help="also expose the verified GPS EMI and power nodes")
    parser.add_argument("--gps-scp-node", action="store_true",
                        help="also expose the verified GPS to SCP node")
    parser.add_argument("--gps-port2", action="store_true",
                        help="also expose the second GPS data-link node")
    parser.add_argument("--factory-gps", action="store_true",
                        help="copy only the 54-byte factory GPS calibration into RAM")
    parser.add_argument("--strace", action="store_true",
                        help="capture bounded file, process, network, and ioctl calls")
    parser.add_argument("--capture-mnl", action="store_true",
                        help="listen for stock mnld messages without sending commands")
    parser.add_argument("--start-mnl", action="store_true",
                        help="issue exact stock start/stop packets during the short trial")
    parser.add_argument("--sky-trial", action="store_true",
                        help="60-second receiver trial after Lynx has clear sky view")
    parser.add_argument("--capture-logd", action="store_true",
                        help="capture stock Android log datagrams in RAM")
    args = parser.parse_args()
    if args.sky_trial and not (args.start_mnl and args.gps_port2 and args.capture_mnl):
        raise RuntimeError("sky trial requires active receiver and both GPS links")
    source = args.source.resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="lynx-gnss-sandbox-", dir="/run"))
    for name in ("bin", "lib64", "etc"):
        shutil.copytree(source / name, root / name)
    for name in ("system/bin", "vendor/bin", "vendor/etc", "data/vendor/gps", "run", "dev", "proc"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "system/bin/linker64").symlink_to("/bin/linker64")
    (root / "vendor/bin/mnld").symlink_to("/bin/mnld")
    (root / "vendor/etc/MNL_Config.xml").symlink_to("/etc/MNL_Config.xml")
    log_socket = None
    log_stop = threading.Event()
    android_log = []
    if args.capture_logd:
        (root / "dev/socket").mkdir()
        log_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        log_socket.bind(str(root / "dev/socket/logdw"))
        log_socket.settimeout(0.2)

        def receive_log():
            while not log_stop.is_set() and len(android_log) < 1000:
                try:
                    packet = log_socket.recv(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break
                android_log.append({"hex_prefix": packet[:32].hex(),
                                    "text": "".join(chr(c) if 32 <= c < 127 else " "
                                                    for c in packet[12:])[:500],
                                    "bytes": len(packet)})

        log_thread = threading.Thread(target=receive_log, daemon=True)
        log_thread.start()
    if args.gpsdl0:
        node = os.stat("/dev/gpsdl0")
        if not stat.S_ISCHR(node.st_mode) or os.major(node.st_rdev) != 497 or os.minor(node.st_rdev) != 0:
            raise RuntimeError("unexpected GPS data-link device")
        os.mknod(root / "dev/gpsdl0", stat.S_IFCHR | 0o600, node.st_rdev)
    if args.gps_power_nodes:
        if not args.gpsdl0:
            raise RuntimeError("GPS power nodes require the data-link node")
        for name, major in (("gps_emi", 496), ("gps_pwr", 495)):
            node = os.stat("/dev/" + name)
            if not stat.S_ISCHR(node.st_mode) or os.major(node.st_rdev) != major or os.minor(node.st_rdev) != 0:
                raise RuntimeError("unexpected " + name + " device")
            os.mknod(root / "dev" / name, stat.S_IFCHR | 0o600, node.st_rdev)
    if args.gps_scp_node:
        if not args.gps_power_nodes:
            raise RuntimeError("GPS SCP node requires power nodes")
        node = os.stat("/dev/gps2scp")
        if not stat.S_ISCHR(node.st_mode) or os.major(node.st_rdev) != 493 or os.minor(node.st_rdev) != 0:
            raise RuntimeError("unexpected GPS to SCP device")
        os.mknod(root / "dev/gps2scp", stat.S_IFCHR | 0o600, node.st_rdev)
    if args.gps_port2:
        if not args.gps_scp_node:
            raise RuntimeError("GPS port 2 requires the verified SCP node")
        node = os.stat("/dev/gpsdl1")
        if not stat.S_ISCHR(node.st_mode) or os.major(node.st_rdev) != 497 or os.minor(node.st_rdev) != 1:
            raise RuntimeError("unexpected GPS data-link port 2")
        os.mknod(root / "dev/gpsdl1", stat.S_IFCHR | 0o600, node.st_rdev)
    if args.factory_gps:
        uevent = Path("/sys/class/block/sdc10/uevent").read_text()
        if "PARTNAME=nvdata\n" not in uevent:
            raise RuntimeError("nvdata partition identity changed")
        with Path("/dev/sdc10").open("rb") as partition:
            partition.seek(1080)
            if partition.read(2) != b"\x53\xef":
                raise RuntimeError("nvdata ext4 signature changed")
        mountpoint = Path("/run/lynx-nvdata-gnss-readonly")
        mountpoint.mkdir(mode=0o700)
        mounted = False
        try:
            subprocess.run(["mount", "-t", "ext4", "-o", "ro,noload,nosuid,nodev,noexec",
                            "/dev/sdc10", str(mountpoint)], check=True, timeout=5)
            mounted = True
            calibration = (mountpoint / "APCFG/APRDEB/GPS").read_bytes()
        finally:
            if mounted:
                subprocess.run(["umount", str(mountpoint)], check=True, timeout=5)
            mountpoint.rmdir()
        if len(calibration) != 54:
            raise RuntimeError("factory GPS calibration size changed")
        factory = root / "mnt/vendor/nvdata/APCFG/APRDEB"
        factory.mkdir(parents=True)
        (factory / "GPS").write_bytes(calibration)
        (factory / "GPS").chmod(0o400)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/lib64"
    env["LD_PRELOAD"] = "/lib64/liblynx_props.so"
    if args.audit_hal:
        env["LD_PRELOAD"] += ":/lib64/liblynx_hal_audit.so"
    cmd = ["unshare", "-mn", "--", "chroot", str(root), "/system/bin/linker64", "/vendor/bin/mnld"]
    messages_file = root.parent / (root.name + "-mnl-messages.jsonl")
    if args.capture_mnl:
        if not args.gps_scp_node:
            raise RuntimeError("MNL capture requires the verified GPS SCP node")
        listener_options = (" --start-trial --seconds 64 --stop-after 52" if args.sky_trial else
                            " --start-trial --seconds 22 --stop-after 12" if args.start_mnl else "")
        shell = ("python3 /run/lynx_mnl_listener.py " +
                 shlex.quote(str(messages_file)) +
                 listener_options +
                 " & sleep 0.2; exec chroot " +
                 shlex.quote(str(root)) + " /system/bin/linker64 /vendor/bin/mnld")
        cmd = ["unshare", "-mn", "--", "sh", "-c", shell]
    elif args.start_mnl:
        raise RuntimeError("MNL start requires message capture")
    trace_file = root.parent / (root.name + "-strace.log")
    if args.strace:
        cmd = ["strace", "-f", "-qq", "-s", "120", "-e",
               "trace=file,process,network,ioctl", "-o", str(trace_file)] + cmd
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=60 if args.sky_trial else 20 if args.start_mnl else 8)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate(timeout=3)
    if log_socket is not None:
        log_stop.set()
        log_thread.join(timeout=1)
        log_socket.close()
    prop_log = root / "run/lynx-gnss-properties.log"
    hal_log = root / "run/lynx-gnss-hal-audit.log"
    result = {"exit": proc.returncode, "timed_out": timed_out,
              "stdout": stdout.decode(errors="replace")[-12000:],
              "stderr": stderr.decode(errors="replace")[-12000:],
              "property_log": prop_log.read_text(errors="replace")[-12000:] if prop_log.exists() else "",
              "hal_audit_log": hal_log.read_text(errors="replace")[-12000:] if hal_log.exists() else "",
              "sandbox": str(root), "hardware_nodes_exposed":
                  (["gpsdl0", "gpsdl1", "gps_emi", "gps_pwr", "gps2scp"] if args.gps_port2 else
                   ["gpsdl0", "gps_emi", "gps_pwr", "gps2scp"] if args.gps_scp_node else
                   ["gpsdl0", "gps_emi", "gps_pwr"] if args.gps_power_nodes else
                   ["gpsdl0"] if args.gpsdl0 else []),
              "ram_data_files": [{"path": str(path.relative_to(root)), "bytes": path.stat().st_size}
                                 for path in (root / "data/vendor/gps").rglob("*") if path.is_file()],
              "strace_tail": trace_file.read_text(errors="replace")[-30000:] if trace_file.exists() else ""}
    if args.capture_logd:
        result["android_log"] = android_log
    if args.capture_mnl:
        result["mnl_messages"] = [json.loads(line) for line in messages_file.read_text().splitlines()] if messages_file.exists() else []
    print(json.dumps(result))
    shutil.rmtree(root)
    trace_file.unlink(missing_ok=True)
    messages_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
