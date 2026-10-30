# Lynx Bluetooth NRP/1 service boundary

## Proven base

V52's stock shared-radio calibration and `/dev/stpbt` work. A bounded,
RAM-only H4 bridge registers a standard `hci0` through the kernel's built-in
`N_HCI` line discipline. A narrow capability correction clears only the
controller's false synchronization-train claim. BlueZ then enumerates and
powers on the controller. The bridge can apply Lynx's read-only factory
address to controller RAM before registration. The exact trial and recovery
receipts are in [the connectivity report](LYNX-CONNECTIVITY-PRECAL.md).

The tested bridge runs for at most 20 seconds. BlueZ and D-Bus are installed
but disabled at boot. A temporary controller is not yet a persistent Bluetooth
service, and no GATT or NRP/1 frame has crossed this BlueZ path.

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
   characteristic and a notification reply characteristic. Reuse the NRP/1
   wire grammar, native IDs, VM, sequencer, and thread classes already served
   over Wi-Fi. Do not create a separate runtime instance with different VM
   state. Add a local Unix socket to the existing `lynx-noobd` process so the
   Bluetooth service can pass complete request lines to that same runtime.
5. Bound each BLE request to 4096 bytes, one line, and a finite assembly
   timeout. Fragment replies at the negotiated ATT MTU; tag every reply with
   its NRP/1 request ID. Reject malformed frames without invoking a native
   call. Keep pairing disabled until a tested authorization policy restricts
   control to Nexus. A peer MAC by itself is not authentication.

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

`tools/lynx_ble_gatt_probe.py` is the first live-tested GATT application.
It accepts only complete `NRP/1 <id> PING` and `INFO` lines, forwards them to
the root-only socket, and exposes the response through a separate read
characteristic. It has no VM or actuator command path. The bounded trial
registered this service with BlueZ, and Nexus discovered, connected without
pairing, resolved the service, wrote `NRP/1 52 PING`, and read
`NRP/1 52 OK PONG`. The trial stopped BlueZ and D-Bus, restored the firmware
search path, canceled its reboot watchdog, and found Alpine healthy. Receipt:
`lynx/logs/v52-bluetooth-hci-1793387060460429646/result.json`.

The GATT endpoint is still disabled at boot. The response
characteristic is shared among peers, so only non-sensitive diagnostic replies
belong there until per-connection state and authorization are implemented.
The phone's stock and V50 rollback images were not touched.

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
per-client authorization, and automatic recovery after a child crash remain
unverified.

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
  bounded `PING` and `INFO` exchanges without pairing. **Done**;
  authentication is still needed before controls are exposed.
- A simple native call, a VM load/run/status cycle, and disconnect/reconnect
  use the same runtime state seen over Wi-Fi.
- A cold boot with the service enabled retains display, battery monitoring,
  thermal limits, Wi-Fi, SSH, and the V50 Fastboot rollback. Any service
  failure leaves SSH available and Bluetooth off.
