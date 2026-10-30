# Lynx Bluetooth NRP/1 service boundary

## Proven base

V52's stock shared-radio calibration and `/dev/stpbt` work. A bounded,
RAM-only H4 bridge registers a standard `hci0` through the kernel's built-in
`N_HCI` line discipline. A narrow capability correction clears only the
controller's false synchronization-train claim. BlueZ then enumerates and
powers on the controller. The bridge can apply Lynx's read-only factory
address to controller RAM before registration. The exact trial and recovery
receipts are in [the connectivity report](LYNX-CONNECTIVITY-PRECAL.md).

The original bridge trial ran for at most 20 seconds. BlueZ and D-Bus remain
disabled at boot. A separate OpenRC service now runs bounded same-boot GATT
trials; it is still disabled at boot.

## Service design

1. Keep the existing V52 boot image and Wi-Fi/SSH independent of Bluetooth.
   Build a separate OpenRC `lynx-bluetooth` service, disabled by default until
   cold-boot tests pass. Its STOP command must close the PTY and `/dev/stpbt`,
   power off the controller, stop its BlueZ child, and restore the previous
   firmware search path.
2. Store the seven matching August firmware files under a root-owned Lynx
   service directory with a manifest of SHA-256 hashes. Verify all hashes
   before opening the radio. Use a private mount namespace for `devpts` and
   keep the one-bit capability correction explicit and audited.
3. Read the factory Bluetooth address from `nvdata` through a transient
   read-only, `noload` mount in that private namespace. Apply it to controller
   RAM before registering `hci0`; verify the result. Never modify `nvdata`.
4. Expose NRP/1 through a Lynx-specific GATT service with a write request
   characteristic and a read reply characteristic. Reuse the NRP/1
   wire grammar, native IDs, VM, sequencer, and thread classes already served
   over Wi-Fi. Do not create a separate runtime instance with different VM
   state. Add a local Unix socket to the existing `lynx-noobd` process so the
   Bluetooth service can pass complete request lines to that same runtime.
5. Bound each signed BLE request to 512 bytes, one line, and a five-second
   assembly timeout. Fragment requests into ATT writes and read replies with
   GATT offsets. Tag every reply with its NRP/1 request ID. Reject malformed
   frames before invoking a native call. Keep pairing disabled; a peer MAC by
   itself is not authentication.

Iris uses the inverse direction: she is a BLE client of a Nexus-hosted GATT
service using the Noobian UUID family. That service's bridge has one
notification socket and is built around Iris. Lynx should not attach to it
as a second client until multiplexing and peer identity are explicitly
implemented. Matching the **NRP/1 protocol** does not require sharing one
GATT connection or one VM instance.

The root-only Unix socket is now installed at `/run/lynx/noobd.sock` in the
**same** `lynx-noobd` process as the Wi-Fi endpoint. The guarded V52 install
verified a local `PING`, Nexus TCP `PING`, and healthy services without a boot
partition write. Receipt:
`lynx/logs/v52-noob-local-socket-1793386552572118101/result.json`.
The prior runtime and OpenRC script are saved on Lynx as `.before-local-socket`.

`tools/lynx_ble_gatt_probe.py` first exposed read-only `PING` and `INFO`.
The bounded initial trial registered this service with BlueZ, and Nexus
discovered, connected without pairing, and exchanged `PING`/`PONG`. The trial
stopped BlueZ and D-Bus, restored the firmware search path, canceled its reboot
watchdog, and found Alpine healthy. Receipt:
`lynx/logs/v52-bluetooth-hci-1793387060460429646/result.json`.

The GATT endpoint is still disabled at boot. It now holds response state per
BlueZ device path, with a 30-second expiry. The phone's stock and V50 rollback
images were not touched.

