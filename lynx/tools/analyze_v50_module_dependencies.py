#!/usr/bin/env python3
"""Inventory stock CPH2493 module dependencies without contacting Lynx."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota"
SEARCH = (
    BASE / "vendor-ramdisk-unpacked/lib/modules",
    BASE / "wifi-reference/vendor-dlkm-unpacked/lib/modules",
)
ROOTS = {
    # Root order reflects the reviewed stack order; dependency edges refine it.
    # This is an inventory, not authorization to load a whole stack at once.
    "gnss": ("connscp", "gps_scp", "gps_pwr", "gps_drv_dl_v050"),
    "bluetooth": ("btif_drv", "bt_drv_6983"),
    "flashlight": ("mtk_battery_oc_throttling", "flashlight", "lm3642_22823"),
    "camera": ("mtk_ccu", "v4l2-fwnode", "imgsensor"),
}
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def field(path, name):
    result = subprocess.run(["modinfo", "-F", name, str(path)], capture_output=True,
                            text=True, timeout=5, check=True)
    return result.stdout.strip()


def main():
    modules = {}
    duplicates = {}
    for directory in SEARCH:
        for path in directory.glob("*.ko"):
            if path.stem in modules:
                duplicates.setdefault(path.stem, []).append(str(path.relative_to(ROOT)))
            else:
                modules[path.stem] = path
    found = {}
    missing = set()

    def visit(name):
        if name in found or name in missing:
            return
        path = modules.get(name)
        if path is None:
            missing.add(name)
            return
        depends = [part for part in field(path, "depends").split(",") if part]
        vermagic = field(path, "vermagic")
        found[name] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "depends": depends,
            "vermagic": vermagic,
            "kernel_matches": vermagic.startswith(KERNEL + " "),
        }
        for dependency in depends:
            visit(dependency)

    for roots in ROOTS.values():
        for name in roots:
            visit(name)
    load_orders = {}
    for group, roots in ROOTS.items():
        order = []
        visiting = set()
        done = set()

        def add(name):
            if name in done:
                return
            if name in visiting:
                raise RuntimeError("module dependency cycle at " + name)
            visiting.add(name)
            for dependency in found[name]["depends"]:
                add(dependency)
            visiting.remove(name)
            done.add(name)
            order.append(name)

        for name in roots:
            add(name)
        load_orders[group] = order
    report = {"schema": 1, "source": str(BASE.relative_to(ROOT)),
              "kernel": KERNEL, "roots": ROOTS, "load_orders": load_orders,
              "modules": dict(sorted(found.items())),
              "missing_dependencies": sorted(missing), "duplicate_names": duplicates,
              "phone_contacted": False, "phone_partitions_written": False}
    out = ROOT / "logs" / f"hardware-dependencies-{time.time_ns()}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary = {name: len(order) for name, order in load_orders.items()}
    print(json.dumps({"receipt": str(out), "module_count": len(found),
                      "missing": sorted(missing), "closure_sizes": summary,
                      "all_kernel_matches": all(v["kernel_matches"] for v in found.values())},
                     sort_keys=True))


if __name__ == "__main__":
    main()
