#!/usr/bin/env python3
"""Bounded, read-only status for Lynx hardware not covered by sensor tools.

An observed node is not proof of a working peripheral. USB, modem, and SIM
remain unvalidated even when their kernel interfaces are visible.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess


COMPONENTS = ("battery", "thermal", "storage", "wifi", "display", "touch",
              "audio", "haptic", "sensorhub", "usb", "cellular", "sim")


def inventory(root=Path("/"), health=None):
    root = Path(root)

    def path(name):
        return root / name.lstrip("/")

    def exists(name):
        return path(name).exists()

    def names(name, pattern):
        return sorted(p.name for p in path(name).glob(pattern))

    def contains(name, needle):
        try:
            return needle in path(name).read_text()
        except OSError:
            return False

    def modem_state():
        try:
            with path("/sys/kernel/ccci/boot").open(encoding="ascii") as handle:
                raw = handle.read(256)
        except (OSError, UnicodeError):
            return None
        match = re.search(r"(?:^|\s)md1:(\d+)(?=\s|\||$)", raw)
        return int(match.group(1)) if match else None

    health = health or {}
    battery = health.get("battery") or {}
    thermal = health.get("thermal") or {}
    storage = health.get("root_filesystem") or {}
    wifi = health.get("wifi") or {}
    power_errors = battery.get("read_errors") or {}
    power_ok = (battery.get("capacity_percent") is not None and
                battery.get("gauge_type") == 42495 and
                all(value == 0 for value in power_errors.values()) and
                len(power_errors) >= 4)
    thermal_ok = isinstance(thermal.get("max_mC"), int)
    storage_ok = (storage.get("type") == "ext4" and
                  storage.get("source") == "/dev/sdc85" and
                  storage.get("ext4_errors_count") == 0)
    wifi_ok = wifi.get("carrier") is True and bool(wifi.get("ipv4"))
    display_ok = exists("/sys/module/mediatek_drm") and exists("/dev/dri/card0")
    touch_events = names("/dev/input", "event*")
    touch_ok = exists("/sys/module/synaptics_tcm2") and bool(touch_events)
    audio_ok = (contains("/proc/asound/cards", "mt6983mt6338") and
                exists("/dev/snd/pcmC0D11c"))
    haptic_ok = exists("/sys/module/haptic") and exists("/sys/class/leds/vibrator")
    sensorhub_ok = (exists("/dev/hf_manager") and
                    exists("/proc/hf_manager"))
    udcs = names("/sys/class/udc", "*")
    real_udcs = [name for name in udcs if not name.startswith("dummy_udc")]
    ccci_nodes = names("/dev", "ccci*")
    md1_state = modem_state()

    guard_disabled = path("/etc/lynx/power-thermal-guard.disable").exists()
    battery_next = ("power and thermal guards are disabled via administrative switch (/etc/lynx/power-thermal-guard.disable)"
                    if guard_disabled else "20% reserve policy may power off even while charging")
    thermal_next = ("power and thermal guards are disabled via administrative switch (/etc/lynx/power-thermal-guard.disable)"
                    if guard_disabled else "keep thermal guards active")

    result = {
        "battery": {"interface_ready": power_ok, "validated": power_ok,
                    "guard_disabled": guard_disabled,
                    "evidence": {"capacity_percent": battery.get("capacity_percent"),
                                 "current_mA_signed": battery.get("current_mA_signed"),
                                 "temperature_mC": battery.get("temperature_mC"),
                                 "voltage_mV": battery.get("voltage_mV"),
                                 "gauge_read_errors": power_errors},
                    "next": battery_next},
        "thermal": {"interface_ready": thermal_ok, "validated": thermal_ok,
                    "guard_disabled": guard_disabled,
                    "evidence": {"max_mC": thermal.get("max_mC"),
                                 "cooling_states": thermal.get("cooling_states", {})},
                    "next": thermal_next},
        "storage": {"interface_ready": storage_ok, "validated": storage_ok,
                    "evidence": {"root_type": storage.get("type"),
                                 "root_source": storage.get("source"),
                                 "ext4_errors_count": storage.get("ext4_errors_count"),
                                 "root_free_mib": health.get("root_free_mib")},
                    "next": "preserve boot and recovery images"},
        "wifi": {"interface_ready": wifi_ok, "validated": wifi_ok,
                 "evidence": {"carrier": wifi.get("carrier"),
                              "ipv4": wifi.get("ipv4")},
                 "next": "a dropped SSH link alone does not prove Lynx shut down"},
        "display": {"interface_ready": display_ok, "validated": display_ok,
                    "evidence": {"drm_card": exists("/dev/dri/card0"),
                                 "drm_module": exists("/sys/module/mediatek_drm")},
                    "next": "visual output was previously verified; inspect live selection separately"},
        "touch": {"interface_ready": touch_ok, "validated": False,
                  "evidence": {"synaptics_module": exists("/sys/module/synaptics_tcm2"),
                               "input_event_nodes": touch_events},
                  "next": "input nodes alone do not identify a live touch event"},
        "audio": {"interface_ready": audio_ok, "validated": False,
                  "evidence": {"alsa_card": contains("/proc/asound/cards", "mt6983mt6338"),
                               "capture_pcm": exists("/dev/snd/pcmC0D11c")},
                  "next": "use bounded media controls for playback"},
        "haptic": {"interface_ready": haptic_ok, "validated": False,
                   "evidence": {"driver_loaded": exists("/sys/module/haptic"),
                                "vibrator_led": exists("/sys/class/leds/vibrator")},
                   "next": "use bounded native HAPTIC_SET and HAPTIC_STOP for motion"},
        "sensorhub": {"interface_ready": sensorhub_ok, "validated": False,
                       "evidence": {"hf_manager": exists("/dev/hf_manager"),
                                    "registration": exists("/proc/hf_manager")},
                       "next": "use bounded raw motion and magnetometer readers"},
        "usb": {"interface_ready": bool(real_udcs), "validated": False,
                "evidence": {"udcs": udcs, "real_udcs": real_udcs,
                             "gadget_configured": False,
                             "host_enumeration_verified": False},
                "next": "native Alpine USB gadget and host enumeration remain unproven"},
        "cellular": {"interface_ready": bool(ccci_nodes), "validated": False,
                     "evidence": {"ccci_node_count": len(ccci_nodes),
                                  "md1_state_code": md1_state,
                                  "modem_runtime_verified": False},
                     "next": "modem startup and radio function remain unverified; do not start ccci_mdinit or write CCCI controls as a status probe"},
        "sim": {"interface_ready": False, "validated": False,
                "evidence": {"ccci_nodes_present": bool(ccci_nodes),
                             "card_presence_checked": False},
                "next": "Noob has not installed a SIM; wait for a scoped cellular trial"},
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=COMPONENTS + ("all",))
    args = parser.parse_args(argv)
    try:
        proc = subprocess.run(["/usr/local/bin/lynx-status"], capture_output=True,
                              text=True, timeout=5, check=True)
        health = json.loads(proc.stdout)
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"error": "lynx-status unavailable", "type": type(exc).__name__}))
        return 1
    states = inventory(health=health)
    print(json.dumps(states if args.component == "all" else states[args.component],
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
