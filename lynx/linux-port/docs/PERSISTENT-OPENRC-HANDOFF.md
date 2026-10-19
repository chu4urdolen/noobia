# Persistent Alpine PID 1 handoff — guarded candidate, not flashed

Lynx now has a persistent Alpine 3.24.2 ext4 root in the first 1 GiB of
`userdata`. The currently running V19 BusyBox image is unchanged. Its Wi-Fi,
SSH and health supervisor remain available at `192.168.100.4` on the same
boot ID `3990a1d8-963d-4d17-972e-b0b8a7b366e6`.

`linux-port/persistent-alpine-probe.sh` and
`tools/probe_persistent_alpine.py` passed on the phone. The probe verified
partition identity, ext4 UUID, Alpine/OpenRC files, temporary `/dev`, `/proc`,
`/sys` and `/run` bindings, native Python/Git/procfs execution, and complete
unmounting. Receipt: `logs/persistent-alpine-probe-1792422556163098607/result.json`.
The reviewed OpenRC health adoption service is installed and enabled in the
persistent root; receipt:
`logs/persistent-openrc-health-install-1792422523913485537/result.json`.
OpenRC correctly refused a service-status request before it became PID 1;
that attempt is retained at
`logs/persistent-alpine-probe-1792422540277649053/result.json`.

The exact host-armed OpenRC safety guard passed on Lynx with live battery,
CPU/SoC thermal, cooling and watcher evidence:
`logs/persistent-openrc-live-guard-1792422739330121923/result.json`.
The preceding filename-only invocation did not call the guard; its receipt
`logs/persistent-openrc-live-guard-1792422725882772591/result.json` was
corrected to `invalid-test-invocation` with the reason preserved.

`tools/build_persistent_openrc_candidate.py` built the private V29 image at
`linux-port/artifacts/persistent-openrc-v29-offline/`. SHA-256:
`2483ba8d5ee43ef2ba692885682b9ebacc59fdb8216700eaad1eff7c531b3048`.
It inherits V19's exact stock kernel, Wi-Fi and SSH setup, adding only a
host-armed handoff script and the safety guard. Its supplement is about
12.2 MB, near V19's 12.2 MB; Alpine lives on `userdata`, not in `boot_a`.
Round-trip packing checked every primary/supplement member and rejected
unrelated changes. Independent syntax, stock-kernel and AOSP AVB model checks
passed at `linux-port/artifacts/persistent-openrc-v29-offline/validation.json`.
The AVB model accepted slot data for an unlocked device and rejected it for a
locked device; it is not the proprietary OnePlus bootloader.

`tools/test_persistent_handoff_live.py` exercised V29's handoff function up
to its final `exec` on the actual phone. The test changed only the guard's
temporary RAM path, the temporary mount-point name, and replaced the final
`exec` with reverse unmounts. The live safety guard, ext4 read-write mount,
partition/UUID/content hashes, all four bind mounts, Alpine Python chroot,
and final health check passed. It unmounted everything and left V19 PID 1,
boot ID, and health state unchanged. Receipt:
`logs/persistent-openrc-live-preexec-1792422904344014443/result.json`.
The temporary read-write mount changed ext4 metadata; the subsequent full
first-GiB hash is
`35a9763dd9f8e8aaa0f007e23d5c7047793d4b11a69d9e6881c58c2244fea7e0`,
at `logs/persistent-alpine-post-preexec-hash-1792422922572893069/result.json`.

V29 has **not** been flashed or booted. The final PID 1 `exec`, automatic
OpenRC service start, Wi-Fi/SSH process survival, and recovery from a failed
hardware boot remain unproven. The repository's general Linux-flash thermal
hold is still active: V29 depends on host-assisted health startup before its
handoff, and native charging remains unvalidated. Noob has been asked to put
Lynx in Fastboot and connect USB for a supervised trial. Before any write,
prepare a fresh pinned network collector, verify stock `boot_a` undo and exact Fastboot restoration, then
check Lynx's current Fastboot serial/slot/size. Only `boot_a` may be changed;
preserve slot B and recovery. A successful V29 boot initially stays in BusyBox
until the host verifies SSH and explicitly writes its handoff token in RAM.
That separates boot-image risk from OpenRC PID 1 risk. If boot or recovery
behaves unexpectedly, stop and use the verified restoration path.

The bounded trial scope is recorded in `V29-TRIAL-EXCEPTION.json`; it does not
clear the general thermal hold. `tools/prepare_persistent_openrc_trial.py`
verified exact V29, V19 and stock images, the matching stock OTA proof and
the pinned Fastboot binary without phone contact. Receipt:
`logs/persistent-openrc-offline-readiness-1792423153966857655/result.json`.
`tools/lynx_boot_a_persistent_openrc_trial.py --prepare` also passed offline.
Its `--flash-v29`, `--reboot-after-v29` and `--restore-v19` paths each require
a fresh read-only Fastboot identity/slot/partition preflight; the flash and
reboot paths also require a current pinned network collector and are separate
actions. No action path has been run. The collector now recognizes V29's exact
`/init` hash as well as V19's, after independently checking the built image.
For the timed trial, start `tools/lynx_wifi_v19_contact.py --listen --fast-ack`
before the Fastboot reboot. This mode saves pinned SSH proof and the
fallback-cancel acknowledgement, then returns immediately so RAM health
bootstrap can start inside its fresh-boot window. Full diagnostics are
deferred until health is ready and must be collected afterward.
