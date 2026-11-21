# Lynx tool index — 2026-11-21 (Solo Dushich, D14)

One page, today's state. "Installed" = present on the Lynx phone rootfs;
most Lynx tools are **Nexus-side** (they talk to the phone over the pinned
SSH route `192.168.100.107:2222`, key-only, bounded timeouts). Test command
pattern: `python3 -m unittest discover -s lynx/tools/<dir> -p 'test_*.py'`
(verified green today where a count is given).

## Tool directories

| Dir | Owner | Purpose | Live/offline | Installed? | Tests (2026-11-21) |
| --- | --- | --- | --- | --- | --- |
| `agent/` | Lynx | On-phone agent: lynx-codex-tool, supervised NRP queue, agent-health; `deploy_native_mcp_catalog.py` (known v19 landmine, Aria lane) | on-phone + Nexus side | **yes** (phone runtime) | cancel suite 9 OK (Gwyn #133) |
| `bluetooth/` | Banshee | BT link-state offline evaluator + acceptance gate; `catalog_proposal/` (schema, wrapper, manifest) | offline; live query gated | **no** (proposal) | 23 OK |
| `camera_deps/` | Banshee | Camera dependency map + IMX890 (B10) / S5K3P9SP (B11) preflights; double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | 20 OK |
| `fingerprint/` | Banshee | Under-display fingerprint read-only identity/secure-boundary inventory | offline | **no** | OK |
| `flashlight/` | Banshee | Second-light gate + running-DT collector (one lm3642 channel) | offline; live collector read-only | **no** | 9 OK |
| `gnss/` | Banshee | **B12 IN-FLIGHT** (working tree): GNSS fix-trial readiness checklist + gated read-only collector | offline | **no** | OK (in-flight) |
| `headset/` | Banshee | Headset insertion evidence collector (interface-state, read-only) | offline; live read-only | **no** | OK |
| `health/` | Dushich | portable-health/1 board: evaluator + Lynx collector (SSH) + **Nexus local collector** (D11) + report diff (D10) | offline; both collectors read-only | **no** | **139 OK** |
| `local_calls/` | Lynx | JSON-stdin wrappers for phone hardware (sensor, light, flashlight, motion) — the phone's own agent-call surface | on-phone | **yes** (phone rootfs) | via Gwyn ui manifest checks (113 OK) |
| `nfc/` | Banshee | SN110T NCI validator + fixtures for the attended tag trial (B14 target) | offline | **no** | 5 OK |
| `ram-log-reader/` | Lynx | ARM-emulated RAM log reader (build + emulation) | offline | **no** | (build/emulate scripts) |
| `ui/` | Gwyn | Presentation: validation-aware tool manifest, board refresh, a11y checks, state broker (`ui/state/latest.json`) | offline (board refresh reads pinned SSH) | **no** | 113 OK |
| `usb/` | Banshee | USB ACM NRP transport, boot-persistence initd (B9v2), collector, preflight | offline; collector read-only | **no** (initd NOT installed) | 34 OK |

## Standalone tools (`lynx/tools/*.py`)

| Tool | Owner | Purpose | Notes |
| --- | --- | --- | --- |
| `lynx_remote.py` (also `aria/tools/lynx-remote`) | Lynx | Bounded Alpine SSH `run` + `result` digest — the shared remote route | 20 s default cap; offline tests |
| `lynx_hardware.py` | Lynx | Shared hardware inventory backend behind local_calls (native IDs 390–395) | phone-side |
| `lynx_noobctl.py` / `lynx_noob_runtime.py` | Lynx | Nexus client / NRP-1 server (port 4243, Iris-compatible) | runtime |
| `lynx_presence.py` | Lynx | Low-duty SSH/presence probe | read-only |
| `lynx_modem_preflight.py` | Banshee | No-SIM modem preflight gate (CCCI trace, MD1 state) | read-only, no RF |
| `lynx_usb_mtu3_preflight.py` | Banshee | MTU3 USB driver trial gate (strict no-write default) | offline |
| `lynx_camera_gate.py` | Lynx | Camera route gate: validated GC02M1/IMX355 only; streaming/capture `HARD_REFUSE` | offline |
| `lynx_agent_haptic.py` / `lynx_agent_media.py` / `lynx_agent_remote.py` | Lynx | NRP haptic bridge / lynx-media wrapper / agent-queue client | power+thermal guards |
| `lynx_motion_read.py` | Lynx | One accel/gyro raw sample via lynx-hf-sample | no FUSION |
| `lynx_peripheral_status.py` | Lynx | NFC/fingerprint/headset interface status probe | read-only |

## Ground rules (unchanged this round)

- Nothing in this index is **deployed** except the phone runtime and
  local_calls surface; every "no" is deliberate and review-gated (Aria
  owns live deployment, Gwyn reviews, Dushich second-reviews).
- All live paths are read-only, bounded, and key-only; RF/capture/writes
  remain HARD_REFUSE until an attended, authorized trial.
- Build-cache dirs under `lynx/tools/` (alpine-*, aarch64-*, build-deps,
  mtk-*, qemu, zig, …) are ignored artifacts, not tools — excluded here.