A persistent-service candidate is installed in `tools/lynx_bluetoothd.py`,
`tools/lynx-bluetooth-openrc.sh`, and
`tools/lynx-bt-firmware-sha256.json`. It verifies the V52 boot image and all
seven August firmware hashes, reads the factory address from a no-replay
read-only mount in a private mount namespace, checks battery and temperature,
and orders GATT, BlueZ, and bridge shutdown. The bridge and GATT application
can now run until SIGTERM. Two consecutive guarded same-boot trials started
the OpenRC service, completed an unpaired BLE `PING`/`PONG`, stopped the
service, verified `hci0` disappeared and Alpine stayed healthy, and canceled
the reboot watchdog. Receipts:
`lynx/logs/v52-bluetooth-service-1793387841289277717/result.json` and
`lynx/logs/v52-bluetooth-service-1793387879934353074/result.json`.
After correcting NRP `INFO`'s old `alpine-v50` label to `alpine-native`, a
third guarded cycle completed both `PING` and the longer `INFO` reply over
BLE, then stopped cleanly. Receipts:
`lynx/logs/v52-noob-info-1793388045443552045.json` and
`lynx/logs/v52-bluetooth-service-1793388079764856722/result.json`.
The passive install receipt is
`lynx/logs/v52-bluetooth-install-1793387653308913027/result.json`.
**The service is still disabled at boot.** Cold-boot, sustained battery use,
and automatic recovery after a child crash remain unverified.

## Nexus-issued controls and audible VM trial

`tools/lynx_ble_auth.py` signs the exact NRP/1 request with HMAC-SHA256, a
fresh 32-byte challenge, and a strictly increasing sequence number. It rejects
malformed, oversized, tampered, and repeated frames. The root-owned Lynx key
at `/etc/lynx/nrp-nexus.key` and the Nexus key under `lynx/private/` are
mode 0600; the key is ignored by Git and has never been logged. Wi-Fi TCP uses
the same signature plus its Nexus source-IP restriction. The local root-only
Unix socket remains available to Lynx processes, and BLE forwards accepted
commands to that *same* runtime. Controls are therefore available remotely
only to a holder of the Nexus key, while local root can still issue commands.

The guarded install receipt is
`lynx/logs/v52-nexus-issuer-1793389116664130594/result.json`. It verified
authenticated TCP `PING`, `INFO`, and VM status, and rejected unsigned TCP.
The first guarded BLE trial rejected an unsigned request, ran a one-byte HALT
VM, reset it, and stopped with healthy Alpine:
`lynx/logs/v52-bluetooth-service-1793389134959764392/result.json`.

The audible trial in
`lynx/logs/v52-bluetooth-service-1793389426154835667/result.json` sent one
authenticated `CALL_MIXED SOUND_PLAY "beep"` command, then loaded and ran a
24-byte VM program that called native `SOUND_PLAY` twice with a 1200 ms wait.
The VM halted, its return register was 1, and `RESET_VM` restored EMPTY. Noob
reported hearing all three beeps. The service stopped, `hci0` disappeared,
Alpine health passed, and the watchdog was canceled. An earlier attempted
audible trial used an unquoted sound name; Lynx rejected it before playing,
and its guarded teardown also passed. No boot partition was written.

Audio had been stopped when the test began. `rc-service lynx-audio start`
loaded the existing MT6983 card and firmware, and `AUDIO_READY` returned
`card=1 firmware=1` before the audible trial. Keep this as a preflight for
later sound tests.

The object tree, registration, advertising, and read/write option contracts
follow the official [BlueZ GATT API](https://bluez.readthedocs.io/en/latest/gatt-api/)
and [Advertising API](https://bluez.readthedocs.io/en/latest/advertising-api/).
The Nexus client uses the documented [Adapter](https://bluez.readthedocs.io/en/latest/adapter-api/)
and [Device](https://bluez.readthedocs.io/en/latest/device-api/) methods.

## Acceptance sequence

- Service starts and stops repeatedly on the same boot, leaving Wi-Fi and
  Alpine healthy and no `hci0` after STOP. **Done three times.**
- BlueZ reports Lynx's factory address and the expected power state. A
  same-boot restart did not switch back to MediaTek's placeholder address.
  **Done; cold boot still untested.**
- Nexus discovers the dedicated Lynx service, connects, and completes
  bounded `PING` and `INFO` exchanges without pairing. **Done**, with signed
  commands and an unsigned-request rejection test.
- A simple native call, a VM load/run/status cycle, and disconnect/reconnect
  use the same runtime state seen over Wi-Fi. **Native call and VM done;**
  disconnect/reconnect preserving VM state still untested.
- A cold boot with the service enabled retains display, battery monitoring,
  thermal limits, Wi-Fi, SSH, and the V50 Fastboot rollback. Any service
  failure leaves SSH available and Bluetooth off.
