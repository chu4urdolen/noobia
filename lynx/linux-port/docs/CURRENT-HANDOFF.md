# Lynx handoff — 2026-11-18

Read this first in the next conversation. Confirm live state before any phone
command; this is a checkpoint, not a live guarantee.

## Current foothold

- Lynx is a OnePlus Nord 3 CPH2493 / MT6983 running native Alpine from the
  verified V53 `boot_a`. The exact V53 image, V50 BusyBox rescue image, and
  Fastboot rollback procedure remain available. No boot partition was changed
  in the work described below.
- Observed address: `192.168.100.107`. Alpine SSH uses port 2222 with the
  pinned Lynx host identity; NRP/1 listens on port 4243 and accepts Nexus.
  Use `python3 /noobia/lynx/tools/lynx_presence.py --once` for a low-duty
  contact check. Do not treat a black screen as proof she is off.
- Previous conversation's check: Alpine Wi-Fi SSH online on boot
  `d629cc73-aa6d-4aec-808b-8a374740e203`, 69% battery, −151 mA net current,
  24.8°C battery, no USB. She was discharging; check again before work.
- Follow-up on 2026-11-18: the previous boot shut down at 20% while
  discharging; the reserve marker is at 10:05 UTC (about 12:05 Sofia time).
  Lynx returned on boot `6613079f-ae1f-4e05-8123-0988b423d6da` and was
  charging. At 25% the sensor retry started audio and sensorhub automatically;
  health and a bounded accelerometer sample passed. See the sensor retry and
  poweroff audit records. Recheck live state before further commands.
- With 27% and positive charging current on the same boot, a bounded V53
  Bluetooth start/reconnect/stop trial passed using a stop-only watchdog;
  health, Wi-Fi, and radio power-off checks passed. See the Bluetooth NRP
  record. A later full 15-minute same-boot hold also passed all 30 health
  samples and clean radio shutdown. Autostart and long-uptime reboot still
  need separate trials. Nexus then lost the Noobia Wi-Fi SSID. Noob restarted
  the repeater; pinned SSH returned on the same Lynx boot, so the contact loss
  was not a Lynx shutdown. At 19:46 UTC she was at 98%, 27.5°C, with clear
  health and Wi-Fi carrier. Recheck live state before further commands.
- The previous conversation found `/noobia` clean on `main` at `f76b6b6` and
  confirmed `origin/main` there. Other resident agents share `main`, so
  recheck Git status, remote, and HEAD before any new commit or push.

## Working hardware and software

- Alpine self-boots with Wi-Fi, SSH, persistent expanded ext4 root, display,
  touchscreen, Console and Status pages, images/animations, sound, vibration,
  battery and thermal monitoring, and the Noobia NRP/1 runtime.
- Existing NRP/1 calls cover accelerometer, gyroscope, magnetometer,
  proximity, rear optical sensor, microphone level, flashlight, and status
  interfaces. Values from motion and optical sensors are driver raw values,
  not calibrated physical units.
- The on-device agent has a supervised job queue, local tool catalog,
  persistent Codex CLI, and a tested Responses connection to Nexus inference.
  The cloud fallback has no installed OpenAI key. Jobs still require explicit
  submission; there is no autonomous scheduler.
- Agent tool manifests and shell wrappers live under
  `/usr/local/share/lynx/agent-tools` on the phone and
  `/noobia/lynx/tools/local_calls/` in source. The agent reads the catalog
  dynamically. Existing motion NRP/1 calls already serve remote and VM use.

## Recent verified changes

- Installed a bounded local magnetometer reader. A live AKM09918 raw vector,
  existing authenticated `MAG_STATUS`/`MAG_VECTOR`, and same-boot health passed.
  Five offline tests passed. See [hardware status](LYNX-HARDWARE-STATUS.md).
- Installed `lynx_motion_read`, a local agent tool for one accelerometer or
  gyroscope vector. Dushich implemented and tested the isolated reader in his
  own workspace; Aria reviewed it, installed it, and verified both live
  samples plus an actual agent catalog invocation. Thirty-eight offline tests
  passed. Receipt:
  `lynx/logs/motion-local-tool-1794956244324033878/result.json`.
