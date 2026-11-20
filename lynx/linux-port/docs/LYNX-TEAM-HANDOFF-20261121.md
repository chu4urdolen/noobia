# Lynx team handoff — 2026-11-21

This is the shared work queue for Aria, Banshee, Gwyn App Nub, and Solo
Dushich. Read [CURRENT-HANDOFF.md](CURRENT-HANDOFF.md) for the device evidence
and recovery boundary before working. Its last battery and boot observations
are historical, not a live health check. Noob authorized the four agents to
work on Lynx in parallel and will ask the other three to read `forge-db`.

## Coordination

- Before starting, run `forge-db project get lynx`, then
  `forge-db project touch lynx --for <your-name> --by <your-name> --together`.
  The `--together` flag records Noob's explicit parallel-work authorization.
  Write dated outcome, blocker, and handoff notes to `lynx` with your own
  `--by` name and cite the changed path. Do not write a note as another agent.
- Work on `/noobia` `main`, stage only your files, and check status before
  committing. The file areas below are ownership boundaries; discuss a
  cross-area edit in forge notes first. A verified source commit does not
  deploy anything to the phone.
- **Each owner tests their own work** and records the command, result, and
  remaining limits in their forge note or handoff. Aria reviews that evidence
  at integration and runs tests for her own live hardware and code changes;
  teammates do not hand routine test execution to Aria. This is Noob's
  2026-11-21 team instruction.
- Aria integrates and reviews phone-facing work. Other lanes are offline or
  read-only until an explicit reviewed live trial. No one should independently
  load kernel modules, activate the modem, alter boot storage, install phone
  services, or change live root sockets. Keep exact V53/V50 rollback paths.
- GNSS position fix is deferred until the other hardware work is finished, as
  Noob requested. The SIM stays out until Aria has an attended modem/SIM test
  ready and asks Noob to insert it.

## Lanes and first deliverables

| Owner | Work and owned source | First reviewable result | Completion gate |
| --- | --- | --- | --- |
| Aria | Live hardware trials, integration, recovery and acceptance; `lynx/tools/trial_*`, device deployment, hardware handoff docs | Review the no-SIM modem plan when ready and prepare the guarded live trial; continue remaining NFC, camera, radio and power work | Bounded receipts, health and recovery evidence, agent tool for each newly proven path |
| Banshee | USB controller and gadget work, offline fingerprint analysis, then offline cellular startup design; `lynx/tools/usb_*`, fingerprint and modem plan docs, later shared MCP work | Produce and test the no-SIM modem startup and stop plan from the current cellular record | Own tests and forge receipts; Aria reviews before modem activation or any persistent phone change |
| Gwyn App Nub | Lynx interface and tool presentation; `lynx/tools/ui/` and UI docs | Generate a read-only, validated-status-aware manifest for the 38 current local agent tools, with an offline test against source manifests | UI can display actual health and tool availability through a bounded broker; no direct unprivileged root-socket access, phone writes, or service install before Aria review |
| Solo Dushich | Portable passive diagnostics inspired by Aigel; `lynx/tools/health/` | Offline read-only `portable_health.py` plus independent tests using fixture input for battery, thermal, storage, network, and service state | Lynx health summary is bounded and accurate; common checks can later be reused on Nexus while GPU/SMART and other machine-specific checks remain separate; Aria reviews before install |

Dushich's Helper thread reviewed this split on 2026-11-21. He identified the
unfinished USB handoff `20261120T182715Z-7349486a`; it has one script in his
workspace, no test, and was not adopted. Banshee should review it first, not
assume it passed. Helper discussion does not change files or create a Solo
task. Solo Dushich can pick up his lane through his own CLI after reading the
forge notes.

**Additional Banshee task, requested by Noob on 2026-11-21:** After the USB
preflight, write `LYNX-FINGERPRINT-PREFLIGHT-20261121.md` here. Trace the
enabled `spi7.0` `oplus,fp_spi` device through exact stock driver candidates,
device tree, expected node, and secure userspace or TEE requirements. Mark
uncertainties and propose a bounded first trial. This is offline analysis; no
module load or biometric access. Forge note #39 is the pickup pointer.

**Next Banshee task, requested by Noob after the cellular read-only check:**
Prepare `LYNX-MODEM-START-PLAN-20261121.md` here and, if useful, a no-write
preflight tool under `lynx/tools/`. Use the current
[cellular record](LYNX-CELLULAR-INVENTORY-20261118.md) and the matching
OnePlus CCCI sources to map Android `ccci_mdinit` dependencies, the first
startup action, observable MD1 state transitions, a bounded stop/rollback,
and failure recovery. A successful write to `/sys/kernel/ccci/boot` is not
proof of startup; the source callback returns `-EACCES` while its wrapper
returns the write count. Keep the SIM out, do not open CCCI character devices,
start the modem, enable RF, or install a service during this offline task.
Banshee runs and records her own tests. Aria owns the later live trial. Forge
note #60 is the pickup pointer.

## Remaining hardware and acceptance ownership

| Area | Lead | Outstanding evidence |
| --- | --- | --- |
| NFC; fingerprint | Aria live; Banshee fingerprint preflight | Guarded NFC RAM probe on 2026-11-21 bound the driver and got a chip GET_VERSION response, but no tag exchange; fingerprint `spi7.0` has no bound driver or verified identity, secure userspace or function |
| USB data | Banshee | Banshee and Noob verified physical high-speed enumeration and bidirectional ACM serial on 2026-11-21 (forge note #58); assess persistence, safe disconnect, and agent-facing use before calling USB finished |
| Cellular and SIM | Banshee startup plan, Aria live trial | CCCI nodes exist but `md1:0`; no modem start, network registration, or SIM path verified; no SIM installed |
| Cameras and lights | Aria | Macro GC02M1 and wide IMX355 have optical frames via RAM patched ISP; main IMX890, front S5K3P9SP, second rear LED, safe persistent startup and agent capture/action interfaces remain |
| Bluetooth | Aria | Manual link and 15-minute hold passed; autostart and long-uptime reboot behavior remain |
| Audio, haptic, headset | Aria with Noob for perception | Noob confirmed speaker audibility and an isolated 80 ms Lynx haptic pulse; physical headset insertion/removal remains |
| Power and diagnostics | Solo Dushich prototypes, Aria deploys | Portable passive health, battery reserve policy and charge behavior need validated Lynx-specific gates; no unattended service changes from the prototype |
| Agent UI and tools | Gwyn prepares, Aria integrates | Catalog has 38 installed tools; preserve the distinction between interface inventory and functionally proven hardware |
| GNSS | Aria, last | 108 checksum-valid NMEA sentences without fix; clear-sky position trial later |

Each proposed new hardware action should first have an offline collector/test,
a fresh identity and health gate, timed receipt, stop-only watchdog where
relevant, and a recovery route. Ask Noob for physical attendance only when
that specific trial is ready. The detailed hazards and known-good paths are in
[the current handoff](CURRENT-HANDOFF.md) and
[hardware trials](LYNX-REMAINING-HARDWARE-TRIALS.md).
