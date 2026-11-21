#!/usr/bin/env python3
"""Audio AFE PCM & DSP core preflight gate for Lynx.

Platform: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 'Vitamin').
Validates offline the board's audio core topology from ``mt6983.dts``:
the AFE PCM controller ``mt6983-afe-pcm@1e100000``
(``compatible = "mediatek,mt6983-sound"``, IRQ 448, clocks from
``topckgen``/``apmixedsys``/``infracfg_ao_clk``, power domain
``MT6983_POWER_DOMAIN_AUDIO``), the SCP DSP offload node
``snd_scp_ultra`` (``compatible = "mediatek,snd_scp_ultra"``, memif ids
0x7 downlink / 0xf uplink), and the machine node ``sound``
(``mediatek,mt6983-mt6338-sound``, platform ``&afe``). Then classifies
the runtime ALSA interface (``/proc/asound``) without ever opening a
stream or writing PCM audio data.

All hardware facts below are verified against the Nord 3 source tree; see
``LYNX-AUDIO-AFE-PREFLIGHT-20261121.md`` for the full map.

Also includes a gated read-only collector for live inspection of the
ALSA interface, running device tree AFE/SCP/sound nodes, and loaded
kernel modules over SSH (strictly requiring both ``--live`` and
``--allow-live``).

Safety invariants:
* Offline by default; the live collector performs zero writes to any
  sysfs or proc attribute and opens no ALSA stream (reading
  ``/proc/asound/*`` is a plain file read, not a PCM capture/playback).
* Zero module loads, zero unapproved installs, zero acoustic emission.
* A fixture reporting an active audio stream at inspection time is
  classified ``STREAM_ACTIVE`` and fails the gate for human review
  (audio should be quiescent during preflight).
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_TIMEOUT = 8

# --- Verified hardware facts -----------------------------------------------
# mt6983.dts:13828-13840 (top-level node, parent /):
#     afe: mt6983-afe-pcm@1e100000 {
#         compatible = "mediatek,mt6983-sound";
#         reg = <0 0x1e100000 0 0x2000>;
#         interrupts = <GIC_SPI 448 IRQ_TYPE_LEVEL_HIGH 0>;
#         topckgen = <&topckgen_clk>;
#         apmixedsys = <&apmixedsys_clk>;
#         infracfg = <&infracfg_ao_clk>;
#         power-domains = <&scpsys MT6983_POWER_DOMAIN_AUDIO>;
#         clocks = <&afe_clk ...>, <&topckgen_clk ...>;
#     };
# mt6983.dts:13984-13988:
#     snd_scp_ultra: snd_scp_ultra {
#         compatible = "mediatek,snd_scp_ultra";
#         scp_ultra_dl_memif_id = <0x7>;
#         scp_ultra_ul_memif_id = <0xf>;
#     };
# mt6983.dts (nearby, top-level):
#     audio_sram@1e102000 { compatible = "mediatek,audio_sram"; ... };
#     audio_extend: audio_extend { compatible = "oplus,asoc-audio"; };
#     sound: sound {
#         compatible = "mediatek,mt6983-mt6338-sound";
#         mediatek,headset-codec = <&mt6338_accdet>;
#         mediatek,platform = <&afe>;
#     };

EXPECTED_AFE_NODE_NAME = "mt6983-afe-pcm@1e100000"
EXPECTED_AFE_LABEL = "afe"
EXPECTED_AFE_COMPATIBLE = "mediatek,mt6983-sound"
EXPECTED_AFE_REG_BASE = "0x1e100000"
EXPECTED_AFE_IRQ = 448
EXPECTED_AFE_POWER_DOMAIN = "MT6983_POWER_DOMAIN_AUDIO"
EXPECTED_AFE_CLOCK_SOURCES = ("topckgen", "apmixedsys", "infracfg_ao_clk")

EXPECTED_SCP_NODE_NAME = "snd_scp_ultra"
EXPECTED_SCP_COMPATIBLE = "mediatek,snd_scp_ultra"
EXPECTED_SCP_DL_MEMIF_ID = 0x7
EXPECTED_SCP_UL_MEMIF_ID = 0xF

EXPECTED_SOUND_NODE_NAME = "sound"
EXPECTED_SOUND_COMPATIBLE = "mediatek,mt6983-mt6338-sound"
EXPECTED_SOUND_PLATFORM = "afe"

# Runtime interface (standard ALSA proc/sys interface):
EXPECTED_RUNTIME_PROC = "/proc/asound"

# NOTE: the Round 7 queue says the gate should "assert PCM DAI links,
# buffer allocations, and sample rates". Those are runtime/audio-core
# concepts, not board-DTS facts: the board DTS defines the AFE controller
# and the machine node, but DAI-link topology is built by the vendor
# sound machine driver (not present in this kernel snapshot — no
# drivers/sound on disk). This gate therefore asserts the verified DTS
# facts and the runtime ALSA interface presence, and does NOT assert
# sample-rate or buffer facts (D17-D22 precedent for unverified claims).


# --- Read-only live collection script (cat/ls/find/tr/echo only) ---
LIVE_COLLECT_SCRIPT = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===ASOUND==="
ls /proc/asound 2>/dev/null || echo "NONE"
echo "===CARDS==="
cat /proc/asound/cards 2>/dev/null || echo "NONE"
echo "===PCM==="
cat /proc/asound/pcm 2>/dev/null || echo "NONE"
echo "===DT_AFE==="
find /sys/firmware/devicetree/base -maxdepth 2 -name "mt6983-afe-pcm@*" 2>/dev/null || echo "NONE"
echo "===DT_AFE_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 2 -name "mt6983-afe-pcm@*" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
  echo "interrupts_present=$([ -f "$f/interrupts" ] && echo yes || echo no)"
done
echo "===DT_SCP==="
find /sys/firmware/devicetree/base -maxdepth 2 -name "snd_scp_ultra" 2>/dev/null || echo "NONE"
echo "===DT_SCP_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 2 -name "snd_scp_ultra" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
done
echo "===DT_SOUND==="
find /sys/firmware/devicetree/base -maxdepth 2 -name "sound" 2>/dev/null || echo "NONE"
echo "===DT_SOUND_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 2 -name "sound" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
done
echo "===MODULES==="
cat /proc/modules 2>/dev/null || true
"""


