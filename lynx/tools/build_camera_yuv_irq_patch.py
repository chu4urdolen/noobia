#!/usr/bin/env python3
"""Rebuild the experimental Nord 3 ISP IRQ patch without contacting Lynx."""

import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
COMMIT = "81ec42ad5e803be0cba619f9f7bb298db7d33d7b"
SPARSE = ROOT / "tools/gauge-build-inputs-1792103708378707350/kbuild-selective"
BASE = PORT / "artifacts/gauge-module-basis-1792107325426159905/basis"
COMPILER = ROOT / "tools/gauge-build-inputs-1792103708378707350/clang/bin"
SOURCE = SPARSE / "drivers/media/platform/mtk-isp/camsys/isp7_1/cam"
PATCH = PORT / "patches/camera-yuv-irq/0001-gate-yuv-irq-on-runtime-power.patch"
STOCK_ROOT = PORT / "artifacts/stock-cph2493-August-eu-ota"
STOCK = STOCK_ROOT / "wifi-reference/vendor-dlkm-unpacked/lib/modules/mtk-cam-isp.ko"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def versions(path, llvm_objcopy, output):
    run([str(llvm_objcopy), "--dump-section", f"__versions={output}", str(path)])
    data = output.read_bytes()
    if len(data) % 64:
        raise RuntimeError("unexpected module version record size")
    result = {}
    for offset in range(0, len(data), 64):
        row = data[offset:offset + 64]
        name = row[8:].split(b"\0", 1)[0].decode()
        crc = struct.unpack_from("<Q", row)[0]
        if name in result:
            raise RuntimeError("duplicate module import: " + name)
        result[name] = crc
    return result


