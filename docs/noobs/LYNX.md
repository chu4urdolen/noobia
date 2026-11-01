# Lynx code map

Lynx is the OnePlus Nord 3 CPH2493 / MT6983. At the latest 2026-11-01
checkpoint, she is running trial V53 Alpine with Wi-Fi, SSH, and a Bluetooth
service started after boot. V53 waits for shared-radio calibration before
requesting Wi-Fi. Two monitored boots, including one short-uptime warm reboot,
and authenticated BLE trials passed. Long-uptime reboot reliability and
automatic Bluetooth startup remain unverified. V52
Bluetooth passes authenticated RAM-only start/stop trials after a healthy
boot, but long-uptime warm reboots have returned to Fastboot before rescue
SSH even after an explicit radio power-off and 60-second wait. V52 is not yet
a dependable reboot image. BusyBox rescue and the exact V50 rollback remain
available. Her observed Noobia address is
`192.168.100.107`. Check live identity and health before a hardware trial.
The persistent Alpine root uses `Europe/Sofia`; its local time was verified
after the latest V50 restoration.

| Need | Source and notes |
| --- | --- |
| Current hardware evidence | [`LYNX-HARDWARE-STATUS.md`](../../lynx/linux-port/docs/LYNX-HARDWARE-STATUS.md) |
| Shared Bluetooth/GNSS calibration and V52/V53 trials | [`LYNX-CONNECTIVITY-PRECAL.md`](../../lynx/linux-port/docs/LYNX-CONNECTIVITY-PRECAL.md) |
| Bluetooth NRP/1 service boundary | [`LYNX-BLUETOOTH-NRP.md`](../../lynx/linux-port/docs/LYNX-BLUETOOTH-NRP.md) |
| Trial sequence and known hazards | [`LYNX-REMAINING-HARDWARE-TRIALS.md`](../../lynx/linux-port/docs/LYNX-REMAINING-HARDWARE-TRIALS.md) |
| NRP/1 server and native calls | `lynx/tools/lynx_noob_runtime.py`; [`LYNX-NOOB-RUNTIME.md`](../../lynx/linux-port/docs/LYNX-NOOB-RUNTIME.md) |
| Nexus remote client | `lynx/tools/lynx_noobctl.py` |
| Nexus presence monitor | [`LYNX-PRESENCE.md`](../../lynx/linux-port/docs/LYNX-PRESENCE.md); `lynx/tools/lynx_presence.py` |
| Local hardware backend and agent wrappers | `lynx/tools/lynx_hardware.py`, `lynx/tools/lynx_microphone_level.py`, `lynx/tools/local_calls/`; [tool contract](../../lynx/linux-port/docs/LYNX-HARDWARE-TOOLS.md) |
| Display, keyboard, scrolling | `lynx/tools/lynx_drm_dmabuf_pattern.c`; [`LYNX-CONSOLE.md`](../../lynx/linux-port/docs/LYNX-CONSOLE.md) |
| Media control | `lynx/tools/lynx_media.py`; [`LYNX-MEDIA-CONTROL.md`](../../lynx/linux-port/docs/LYNX-MEDIA-CONTROL.md) |
| Microphone capture experiment | `lynx/tools/trial_v50_microphone.py`; external clap validated on V50 |
| Flashlight probe incident | `lynx/tools/trial_v50_flashlight_probe.py`; core unload hung, further trial paused |
| Boot restoration | [`RECOVERY-AND-FIRST-BOOT.md`](../../lynx/linux-port/docs/RECOVERY-AND-FIRST-BOOT.md) and `lynx/tools/lynx_boot_a_v50_trial.py` |
| V50 Alpine to Fastboot and retained logs | `lynx/tools/return_fastboot_from_alpine.py`, `lynx/tools/capture_v50_expdb_prefix.py`; [Bluetooth boot evidence](../../lynx/linux-port/docs/LYNX-BLUETOOTH-NRP.md) |
| Deferred cleanup after a stable build | [`LYNX-CLEANUP-WHEN-STABLE.md`](../../lynx/linux-port/docs/LYNX-CLEANUP-WHEN-STABLE.md) |
| One-shot OpenAI inference test | `lynx/tools/lynx_inference_probe.py`, `lynx/tools/trial_v50_openai_inference.py`; [inference notes](../../lynx/linux-port/docs/LYNX-INFERENCE.md) |

GPS, Bluetooth, and camera have matching stock modules. V52's shared-radio
calibration succeeded, Bluetooth answered HCI commands, and Nexus connected
to Lynx using her factory Bluetooth address. A bounded PTY bridge now also
exposes a standard `hci0` to BlueZ, and a guarded trial powered it on; BlueZ
is installed but not started automatically. A separate guarded trial completed
an unpaired NRP/1 `PING`/`PONG` over a temporary GATT service using the same
runtime as Wi-Fi. GNSS now emits NMEA through a
native listener; the latest GGA reported fix quality 0 and no position has yet
been measured. Microphone
level capture works locally and over NRP/1 for one second; an external clap
validated its acoustic response. Flashlight driver binding
was observed, then unloading
the core lost SSH; do not repeat that sequence until its failure is resolved.
The V50 boot image and recovery path must stay available during driver work.
