#!/usr/bin/env python3
"""Lynx cellular/SIM *inventory* tool (read-only, on-device, offline-safe).

This tool produces a single concise JSON object describing which cellular- and
SIM-related kernel modules and device nodes are *present* on a running Lynx
boot. It is an inventory, not a functional test: it must never claim that the
modem firmware booted, that a SIM slot works, or that any radio is safe to use.

Hard safety constraints (enforced by design, asserted in the output):
  * read-only: it only reads /proc/modules and *inspects* filesystem metadata
    (name / type / driver symlink) of the three known SIM platform nodes and the
    existence / type of selected /dev CCCI status nodes;
  * it NEVER opens a CCCI character device for I/O (existence/type come from
    lstat, never open());
  * it NEVER reads SIM identifiers (ICCID/IMSI/IMSI), never activates RF, never
    loads modules, never runs subprocesses, and never changes services.

All source roots are injectable so offline tests can run against temp fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import stat as stat_mod
import sys
import time
from pathlib import Path

SCHEMA = 1
TOOL = "lynx_cellular_inventory"

# Default (on-device) roots. Every one is injectable for offline tests.
DEFAULT_PROC_MODULES = Path("/proc/modules")
DEFAULT_SYSFS_ROOT = Path("/sys")
DEFAULT_DEV_ROOT = Path("/dev")

# The three known Lynx SIM platform device nodes to inspect.
SIM_NODE_NAMES = (
    "MD1_SIM1_HOT_PLUG_EINT",
    "MD1_SIM2_HOT_PLUG_EINT",
    "odm:oplus_sim_detect",
)

# Bounded candidate parent directories (relative to the sysfs root) where the
# SIM platform nodes are expected. Constant number of stat calls -> prompt.
DEFAULT_SIM_NODE_DIRS = (
    "devices/platform",
    "bus/platform/devices",
)

# Selected /dev CCCI status/control nodes to check for existence and type only.
CCCI_NODE_NAMES = (
    "ccci_md1_sta",
    "ccci_ioctl0",
    "ccci_ioctl1",
    "ccci_ioctl2",
    "ccci_ioctl3",
    "ccci_ioctl4",
)

# Keyword set used to surface cellular-related module names from /proc/modules.
CELLULAR_MODULE_KEYWORDS = (
    "ccci", "eccc", "mddp", "mtk_md", "md1", "md2", "sim", "modem", "agps",
)

# Cap the /proc/modules read so the tool always exits promptly.
MAX_PROC_MODULES_BYTES = 1024 * 1024

VALID_TYPES = (
    "directory", "symlink", "file", "char_device", "block_device", "fifo", "other",
)


def classify_inode(mode: int) -> str:
    """Map an st_mode value to a human-readable filesystem entry type."""
    if stat_mod.S_ISDIR(mode):
        return "directory"
    if stat_mod.S_ISLNK(mode):
        return "symlink"
    if stat_mod.S_ISREG(mode):
        return "file"
    if stat_mod.S_ISCHR(mode):
        return "char_device"
    if stat_mod.S_ISBLK(mode):
        return "block_device"
    if stat_mod.S_ISFIFO(mode):
        return "fifo"
    return "other"


def _hostname():
    try:
        return os.uname().nodename
    except (AttributeError, OSError):
        return None


def _read_module_names(path):
    """Read loaded-module names from a /proc/modules-like file.

    Returns ``(names, None)`` on success or ``(None, error_string)`` on failure.
    Only this proc file is ever opened; CCCI device nodes are never opened.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            data = handle.read(MAX_PROC_MODULES_BYTES)
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc.strerror or exc}"
    names = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        head = line.split(None, 1)
        if not head:
            continue
        name = head[0]
        if name and name not in names:
            names.append(name)
    return names, None


def _resolve_sim_node(sysfs_root, name, sim_node_dirs):
    """Find the first existing SIM node under the candidate parent dirs."""
    for rel in sim_node_dirs:
        candidate = sysfs_root / rel / name
        try:
            os.lstat(candidate)
        except OSError:
            continue
        return candidate
    return None