- Audio and sensorhub were stopped after a boot at about 22% battery. Both
  started normally after charge rose. Installed `lynx-sensor-retry`, a bounded
  OpenRC service that waits for the existing bootstrap charge/temperature
  gates, then starts audio before sensorhub. It is running and idle on the
  current healthy boot. Twenty-nine offline tests passed; the natural
  low-charge cold-boot retry has now passed. See [retry record](LYNX-SENSOR-RETRY-20261118.md).
- Investigated spontaneous-looking shutdowns. Most saved events are deliberate
  battery-reserve poweroffs at 20% while discharging; Nov 16 ended at 20% and
  −152 mA. One Nov 6 shutdown at 48% was `safety_guard_failed`, but its older
  log does not identify the failed check. There is no elapsed-uptime shutdown.
  The installed reserve guard is the older policy and can power off at 20%
  even while charging; the newer charging-aware source was intentionally
  rolled back after an inconclusive trial. Do not replace it casually. See
  [poweroff audit](LYNX-POWER-SHUTDOWNS-20261118.md).

## Hardware still to finish

1. GNSS emits NMEA but has not produced a position fix. Bluetooth has passed
   HCI and authenticated NRP/1 GATT trials, but its automatic and long-uptime
   behavior remains unverified. SIM/cellular needs modem readiness and SIM
   path validation before any radio activation. Noob confirmed no SIM is
   installed on 2026-11-18 and will add one when a specific trial is ready.
   A read-only [cellular inventory](LYNX-CELLULAR-INVENTORY-20261118.md)
   found CCCI nodes and SIM hot-plug platform names, but no working modem
   route has been established. Dushich prepared
   `lynx/tools/lynx_cellular_inventory.py` with offline tests for a repeatable
   metadata-only check. After Noobia Wi-Fi returned, it ran from RAM on the
   same V53 boot, with clean post-check health and RAM cleanup. A live CCCI
   kernel message reports
   `md_state = 0` repeatedly; firmware boot and radio function remain
   unproven. Read-only CCCI sysfs says the bootloader loaded MD material, while
   stock `ccci_mdinit` includes a modem-start path. Keep the SIM out and do not
   run that daemon or write CCCI controls as a status probe. See the cellular
   inventory record before any modem action.
   The documented GNSS outdoor trial in `LYNX-CONNECTIVITY-PRECAL.md` uses
   `trial_v52_gnss_mnld.py`, whose preflight requires the exact older V52
   kernel hash. On the current V53 boot, its GNSS modules, device nodes, and
   RAM daemon bundle are absent; review the guard and prerequisites for V53
   before reuse.
2. Flashlight has a verified bounded pulse from one rear LED. The second rear
   light and safe persistent startup need separate investigation. Avoid the
   stock flashlight core unload sequence that previously lost SSH.
3. GC02M1 macro and IMX355 wide produced recognizable frames using a patched
   ISP module loaded in RAM. The stock ISP caused a YUV-B IRQ storm. Main
   IMX890 and front S5K3P9SP remain untested. A stock camera-control ioctl
   caused a kernel Oops; avoid repeating it. Package the patched module on
   Alpine only after a guarded cold-boot test and local disable switch.
4. Continue adding small local agent tools for verified hardware, with the
   same bounded behavior and explicit validation as the motion tool. Do not
   label an inventory-only interface as a working capture or actuator.

## Recovery and collaboration

- Keep V53 and V50 images intact. [Kernel-to-agent gate](LYNX-KERNEL-TO-AGENT-GATE.md)
  says no new `boot_a` flash is needed for the verified camera paths.
  [Recovery steps](RECOVERY-AND-FIRST-BOOT.md) remain the authority before a
  boot trial.
- Dushich works through the local `dushich` CLI and can take bounded offline
  coding tasks in his separate workspace. Aria reviewed and corrected two
  edge cases before adopting his policy and motion code. The session-bound
  MCP bridge failed in this very long conversation with an `Argument list too
  long` context handoff; the direct CLI worked. Banshee and Noob are working
  on the long-conversation issue. Retry the verified bridge in a new session
  with a bounded context, and inspect his result before phone deployment.
- Start from [the code map](/noobia/docs/noobs/LYNX.md),
  [agent notes](LYNX-AGENT.md), and [camera plan](LYNX-CAMERA-PORT-PLAN.md).
