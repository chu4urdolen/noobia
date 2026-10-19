# Lynx Alpine PID 1 hardware milestone

On 2026-10-20, Lynx (OnePlus Nord 3 CPH2493 / MT6983) ran Alpine Linux
3.24.2 with OpenRC 0.63.2 as **native PID 1** on the stock 5.10.149 kernel.
Pinned Wi-Fi SSH remained reachable at `192.168.100.4`, the persistent ext4
root on `userdata` was mounted, and the phone-side health supervisor passed
after handoff. OpenRC's `lynx-health` service reached `started` in its default
runlevel. Native Alpine Python 3.14.8 and Git 2.54.0 also ran in the root.

On the same boot, signed Alpine `dropbear` and `dropbear-openrc` packages
were installed on the persistent root. A separate Alpine Dropbear daemon
accepted pinned-key login at `192.168.100.4:2222` using the same host key as
the rescue daemon on port 22. The custom `lynx-dropbear` OpenRC service
adopted that live process without interruption and is enabled in the
default runlevel. Receipts:
`logs/alpine-dropbear-install-1792446317107196658/result.json`,
`logs/alpine-dropbear-2222-trial-1792446420853903013/result.json`,
`logs/alpine-ssh-openrc-1792446536010993475/result.json`, and
`logs/alpine-ssh-openrc-1792446553988516771/result.json`.
The runlevel link created by `rc-update` is absolute
(`/etc/init.d/lynx-dropbear`); an initial verifier expected a relative link
and falsely marked the successful enable operation incomplete. The corrected
verifier then passed. No `boot_a` write or reboot occurred for this stage.

Signed Alpine `wpa_supplicant`, `wpa_supplicant-openrc`, and `iproute2`
packages were also installed, but no Alpine Wi-Fi service was started:
`logs/alpine-wifi-install-1792446612004066034/result.json`. Alpine's
`wpa_cli` timed out against the current rescue-stage WPA control socket;
the rescue-stage client still reported `wpa_state=COMPLETED` and
`192.168.100.4`. The `lynx-wifi` OpenRC service subsequently adopted the
existing associated WLAN without restarting WPA or DHCP. Its private
configuration was copied phone-to-phone into the Alpine root with mode
`0600`; the contents and hash were not logged. Both `lynx-wifi` and
`lynx-dropbear` are now enabled in the default runlevel, with rescue SSH
still listening on port 22. Receipts:
`logs/alpine-wifi-openrc-1792446767347104772/result.json` and
`logs/alpine-wifi-openrc-1792446772729967886/result.json`. Alpine's
own association and DHCP startup path remains **untested on hardware**;
do not disturb the live Wi-Fi process until an independent reconnect path
exists.

The decisive host capture is
`logs/v33-first-handoff-observation-1792446062978025910/`: `/proc/1/exe`
resolved to `/run/lynx/persistent-alpine/sbin/openrc-init`, `/proc/1/root`
resolved to the same Alpine root, and `/proc/1/root/etc/alpine-release` read
`3.24.2`. The reusable `tools/verify_alpine_pid1.py` then checked the same
boot ID, PID 1 path and root, Alpine release, ext4 mount, OpenRC service,
inherited Wi-Fi SSH, Python, Git and a fresh health sample. Its receipt is
`logs/v33-alpine-pid1-verification-1792446158439995141/result.json`; the
OpenRC command `/bin/rc-status -a` showed `lynx-health [ started ]`.

## Why earlier handoffs refused

V29 and V32 booted BusyBox and reached SSH, but PID 1's final safety guard
returned nonzero. V32 retained the error in `/run/lynx/openrc-pid1-stderr.log`:
`sh: write error: Bad file descriptor`. PID 1 had no descriptor 0 or 1.
The guard's final success message failed to write to closed stdout; its
checks were otherwise passing. A pinned RAM-only experiment reproduced that
failure with stdout closed and passed after reopening standard descriptors:
`logs/pid1-stdio-diagnostic-1792445807386439038/result.json`.

V33 changes **only primary `/init`** relative to the hardware-booted V32:
before the guard, PID 1 opens stdin from `/dev/null` and directs stdout and
stderr to separate RAM logs. The stock kernel, V32 supplementary payload,
module and Wi-Fi startup, bounded guard retries, boot tail, and unrelated
ramdisk members are identical. Offline BusyBox syntax, archive roundtrip,
retry fixtures and AOSP AVB model checks passed in
`linux-port/artifacts/persistent-openrc-v33-offline/validation.json`.
The AOSP model is not the OnePlus bootloader; the hardware receipt above is
the boot evidence.

## Repeat the supervised trial

Keep the exact V19 rollback image and stock recovery artifacts available.
Only `boot_a` may be written for this trial; do not switch slots. Keep USB
disconnected during native boot and do not test native charging yet.

1. In Fastboot with USB connected, run `python3 tools/lynx_fastboot_preflight.py --connect` and require the expected serial, unlocked slot A, bootloader and sizes. New USB nodes may need a **node-scoped** ACL for the local user.
2. Check `python3 tools/lynx_boot_a_v33_trial.py --prepare`. Start `python3 tools/lynx_wifi_v19_contact.py --listen --fast-ack --seconds 600` and retain its fresh receipt path.
3. Run `python3 tools/lynx_boot_a_v33_trial.py --flash-v33 --collector-receipt <listener-result.json>`. It writes only `boot_a` and does not reboot. Keep the flash receipt.
4. With Noob at the cable, run `python3 tools/lynx_boot_a_v33_trial.py --reboot-after-v33 --collector-receipt <listener-result.json> --flash-receipt <flash-result.json>`. Unplug USB immediately when Fastboot departs. Wait for pinned native SSH.
5. Within the fresh-boot window, run `python3 tools/launch_local_health_ram_trial_v31.py --run --contact-receipt <contact-result.json> --usb-unplugged-confirmed`. Require `local-health-in-ram-verified` before proceeding.
6. Run `python3 tools/arm_v33_openrc.py --contact <contact-result.json> --health <health-result.json> --arm`. This writes a one-boot RAM marker; PID 1 independently rechecks the guard and persistent root.
7. Verify the same boot ID, `/proc/1/exe`, `/proc/1/root`, Alpine release, `userdata` mount, `rc-status -a`, SSH and a fresh health check. Save stdout, stderr and logs before any reboot.

Trial receipts: V33 `boot_a` write
`logs/v33-boot-a-trial-1792445914513243332/result.json`, separate reboot
`logs/v33-boot-a-trial-1792445920287863995/result.json`, pinned contact
`logs/wifi-v19-contact-1792445911633295372/result.json`, V31 health
`logs/local-health-v31-ram-trial-1792446026167719022/result.json`, and
one-boot handoff arm `logs/v33-openrc-arm-1792446052738563577/result.json`.

If a future trial must be undone, first return to Fastboot and run fresh
preflight. The independent rollback path is
`python3 tools/lynx_boot_a_v33_trial.py --restore-v19`; its exact source is
`linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img`
with SHA-256 `5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851`.
Stop if Fastboot identity or recovery behavior differs.

## What remains

V33 still requires host contact, RAM health startup and a one-boot handoff
marker. Wi-Fi, DHCP and rescue SSH on port 22 started in the BusyBox stage;
Alpine now owns the additional SSH daemon on port 2222 and has adopted
the existing Wi-Fi connection, but neither service has been tested across
a cold boot. Native Wi-Fi startup and restart remain unproven. Native
charging and a self-booting thermal policy remain
unvalidated. The current Alpine milestone is real and reproducible, but
Lynx is not yet independent of the Nexus at cold boot.
