# Syra desktop repairs — 2026-10-06

SSH: `ssh rose`, using the verified key documented in `network-current.md`.

## Chromium

Chromium refused startup because its existing profile had a stale
`SingletonLock` pointing to `raspberrypi-32887`, from before the host rename.
No Chromium process was running. Moved only the three Singleton symlinks into
`/home/rose/.local/state/noobia-repairs/chromium-locks-20261006-194844/`.
No browser profile data was removed.
Started Chromium with the user unit `noobia-browser.service`; process status
and a desktop screenshot confirmed it opened. A locked keyring prompt appeared;
the keyring and password-storage settings were left intact.

## Wireless keyboard diagnosis

Initially two receivers were present: YICHIP `3151:3020` and `3151:3000`.
Noob unplugged and replugged devices; only `3151:3020` remained at the latest
check. It exposes keyboard, mouse, system-control, and consumer-control input
devices, handled by `usbhid` / `hid-generic` and enumerated by libinput.
The device is authorized, runtime power status is active, autosuspend control
is `on` (no automatic suspension), and the input device is not inhibited.
Rose has input-device read access. No undervoltage is reported (`throttled=0x0`).

Bounded raw-input tests saw zero key/mouse events, including the latest test
of the remaining receiver. This does not establish whether keys were pressed
during the exact windows. The keyboard's brand/model, power state, wireless
mode, and receiver pairing still need confirmation. No firmware or pairing
commands were sent speculatively.

A visible diagnostic was installed at
`/home/rose/.local/state/noobia-repairs/syra-input-test.py`, from the local
`tools/syra-input-test.py`. It counts receiver events and includes a desktop
typing test, with no character logging or saved text. Its window was later
closed; `noobia-input-test.service` was inactive at the latest check.

Squeekboard, the touchscreen keyboard, is running and was visible on the
desktop. Syra's Bluetooth adapter is the built-in serial-attached controller;
no USB Bluetooth adapter appeared in the USB enumeration.

Other USB devices: two Huasheng hubs, Ubertooth One, u-blox GNSS receiver,
and TP-Link `2357:0141`, identified by its USB descriptor as an 802.11ac adapter.
The latter has no kernel driver bound in the observed USB topology. Its repair
is outside the current browser/keyboard priority.

## Nexus clipboard

`tools/shared-clipboard.py` runs as `noobia-shared-clipboard.service`, enabled
for the graphical session. It synchronizes current selected and explicitly
copied text through XWayland so middle-click and explicit paste share text.
Both transfer directions passed a cross-process test; previous clipboard text
was restored without logging it. No history is kept. Middle-click paste is
enabled. Images and other non-text payloads are not mirrored.