def _inspect_sim_node(resolved, name):
    """Inspect one SIM platform node: found / type / driver symlink.

    Metadata only (lstat + readlink); the node is never opened or activated.
    """
    entry = {"name": name, "found": False, "type": None, "driver": None,
             "path": None, "error": None}
    if resolved is None:
        entry["error"] = "not_found"
        return entry
    entry["path"] = str(resolved)
    try:
        st = os.lstat(resolved)
    except OSError as exc:
        entry["error"] = f"lstat: {type(exc).__name__}: {exc.strerror or exc}"
        return entry
    entry["found"] = True
    entry["type"] = classify_inode(st.st_mode)
    driver = resolved / "driver"
    try:
        entry["driver"] = os.readlink(driver)
    except FileNotFoundError:
        entry["driver"] = None
    except OSError as exc:
        entry["driver"] = None
        entry["driver_error"] = f"{type(exc).__name__}: {exc.strerror or exc}"
    return entry


def _inspect_ccci_node(dev_root, name):
    """Check existence/type of one CCCI node by lstat only -- never open it."""
    path = dev_root / name
    entry = {"name": name, "exists": False, "type": None,
             "path": str(path), "error": None}
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        entry["error"] = "not_found"
        return entry
    except OSError as exc:
        entry["error"] = f"lstat: {type(exc).__name__}: {exc.strerror or exc}"
        return entry
    entry["exists"] = True
    entry["type"] = classify_inode(st.st_mode)
    return entry


def collect_inventory(proc_modules=DEFAULT_PROC_MODULES,
                      sysfs_root=DEFAULT_SYSFS_ROOT,
                      dev_root=DEFAULT_DEV_ROOT,
                      sim_node_names=SIM_NODE_NAMES,
                      ccci_node_names=CCCI_NODE_NAMES,
                      sim_node_dirs=DEFAULT_SIM_NODE_DIRS):
    """Build the read-only cellular/SIM inventory as a plain dict.

    Pure filesystem reads. Missing paths and read errors are reported
    explicitly in the returned structure; nothing is thrown for expected
    conditions.
    """
    module_names, module_error = _read_module_names(proc_modules)
    if module_names is None:
        proc_modules_info = {
            "readable": False,
            "module_count": 0,
            "cellular_modules": [],
            "error": module_error,
        }
    else:
        cellular = [
            name for name in module_names
            if any(k in name.lower() for k in CELLULAR_MODULE_KEYWORDS)
        ]
        proc_modules_info = {
            "readable": True,
            "module_count": len(module_names),
            "cellular_modules": cellular,
            "error": None,
        }

    sim_nodes = []
    for name in sim_node_names:
        resolved = _resolve_sim_node(sysfs_root, name, sim_node_dirs)
        sim_nodes.append(_inspect_sim_node(resolved, name))

    ccci_devices = [_inspect_ccci_node(dev_root, name) for name in ccci_node_names]

    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "label": "inventory-only",
        "hostname": _hostname(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Self-attested by design; the code structurally guarantees these.
        "constraints": {
            "read_only": True,
            "no_subprocess": True,
            "no_ccci_device_open": True,
            "no_rf_activation": True,
            "no_module_load": True,
            "no_service_change": True,
            "no_sim_identifier_read": True,
        },
        # Never claim a functional result.
        "cellular_function_validated": False,
        "modem_boot_status": "unknown",
        "sim_status": "unknown",
        "sim_present": None,
        "radio_activated": False,
        "ccci_device_opened": False,
        "proc_modules": proc_modules_info,
        "sim_nodes": sim_nodes,
        "ccci_devices": ccci_devices,
        "limits": [
            "presence only: does not prove modem firmware boot",
            "does not prove any SIM slot is usable or registered",
            "no radio activation and no SIM identifiers were read",
        ],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Read-only Lynx cellular/SIM node and module inventory "
                    "(never opens CCCI, never activates RF).",
    )
    parser.add_argument("--proc-modules", type=Path, default=DEFAULT_PROC_MODULES,
                        help="path to the /proc/modules-like file (default: /proc/modules)")
    parser.add_argument("--sysfs-root", type=Path, default=DEFAULT_SYSFS_ROOT,
                        help="sysfs root to search for SIM platform nodes (default: /sys)")
    parser.add_argument("--dev-root", type=Path, default=DEFAULT_DEV_ROOT,
                        help="dev root holding CCCI status nodes (default: /dev)")
    parser.add_argument("--compact", action="store_true",
                        help="print single-line JSON instead of indented")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = collect_inventory(
        proc_modules=args.proc_modules,
        sysfs_root=args.sysfs_root,
        dev_root=args.dev_root,
    )
    if args.compact:
        print(json.dumps(result, separators=(",", ":"), sort_keys=False))
    else:
        print(json.dumps(result, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
