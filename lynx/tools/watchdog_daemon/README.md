# lynx-watchdogd — MT6983 TOPRGU watchdog petting daemon (D25)

Software supervisor + petting daemon for the OnePlus Nord 3 hardware watchdog
(`watchdog@1c007000`, `mediatek,mt6983-wdt`, MMIO `0x1c007000`, HW range 1–32 s,
reboot-mode syscon child at `0x24`). See `../../linux-port/docs/LYNX-WATCHDOG-DAEMON-20261121.md`.

Safety model:

- **Critical Kernel Behavior:** Opening `/dev/watchdog` arms the MediaTek
  TOPRGU hardware watchdog timer. Administrative exit requires writing the magic
  character `V` before closing. If the process is terminated via `SIGKILL` or an
  unhandled fatal signal, signal handlers are bypassed, leaving `/dev/watchdog`
  armed without petting. After ~30 seconds of starvation, the SoC hardware
  watchdog fires a cold hardware reset of Lynx. All live runs must be attended.
- **Offline by default:** `--validate FIXTURE` simulates the full pet loop,
  health gates, and SIGTERM/SIGINT magic-'V' handling in-process. No hardware
  is ever touched.
- **Platform Verification:** Refuses live execution unless `/proc/device-tree/compatible`
  names `mt6983` and the device tree model names the MT6983 / Nord 3 platform.
- **Bounded Manual Execution:** Manual live runs require `--cycles >= 1` (unbounded
  execution is strictly gated behind `--daemon` for supervised OpenRC service runs).
- **Live is double-gated:** `--live --allow-live` (refused otherwise), bounded
  by `--cycles` / `--interval` / `--wall-cap`.
- **Pre-pet health gate:** free RAM > 50 MB, rootfs writable, 1-min loadavg
  < 16.0. Gate failure → stop petting and close WITHOUT 'V' so the hardware
  watchdog performs recovery.
- **Magic 'V' handler:** SIGTERM/SIGINT → write `V` to `/dev/watchdog`, close,
  exit cleanly (administrative stop, no reset).
- All `/dev/watchdog` access lives in the whitelisted `_live_*` functions
  (enforced by `test_lynx_watchdogd.py` AST scans).

`lynx-watchdogd.initd` is STAGED for review — not installed into
`/etc/init.d/` until approved (runlevel `default`, `before net`,
`provide watchdog`).

```sh
python3 lynx_watchdogd.py --validate fixtures/watchdogd-nominal.json
python3 -m unittest test_lynx_watchdogd
```
