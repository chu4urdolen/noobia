# Lynx tool index — 2026-11-21 (Solo Dushich, D14, refreshed D20)

One page, today's state. "Installed" = present on the Lynx phone rootfs;
most Lynx tools are **Nexus-side** (they talk to the phone over the pinned
SSH route `192.168.100.107:2222`, key-only, bounded timeouts). Test command
pattern: `python3 -m unittest discover -s lynx/tools/<dir> -p 'test_*.py'`
(verified green today where a count is given).

## Tool directories

| Dir | Owner | Purpose | Live/offline | Installed? | Tests (2026-11-21) |
| --- | --- | --- | --- | --- | --- |
| `agent/` | Lynx | On-phone agent: lynx-codex-tool, supervised NRP queue, agent-health; `deploy_native_mcp_catalog.py` (known v19 landmine, Aria lane) | on-phone + Nexus side | **yes** (phone runtime) | 30 OK (incl. cancel suite) |
| `audio_afe/` | Dushich | **D23**: audio AFE preflight gate (`mt6983-afe-pcm@1e100000` mediatek,mt6983-sound, IRQ 448, MT6983_POWER_DOMAIN_AUDIO, topckgen/apmixedsys/infracfg_ao clocks; `snd_scp_ultra` memif 0x7/0xf; sound machine mediatek,mt6983-mt6338-sound platform &afe); STREAM_ACTIVE safety status; double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | **35 OK** |
| `watchdog_daemon/` | Dushich | **D25**: MT6983 TOPRGU watchdog petting/supervision daemon (`watchdog@1c007000` mediatek,mt6983-wdt, MMIO 0x1c007000, HW 1-32 s, reboot-mode syscon 0x24); pre-pet health gate (RAM>50MB, rootfs writable, loadavg<16.0), magic-'V' SIGTERM/SIGINT stop, abort-without-'V' on gate failure; staged `lynx-watchdogd.initd` (not installed) | offline sim default; live double-gated (`--live --allow-live`) | **no** (staged initd) | **45 OK** |
| `survival_daemon/` | Dushich | **D26**: autonomous survival & power daemon executing the B28 4-state engine (BQ28Z610 gauge i2c7@0x55, MT6375 charger i2c5@0x34, LVTS/NTC); broker /tmp/lynx_survival_state.json; SIMULATED actions only (schedutil/powersave, <=500mA, SCP/LPM C_SLEEP, graceful shutdown); no os import at all; staged `lynx-survivald.initd` (not installed, after lynx-watchdogd) | offline sim default; live double-gated, read-only telemetry | **no** (staged initd) | **39 OK** |
| `cgroups/` | Dushich | **D27**: cgroups v2 agent sandbox — spec validator + SIMULATED mutation plan for `/sys/fs/cgroup/lynx-agent/` (memory.max 512 MiB, memory.high 400 MiB, cpu.max 150000/100000 = 1.5 cores, oom.group=1, mirrored from B32 arch doc with drift test), PID migration, PSI thrash monitor; read-only live inspect; no os import; **no initd** (D27 scope) | offline sim default; live double-gated, read-only | **no** | **57 OK** |
| `openrc_validator/` | Dushich | **D28**: OpenRC service-tree dependency & startup-order validator for the untethered boot chain (bootmisc→sysfs→networking→lynx-watchdogd→lynx-survivald→lynx-cgroups→lynx-agent→lynx-presence); need=HARD (cycle=DEADLOCK), use=SOFT, before/after=WEAK (contradiction=ORDER_CONFLICT), provide-resolution, deterministic startup + reverse shutdown order, missing-prereq flags; read-only live parse of the staged D25/D26 initds; no os import | offline sim default; live double-gated, read-only | **no** | **38 OK** |
| `bluetooth/` | Banshee | BT link-state offline evaluator + acceptance gate; `catalog_proposal/` (schema, wrapper, manifest) | offline; live query gated | **no** (proposal) | 23 OK |
| `camera_deps/` | Banshee / Dushich | Camera dependency map + IMX890 (B10) / S5K3P9SP (B11) preflights + **D19 aux-cameras preflight** (IMX355 wide `sensor2@1a` + GC02M1 macro `sensor4@3d`); double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | **50 OK** |
| `display/` | Dushich | **D17 landed** (`df47f0b`): AMOLED display & panel preflight gate (Tianma NT37705 primary + BOE NT37701A second-source, `&dsi0`); double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | **29 OK** |
| `fingerprint/` | Banshee | Under-display fingerprint read-only identity/secure-boundary inventory | offline | **no** | 7 OK |
| `flashlight/` | Banshee | Second-light gate + running-DT collector (one lm3642 channel) | offline; live collector read-only | **no** | 9 OK |
| `flashlight_gate/` | Dushich | **D22**: flashlight core gate (`flashlight_core`, `mediatek,flashlight_core`, top-level in mt6983.dts; LM3642 `lm3642@63` on `&i2c6`, single `flash@0` channel, `fl_core_0`<->`flashlight_0`; `cam_temp` NTC on mt6373_adc AUXADC_VIN3); TORCH_ACTIVE safety status; double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | **35 OK** |
| `gnss/` | Banshee | **B12 landed** (`080594b`): GNSS fix-trial readiness checklist, gates, gated read-only live collector | offline; live gated (`--live --allow-live`) | **no** | 8 OK |
| `haptics/` | Dushich | **D21**: haptics LRA preflight gate (`&odm` `vibrator@0`, `mediatek,vibrator`, vib_timer 25 / limit 9 / vol 9); ACTIVE_PULSE safety status; double-flag gated read-only live inspector | offline; live gated (`--live --allow-live`) | **no** | **31 OK** |
| `headset/` | Banshee | Headset insertion evidence collector + **B13 landed** (`2185a79`): Type-C analog accessory detection trace + accessory classifier (11 tests) | offline; live read-only | **no** | 11 OK |
| `health/` | Dushich | portable-health/1 board: evaluator + Lynx collector (SSH) + **Nexus local collector** (D11) + report diff (D10) | offline; both collectors read-only | **no** | **139 OK** |
| `local_calls/` | Lynx | JSON-stdin wrappers for phone hardware (sensor, light, flashlight, motion) — the phone's own agent-call surface | on-phone | **yes** (phone rootfs) | via Gwyn ui manifest checks (113 OK) |
| `nfc/` | Banshee | SN110T NCI validator + **B14 landed** (`2adb7aa`): offline NCI frame parser + trial receipt decoder | offline (zero RF actuation) | **no** | 18 OK |
| `ram-log-reader/` | Lynx | ARM-emulated RAM log reader (build + emulation) | offline | **no** | (build/emulate scripts) |
| `touch/` | Dushich | **D18 landed** (`7143e3e`): touchscreen preflight gate (Synaptics S3908, `&i2c0` @ `0x4B`, IRQ GPIO8 / reset GPIO3); driver-link + input-class binding evidence, no unverified module asserts | offline; live gated (`--live --allow-live`) | **no** | **29 OK** |
| `tri_state_key/` | Banshee | **B25 landed**: OnePlus Alert Slider dual-hall preflight gate (MagnaChip MXM1120 / Isentek IST8801 on `&i2c0` @ `0x0C`/`0x0D` or `0x18`/`0x19`, GPIO4/5, Silent/Vibrate/Ring state machine); double-gated read-only live collector | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `ufs/` | Banshee | **B26 landed**: UFS 3.1 host controller & JEDEC health telemetry preflight gate (`ufshci@112b0000`, 5 clocks, 3 resets, VUFS18/12, Gear 4 M-PHY @ `0x11fa0000`, Pre-EOL / Lifetime Est A & B); double-gated read-only live collector | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `watchdog/` | Banshee | **B27 landed**: MTK-WDT hardware watchdog & recovery policy preflight (`watchdog@1c007000`, 1..32s timeout, reboot-mode offset 0x24); sysfs-only read-only inspection, zero open on `/dev/watchdog` | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `survival/` | Banshee | **B28 landed**: Autonomous thermal & battery survival decision engine (evaluates fuel gauge, SuperVOOC charger, LVTS/NTC thermals into 4 policy states: nominal, thermal throttle, low-power suspend, emergency shutdown) | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `heartbeat/` | Banshee | **B30/B33**: Autonomous health heartbeat payload generator and validator (aggregates battery, thermal, survival policy, watchdog, and cgroups into structured JSON payloads; payload-only, zero network broadcast) | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `autonomy_check/` | Banshee | **B31 landed**: Untethered autonomy readiness preflight checklist (evaluates all 6 critical autonomy gates: battery >=50%, cell delta <=50mV, thermals, UFS health, watchdog, survival engine) | offline; live gated (`--live --allow-live`) | **no** | **10 OK** |
| `ui/` | Gwyn | Presentation: validation-aware tool manifest, board refresh, a11y checks, state broker (`ui/state/latest.json`) | offline (board refresh reads pinned SSH) | **no** | 113 OK |
| `usb/` | Banshee | USB ACM NRP transport, boot-persistence initd (B9v2), collector, preflight + **B15 landed** (`49cd03e`): serial status proposal staged in `catalog_proposal/` | offline; collector read-only | **no** (initd + proposal NOT installed) | 39 OK |

## Standalone tools (`lynx/tools/*.py`)

| Tool | Owner | Purpose | Notes |
| --- | --- | --- | --- |
| `lynx_remote.py` (also `aria/tools/lynx-remote`) | Lynx | Bounded Alpine SSH `run` + `result` digest — the shared remote route | 20 s default cap; offline tests |
| `run_all_lynx_tests.py` | Dushich | **D20**: consolidated offline test-suite runner + `git diff --check`-equivalent whitespace gate across all tool dirs | offline; `--strict` counts env-blocked (missing deps) as failure | 30 self-tests OK |
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
  owns live deployment; Round 6 (2026-11-21): Banshee coordinates and peer-reviews, Dushich second-reviews).
- All live paths are read-only, bounded, and key-only; RF/capture/writes
  remain HARD_REFUSE until an attended, authorized trial.
- Build-cache dirs under `lynx/tools/` (alpine-*, aarch64-*, build-deps,
  mtk-*, qemu, zig, …) are ignored artifacts, not tools — excluded here.