def provider_map(imports):
    providers = {}
    depends = run(["modinfo", "-F", "depends", str(STOCK)], text=True).stdout.strip().split(",")
    for module in depends:
        matches = list(STOCK_ROOT.rglob(module + ".ko"))
        if len(matches) != 1:
            raise RuntimeError("stock provider not unique: " + module)
        symbols = run(["readelf", "-sW", str(matches[0])], text=True).stdout
        for name in re.findall(r"__ksymtab_([A-Za-z0-9_]+)", symbols):
            if name not in imports:
                continue
            if name in providers:
                raise RuntimeError("multiple providers for " + name)
            providers[name] = module
    if set(providers.values()) != set(depends):
        raise RuntimeError("incomplete stock provider map")
    return providers, depends


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra-patch", type=Path,
                        help="apply a second reviewed patch after the YUV IRQ gate")
    args = parser.parse_args()
    extra_patch = args.extra_patch.resolve() if args.extra_patch else None
    if run(["git", "-C", str(SPARSE), "rev-parse", "HEAD"], text=True).stdout.strip() != COMMIT:
        raise RuntimeError("unexpected kernel source commit")
    manifest = json.loads((ROOT / "sources/oneplus-nord3-mtkcam/SOURCE.json").read_text())
    if manifest["commit"] != COMMIT:
        raise RuntimeError("source manifest commit differs")
    for row in manifest["files"]:
        source = SOURCE / row["file"]
        if not source.is_file() or source.stat().st_size != row["bytes"] or digest(source) != row["sha256"]:
            raise RuntimeError("source integrity failed: " + row["file"])
    if not PATCH.is_file() or not BASE.is_dir() or not COMPILER.is_dir() or (extra_patch and not extra_patch.is_file()):
        raise RuntimeError("pinned build input absent")
    output = PORT / "artifacts" / f"camera-yuv-irq-rebuild-{time.time_ns()}"
    output.mkdir(mode=0o700)
    report = {"schema": 1, "state": "building", "phone_contacted": False,
              "kernel_source_commit": COMMIT, "patch_sha256": digest(PATCH),
              "stock_module_sha256": digest(STOCK)}
    if extra_patch:
        report["extra_patch_sha256"] = digest(extra_patch)
        report["extra_patch_path"] = str(extra_patch)

    def save():
        (output / "build-result.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    try:
        source_copy = output / "cam"
        basis_copy = output / "basis"
        shutil.copytree(SOURCE, source_copy)
        shutil.copytree(BASE, basis_copy, symlinks=True)
        (basis_copy / "drivers").symlink_to(SPARSE / "drivers", target_is_directory=True)
        patched = run(["patch", "--batch", "--forward", "-p1", "-d", str(source_copy)],
                      input=PATCH.read_bytes())
        (output / "patch.stdout").write_bytes(patched.stdout)
        if extra_patch:
            patched_extra = run(["patch", "--batch", "--forward", "-p1", "-d", str(source_copy)],
                                input=extra_patch.read_bytes())
            (output / "extra-patch.stdout").write_bytes(patched_extra.stdout)
        kbuild = source_copy / "Kbuild"
        data = kbuild.read_text().replace(
            "obj-$(CONFIG_VIDEO_MTK_ISP_CAMSYS) += mtk-cam-isp.o", "obj-m += mtk-cam-isp.o")
        data = "\n".join(line for line in data.splitlines()
                         if not line.startswith("obj-$(CONFIG_VIDEO_MTK_ISP_CAMSYS) +=")) + "\n"
        kbuild.write_text(data)
        llvm_objcopy = COMPILER / "llvm-objcopy"
        stock_imports = versions(STOCK, llvm_objcopy, output / "stock-versions.bin")
        providers, stock_depends = provider_map(stock_imports)
        (output / "provider-map.json").write_text(json.dumps(providers, indent=2, sort_keys=True) + "\n")
        symvers = basis_copy / "Module.symvers"
        lines = []
        existing = {}
        for line in symvers.read_text().splitlines():
            fields = line.split()
            name, crc = fields[1], int(fields[0], 16)
            existing[name] = crc
            if name in providers:
                fields[2] = providers[name]
                line = "\t".join(fields) + "\t"
            lines.append(line)
        for name, crc in sorted(stock_imports.items()):
            if name in existing:
                if existing[name] != crc:
                    raise RuntimeError("stock symbol CRC conflict: " + name)
                continue
            lines.append(f"0x{crc:08x}\t{name}\t{providers.get(name, 'vmlinux')}\tEXPORT_SYMBOL\t")
        symvers.write_text("\n".join(lines) + "\n")
        command = ["make", "-C", str(basis_copy), "-j8", "ARCH=arm64", "LLVM=1",
                   "LLVM_IAS=1", "CLANG_TRIPLE=aarch64-linux-gnu-",
                   "CROSS_COMPILE=" + str(ROOT / "tools/aarch64-gcc/root/usr/bin/aarch64-linux-gnu-"),
                   "M=" + str(source_copy), "modules"]
        env = os.environ.copy()
        env["PATH"] = str(COMPILER) + os.pathsep + env["PATH"]
        built = subprocess.run(command, capture_output=True, env=env, timeout=300)
        (output / "build.stdout").write_bytes(built.stdout)
        (output / "build.stderr").write_bytes(built.stderr)
        if built.returncode:
            raise RuntimeError("kernel module build failed")
        candidate = source_copy / "mtk-cam-isp.ko"
        candidate_imports = versions(candidate, llvm_objcopy, output / "candidate-versions.bin")
        candidate_depends = run(["modinfo", "-F", "depends", str(candidate)], text=True).stdout.strip().split(",")
        stock_vermagic = run(["modinfo", "-F", "vermagic", str(STOCK)], text=True).stdout.strip()
        candidate_vermagic = run(["modinfo", "-F", "vermagic", str(candidate)], text=True).stdout.strip()
        if (candidate_imports != stock_imports or candidate_depends != stock_depends or
                candidate_vermagic != stock_vermagic or not candidate_vermagic.startswith(KERNEL)):
            raise RuntimeError("candidate module ABI checks failed")
        stripped = source_copy / "mtk-cam-isp-stripped.ko"
        run([str(COMPILER / "llvm-strip"), "--strip-debug", "-o", str(stripped),
             str(candidate)])
        if (versions(stripped, llvm_objcopy, output / "stripped-versions.bin") != candidate_imports or
                run(["modinfo", "-F", "depends", str(stripped)], text=True).stdout.strip().split(",")
                != candidate_depends or
                run(["modinfo", "-F", "vermagic", str(stripped)], text=True).stdout.strip()
                != candidate_vermagic):
            raise RuntimeError("debug stripping changed module ABI")
        report.update(state="offline-module-built-not-tested-on-lynx",
                      candidate_module_sha256=digest(candidate),
                      candidate_module=str(candidate), module_bytes=candidate.stat().st_size,
                      stripped_trial_module_sha256=digest(stripped),
                      stripped_trial_module=str(stripped),
                      stripped_bytes=stripped.stat().st_size,
                      import_count=len(candidate_imports), provider_import_count=len(providers),
                      depends=candidate_depends, vermagic=candidate_vermagic)
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(output / "build-result.json"),
                      "error": report.get("error")}))
    if report["state"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