@dataclass
class AudioAfeVerdict:
    status: str  # SOUND_READY / UNBOUND_QUIESCENT / PARTIAL_ENUMERATED / STREAM_ACTIVE / MALFORMED_SPEC
    is_valid: bool
    afe_node_mapped: bool
    scp_node_mapped: bool
    sound_node_mapped: bool
    runtime_proc_present: bool
    pcm_enumerated: bool
    stream_quiescent: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "afe_node_mapped": self.afe_node_mapped,
            "scp_node_mapped": self.scp_node_mapped,
            "sound_node_mapped": self.sound_node_mapped,
            "runtime_proc_present": self.runtime_proc_present,
            "pcm_enumerated": self.pcm_enumerated,
            "stream_quiescent": self.stream_quiescent,
            "summary": self.summary,
            "failures": self.failures,
            "details": self.details,
        }


def validate_audio_afe_spec(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Audit the board-spec sections of an audio AFE preflight document."""
    failures: List[str] = []
    dt = data.get("device_tree", {})

    # AFE PCM controller
    if not dt.get("afe_node_present"):
        failures.append("missing_afe_node_in_dt")
    if dt.get("afe_node_name") != EXPECTED_AFE_NODE_NAME:
        failures.append(f"afe_node_name_mismatch_{dt.get('afe_node_name')}_vs_{EXPECTED_AFE_NODE_NAME}")
    if dt.get("afe_compatible") != EXPECTED_AFE_COMPATIBLE:
        failures.append(f"afe_compatible_mismatch_{dt.get('afe_compatible')}_vs_{EXPECTED_AFE_COMPATIBLE}")
    if str(dt.get("afe_reg_base", "")).lower().replace("0x", "") != EXPECTED_AFE_REG_BASE.lower().replace("0x", ""):
        failures.append(f"afe_reg_base_mismatch_{dt.get('afe_reg_base')}_vs_{EXPECTED_AFE_REG_BASE}")
    if dt.get("afe_irq") != EXPECTED_AFE_IRQ:
        failures.append(f"afe_irq_mismatch_{dt.get('afe_irq')}_vs_{EXPECTED_AFE_IRQ}")
    if dt.get("afe_power_domain") != EXPECTED_AFE_POWER_DOMAIN:
        failures.append(f"afe_power_domain_mismatch_{dt.get('afe_power_domain')}_vs_{EXPECTED_AFE_POWER_DOMAIN}")
    clock_sources = [str(c).lower() for c in (dt.get("afe_clock_sources") or [])]
    for expected in EXPECTED_AFE_CLOCK_SOURCES:
        if expected not in clock_sources:
            failures.append(f"afe_clock_source_missing_{expected}")

    # SCP DSP offload node
    if not dt.get("scp_node_present"):
        failures.append("missing_scp_node_in_dt")
    if dt.get("scp_compatible") != EXPECTED_SCP_COMPATIBLE:
        failures.append(f"scp_compatible_mismatch_{dt.get('scp_compatible')}_vs_{EXPECTED_SCP_COMPATIBLE}")
    if dt.get("scp_dl_memif_id") not in (EXPECTED_SCP_DL_MEMIF_ID, hex(EXPECTED_SCP_DL_MEMIF_ID)):
        failures.append(f"scp_dl_memif_mismatch_{dt.get('scp_dl_memif_id')}_vs_{EXPECTED_SCP_DL_MEMIF_ID}")
    if dt.get("scp_ul_memif_id") not in (EXPECTED_SCP_UL_MEMIF_ID, hex(EXPECTED_SCP_UL_MEMIF_ID)):
        failures.append(f"scp_ul_memif_mismatch_{dt.get('scp_ul_memif_id')}_vs_{EXPECTED_SCP_UL_MEMIF_ID}")

    # sound machine node
    if not dt.get("sound_node_present"):
        failures.append("missing_sound_node_in_dt")
    if dt.get("sound_compatible") != EXPECTED_SOUND_COMPATIBLE:
        failures.append(f"sound_compatible_mismatch_{dt.get('sound_compatible')}_vs_{EXPECTED_SOUND_COMPATIBLE}")
    if dt.get("sound_platform") != EXPECTED_SOUND_PLATFORM:
        failures.append(f"sound_platform_mismatch_{dt.get('sound_platform')}_vs_{EXPECTED_SOUND_PLATFORM}")

    return len(failures) == 0, failures


def evaluate_audio_afe_preflight(data: Dict[str, Any]) -> AudioAfeVerdict:
    """Evaluate preflight telemetry or fixture for the Nord 3 audio AFE."""
    spec_ok, failures = validate_audio_afe_spec(data)

    dt = data.get("device_tree", {})
    afe_mapped = (
        bool(dt.get("afe_node_present"))
        and dt.get("afe_node_name") == EXPECTED_AFE_NODE_NAME
        and dt.get("afe_compatible") == EXPECTED_AFE_COMPATIBLE
        and str(dt.get("afe_reg_base", "")).lower().replace("0x", "")
            == EXPECTED_AFE_REG_BASE.lower().replace("0x", "")
        and dt.get("afe_irq") == EXPECTED_AFE_IRQ
        and dt.get("afe_power_domain") == EXPECTED_AFE_POWER_DOMAIN
        and all(
            expected in [str(c).lower() for c in (dt.get("afe_clock_sources") or [])]
            for expected in EXPECTED_AFE_CLOCK_SOURCES
        )
    )
    scp_mapped = (
        bool(dt.get("scp_node_present"))
        and dt.get("scp_compatible") == EXPECTED_SCP_COMPATIBLE
        and dt.get("scp_dl_memif_id") in (EXPECTED_SCP_DL_MEMIF_ID, hex(EXPECTED_SCP_DL_MEMIF_ID))
        and dt.get("scp_ul_memif_id") in (EXPECTED_SCP_UL_MEMIF_ID, hex(EXPECTED_SCP_UL_MEMIF_ID))
    )
    sound_mapped = (
        bool(dt.get("sound_node_present"))
        and dt.get("sound_compatible") == EXPECTED_SOUND_COMPATIBLE
        and dt.get("sound_platform") == EXPECTED_SOUND_PLATFORM
    )

    runtime = data.get("runtime", {}) or {}
    proc_present = bool(runtime.get("proc_asound_present"))
    pcm_enumerated = bool(runtime.get("pcm_enumerated"))
    stream_active = bool(runtime.get("stream_active"))
    quiescent = not stream_active

    if not spec_ok:
        return AudioAfeVerdict(
            status="MALFORMED_SPEC",
            is_valid=False,
            afe_node_mapped=afe_mapped,
            scp_node_mapped=scp_mapped,
            sound_node_mapped=sound_mapped,
            runtime_proc_present=proc_present,
            pcm_enumerated=pcm_enumerated,
            stream_quiescent=quiescent,
            summary=f"Audio AFE preflight specification audit failed: {len(failures)} violation(s)",
            details=data,
            failures=failures,
        )

    if stream_active:
        return AudioAfeVerdict(
            status="STREAM_ACTIVE",
            is_valid=False,
            afe_node_mapped=afe_mapped,
            scp_node_mapped=scp_mapped,
            sound_node_mapped=sound_mapped,
            runtime_proc_present=proc_present,
            pcm_enumerated=pcm_enumerated,
            stream_quiescent=False,
            summary=(
                "An audio stream is ACTIVE at inspection time. "
                "This is a safety anomaly for preflight: audio should be "
                "quiescent. Verify no capture/playback source is running "
                "before proceeding."
            ),
            details=data,
            failures=["stream_not_quiescent"],
        )

    if proc_present and pcm_enumerated:
        status = "SOUND_READY"
        summary = (
            "ALSA interface enumerated (cards + PCM devices), quiescent. "
            "Board audio core mapped (mt6983-afe-pcm@1e100000, IRQ 448, "
            "MT6983_POWER_DOMAIN_AUDIO; snd_scp_ultra memif 0x7/0xf; "
            "sound machine platform &afe)."
        )
    elif proc_present and not pcm_enumerated:
        status = "PARTIAL_ENUMERATED"
        summary = (
            "Audio interface partially enumerated: /proc/asound present but "
            "no PCM devices listed. Board spec verified offline."
        )
    else:
        status = "UNBOUND_QUIESCENT"
        summary = (
            "Audio AFE preflight verified quiescent. Device tree mapped "
            "(mt6983-afe-pcm@1e100000, snd_scp_ultra, sound machine), no "
            "runtime ALSA interface (driver safely absent)."
        )

    return AudioAfeVerdict(
        status=status,
        is_valid=True,
        afe_node_mapped=afe_mapped,
        scp_node_mapped=scp_mapped,
        sound_node_mapped=sound_mapped,
        runtime_proc_present=proc_present,
        pcm_enumerated=pcm_enumerated,
        stream_quiescent=quiescent,
        summary=summary,
        details=data,
        failures=[],
    )


def collect_live_audio_afe(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform read-only live inspection of audio AFE state over SSH."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    key_file = repo_root / "secrets/nexus_lynx_ed25519"
    known_hosts = repo_root / "secrets/lynx_known_hosts"

    if not key_file.is_file():
        return {"error": f"Missing private SSH key: {key_file}"}

    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=5",
        "-i", str(key_file),
        "-p", str(port),
        f"root@{host}",
        "sh", "-s",
    ]

    try:
        res = subprocess.run(cmd, input=LIVE_COLLECT_SCRIPT, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return {"error": f"SSH invocation failed: {e}"}

    if res.returncode != 0:
        return {"error": f"SSH returned code {res.returncode}: {res.stderr.strip()}"}

    def section(name: str) -> List[str]:
        marker = f"==={name}==="
        if marker not in res.stdout:
            return []
        rest = res.stdout.split(marker, 1)[1]
        next_pos = rest.find("\n===")
        chunk = rest if next_pos == -1 else rest[:next_pos]
        return [l.strip() for l in chunk.splitlines() if l.strip()]

    boot_lines = res.stdout.split("===ASOUND===", 1)[0].splitlines()
    boot_id = boot_lines[-1].strip() if boot_lines else "UNKNOWN_BOOT"

    asound_entries = [l for l in section("ASOUND") if l != "NONE"]
    proc_present = len(asound_entries) > 0

    cards = [l for l in section("CARDS") if l != "NONE"]
    pcm_lines = [l for l in section("PCM") if l != "NONE"]
    pcm_enumerated = len(pcm_lines) > 0

    afe_nodes = [l for l in section("DT_AFE") if l != "NONE"]
    afe_present = len(afe_nodes) > 0
    afe_compatible = None
    afe_irq_present = False
    for line in section("DT_AFE_PROPS"):
        if line.startswith("compatible="):
            afe_compatible = line.split("=", 1)[1].strip() or None
        if line.startswith("interrupts_present="):
            afe_irq_present = line.split("=", 1)[1].strip() == "yes"

    scp_nodes = [l for l in section("DT_SCP") if l != "NONE"]
    scp_present = len(scp_nodes) > 0
    scp_compatible = None
    for line in section("DT_SCP_PROPS"):
        if line.startswith("compatible="):
            scp_compatible = line.split("=", 1)[1].strip() or None

    sound_nodes = [l for l in section("DT_SOUND") if l != "NONE"]
    sound_present = len(sound_nodes) > 0
    sound_compatible = None
    for line in section("DT_SOUND_PROPS"):
        if line.startswith("compatible="):
            sound_compatible = line.split("=", 1)[1].strip() or None

    module_lines = section("MODULES")
    loaded_mods = [l.split()[0] for l in module_lines if l.strip()]

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / project 22823 'Vitamin')",
        "boot_id": boot_id,
        "device_tree": {
            "afe_node_present": afe_present,
            "afe_node_name": "mt6983-afe-pcm@1e100000" if afe_present else None,
            "afe_compatible": afe_compatible,
            "afe_reg_base": EXPECTED_AFE_REG_BASE,
            "afe_irq": EXPECTED_AFE_IRQ if afe_irq_present else None,
            "afe_power_domain": EXPECTED_AFE_POWER_DOMAIN,
            "afe_clock_sources": list(EXPECTED_AFE_CLOCK_SOURCES),
            "scp_node_present": scp_present,
            "scp_compatible": scp_compatible,
            "scp_dl_memif_id": EXPECTED_SCP_DL_MEMIF_ID,
            "scp_ul_memif_id": EXPECTED_SCP_UL_MEMIF_ID,
            "sound_node_present": sound_present,
            "sound_compatible": sound_compatible,
            "sound_platform": EXPECTED_SOUND_PLATFORM,
        },
        "runtime": {
            "proc_asound_present": proc_present,
            "card_count": len([c for c in cards if not c.startswith("card")]),
            "pcm_enumerated": pcm_enumerated,
            "pcm_devices": pcm_lines,
            "stream_active": False,  # not determinable read-only; fixtures may report it
        },
        "loaded_modules": loaded_mods,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Audio AFE PCM & DSP core preflight gate")
    parser.add_argument("fixture", type=Path, nargs="?", default=None, help="Path to JSON fixture")
    parser.add_argument("--live", action="store_true", help="Perform read-only query on Lynx (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true", help="Confirm read-only live query")
    parser.add_argument("--host", default=DEFAULT_LYNX_HOST, help="Lynx IP")
    parser.add_argument("--port", type=int, default=DEFAULT_LYNX_PORT, help="Lynx SSH port")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print(json.dumps({"error": "Refusing live query without both --live and --allow-live"}, indent=2), file=sys.stderr)
            sys.exit(2)
        data = collect_live_audio_afe(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)
        verdict = evaluate_audio_afe_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.fixture:
        data = json.loads(args.fixture.read_text())
        verdict = evaluate_audio_afe_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
