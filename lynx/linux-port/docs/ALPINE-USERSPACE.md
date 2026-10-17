# Native Alpine userspace and syscall tracing on Lynx

Alpine 3.24.2 ARM64 now executes on Lynx in
`/run/lynx/alpine-3.24.2`. Its shell, musl runtime and APK 3.0.8 package manager
passed the same probe in an isolated exact-stock-kernel VM and on the phone.
APK then installed `strace` 6.19-r1 and its dependencies from the signed Alpine
repositories; a real traced `/bin/true` child exited successfully. A later
isolated VM test also booted the Alpine shell directly as PID 1; see
[Alpine startup and storage](ALPINE-STARTUP-STORAGE.md).

This is a RAM chroot under the already-running native Linux kernel. PID 1
remains the proven BusyBox init. Wi-Fi, pinned SSH and the three temperature
watchers remain in the original environment. No partition was written, no
service replaced, and no new network namespace was created. The initial trial
added no mounts; the later observability step mounted read-only proc and sysfs
inside the chroot. This is a userspace foundation for further Linux work, not
a completed postmarketOS port or a replacement PID 1 boot on the handset.

The later [offline runtime stage](ALPINE-RUNTIME-STAGE.md) combines the verified
inputs and read-only kernel views into an optional step after host-assisted
power setup, with cold VM tests and live verification of the existing phone
environment.

## Use it now

From `/noobia/lynx`:

```sh
tools/lynx-alpine apk info -v
tools/lynx-alpine strace -o /tmp/example.trace /bin/true
tools/lynx-alpine cat /tmp/example.trace
```

The wrapper selects the newest verified continuous session and matching rootfs
trial, checks the original boot ID and rootfs release, and obtains a fresh
native identity proof before execution. It quotes individual arguments and
preserves stdout/stderr and timestamps through `lynx_live_command.py`.
Commands are bounded to 60 seconds. After a reboot it refuses the old RAM
receipt rather than assuming the rootfs survived.

Paths inside the chroot refer to that RAM filesystem. The existing kernel,
process namespace and network are shared with the original environment.
`strace` was tested on a short-lived child; the temperature watchers were not
attached to or stopped.

## Verified inputs

The [official Alpine download page](https://www.alpinelinux.org/downloads/)
provided the ARM64 mini rootfs and release-key fingerprint. Source archive:

`https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-minirootfs-3.24.2-aarch64.tar.gz`

SHA256:
`9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773`.

Both published SHA256/SHA512 checks passed. GPG verification passed against
the primary key fingerprint published on Alpine's site:
`0482D84022F52DF1C4E7CD43293ACD0907D9495A`.
The key was downloaded from `https://www.alpinelinux.org/keys/ncopa.asc` and
its primary fingerprint checked before import. GPG status captures retain the
actual `VALIDSIG`; no trust override was used to execute an unverified archive.

The archive contains 514 non-root entries, 8,655,157 regular-file bytes and 17
ARM64 ELF files. `alpine_rootfs.py` rejects unsafe member paths and members
below non-directory parents, bounds sizes, resolves required executable links
in memory, and checks ARM64 ELF/interpreter compatibility. The host reader
does not extract through archive symlinks. The phone verifies the archive hash
again before extracting into a newly created directory on the `/run` tmpfs.

## Hardware procedure and observations

`install_alpine_rootfs.py` requires the signed archive receipt, successful
matching stock-kernel VM evidence and a current native continuous-session
receipt. It first verifies the working power setup and boot ID, requires a
recent valid battery snapshot, battery below 35°C and charge at least 20%,
charger offline, and at least 128 MiB available memory. It refuses an existing
rootfs directory or archive. Every subsequent phase is bound to the same boot.

The initial attempt stopped before upload because a Python string converted
a shell backreference into a control character. The command was simplified
and control-character rejection added. That failure is retained. The second
trial uploaded, checked, unpacked and ran the probe successfully, then verified
the original power runtime again.

Lynx's wall clock was initially in 1970. `sync_lynx_clock.py --sync` explicitly
set Linux wall time from Nexus so normal HTTPS certificate checks could work.
It recorded before/after wall time, uptime and unchanged boot identity. It did
not write the hardware RTC and is not a precision synchronization service.

`alpine-diagnostics.sh` copied the existing resolver configuration into the new
rootfs, created its basic `/dev` nodes and performed a bounded signed APK
transaction. It retained normal HTTPS certificate and package signature
checks. The seven added packages were:

| Package | Version |
| --- | --- |
| strace | 6.19-r1 |
| libdw, libelf | 0.195-r0 |
| libbz2 | 1.0.8-r6 |
| musl-fts | 1.2.7-r7 |
| xz-libs | 5.8.4-r0 |
| zstd-libs | 1.5.7-r2 |

The resulting environment had 23 installed packages. Native tracing recorded
`execve`, memory setup, `getuid`, and a successful `exit_group(0)`.
Post-checks kept the same boot and BusyBox PID 1; battery was about 22°C,
82% and −60 mA in the final runtime snapshot. This is not an idle-power claim.

## Repeat and offline reconstruction

The VM test and RAM installer are separate from V19 and the battery resume
worker. Reuse the unchanged, verified input receipts after the next otherwise
needed boot; the current phone does not need a reboot for this work.

```sh
python3 tools/test_alpine_rootfs_kernel.py --rootfs-receipt ROOTFS_RECEIPT
python3 tools/install_alpine_rootfs.py --session SESSION_RECEIPT \
  --rootfs-receipt ROOTFS_RECEIPT --vm-receipt VM_RECEIPT --install
```

`fetch_alpine_rootfs.py --download` reproduces the official download and GPG
verification when a new local copy is needed. The installer leaves partial
state for diagnosis after a failed phase; it never cleans unrelated files or
powers off the phone.

The native APK fetch also cached nine dependency files. The resolver selected
a newer zlib than the already-installed base, so the filtered replay bundle
contains only the exact seven newly installed packages. Base musl and zlib
remain supplied by the pinned mini rootfs.

A fresh VM rebuilt that seven-package environment with networking disabled,
standard package signature checks and explicit package caching, then traced a
child successfully. The first offline test correctly refused local packages
without caching; enabling caching resolved it without a force option.
`export_alpine_apk_cache.py` verifies the successful VM/package hashes and
exports only those exact seven APKs, with a round-trip-checked bundle manifest.

The offline install command exercised in the VM was:

```sh
apk --no-network --repositories-file /dev/null \
  --cache-dir /tmp/lynx-offline-apks --cache-packages \
  add /tmp/lynx-offline-apks/*.apk
```

Provide `/dev/null` and unpack the filtered bundle into the new chroot's `/tmp`
before using that command. The offline replay passed in the exact-kernel VM;
the phone's actual package install used HTTPS. A complete fresh-boot combined
hardware replay has not been performed.

## OpenRC as a real init process

Alpine's signed `openrc` and `openrc-init` 0.63.2-r0 packages have now been
installed into a separate scratch copy of the verified ARM64 rootfs with APK
signature verification enabled. A QEMU test packs that complete root at the
initramfs root, mounts proc/sysfs and tmpfs `/dev`, then `exec`s OpenRC from
`/init` so it becomes PID 1. With the frozen V19 stock kernel it reached the
default runlevel, ran a test service, handled `openrc-shutdown --poweroff now`,
and powered down cleanly. `tools/test_openrc_bundle_replay.py` now reproduces
the full step offline from the GPG-verified Alpine rootfs and six cached APKs:
it checks each APK signature, installs with network and package scripts
disabled, then boots the result. The final VM result and console are
`linux-port/artifacts/openrc-userspace-vm-1792236672087913929/`; the whole
replay receipt is `linux-port/artifacts/openrc-bundle-replay-1792236671965134306/`.
`tools/export_openrc_apks.py` re-verifies and hashes the local APK bundle.

This proves OpenRC itself can run on the exact ARM64 kernel/userspace pairing
in a VM using an offline, signature-checked package replay. It is not a handset
boot, and its scratch root intentionally lacks normal package post-install
service links; the test service supplies only the default-runlevel proof. The
phone's proven V19 init still owns early hardware, Wi-Fi and SSH startup.
Battery and thermal watchers have been verified in separate native sessions;
their startup from a cold V19 boot must be included and verified before any
OpenRC PID 1 handoff. Do not replace that startup sequence until those
safeguards and the OpenRC handoff are integrated and tested on a reachable
native session.

`tools/export_openrc_rootfs.py` now exports the signed-package replay as a
deterministic standalone Alpine/OpenRC `newc` root archive. It omits only the
downloaded APK cache, verifies a round trip, and records the package and base
rootfs provenance. Archive:
`linux-port/artifacts/openrc-rootfs-export/alpine-openrc-rootfs.cpio.gz`,
SHA256 `88efe68505c7b98645d24e4e1cff7678073fbfd610011928ee3f92b76399571a`,
4,496,025 bytes. `tools/measure_openrc_payload_fit.py` inserts that archive into
a temporary copy of the V19 supplement in memory and round-trip checks it. The
combined payload measures 16,682,636 bytes, below V19's strict 40,000,000-byte
loader limit by 23,317,364 bytes. This is a size measurement only: no updated
boot image has been built and the root archive remains inert.

`tools/test_openrc_pid1_handoff_vm.py` adds a second, more realistic VM check:
BusyBox mounts the early kernel interfaces, starts a long-lived worker, binds
proc/sys/dev/run into the exported Alpine root and replaces itself with
`openrc-init`.
An OpenRC default-runlevel service confirms the earlier worker survived the
PID 1 handoff, then requests a clean VM poweroff. It passed against the same
V19 kernel fixture at
`linux-port/artifacts/openrc-pid1-handoff-vm-1792237351578370070/` in 8.75s.
Two earlier harness failures are preserved alongside it: one exposed missing
parent directories in the synthetic initramfs; the next exposed that the VM
must explicitly include the Alpine root's parent directories. This remains a
QEMU handoff-mechanics test. It does not exercise V19's phone-specific driver,
Wi-Fi, SSH, or battery/thermal setup, and it is not a handset image.

## Opt-in OpenRC candidate with a fail-closed power gate

`tools/build_openrc_gated_candidate.py` builds a separate local V20 candidate
from the unchanged V19 image, embeds the exported OpenRC root, and changes only
the initramfs policy. The 64 MiB image is
`linux-port/artifacts/openrc-gated-v20-guardv6/nord3-openrc-gated-candidate.img`
with SHA256
`53156a5f9722eb799f2e27c777d3f63a143fbde339851a3f81683bb0bf9a2dad`.
Its combined payload is 16,686,490 bytes, below the existing strict 40,000,000
byte limit. The file inherits the V19 Wi-Fi and SSH credentials and is mode
0600; it and all binary inputs stay local and are not published.

After the original pinned SSH contact, the candidate keeps the BusyBox PID 1
and the V19 beacon alive for up to 30 minutes while separate host tools load
the reviewed SoC temperature module, install the battery gauge monitor, and
start the existing temperature, battery, and soft-throttle watchers. No valid
gate means the original BusyBox Wi-Fi/SSH environment remains running. The
gate requires matching per-boot tokens, live watcher processes with exact
source hashes, the identified battery monitor and readable gauge, a fresh
error-free battery sample below 35°C with at least 20% charge, one SoC and two
CPU sensors all below 40°C, and exactly three present CPU cooling controls.
`tools/arm_openrc_handoff.py` writes the one-boot marker only after a fresh
pinned identity/boot-ID check and the same live guard passes. A refusal leaves
the marker unwritten.

Validation: `tools/test_openrc_handoff_guard.py` passes nine synthetic safety
cases; `tools/test_arm_openrc_handoff.py` accepts only the matching candidate,
native contact, and successful runtime-power receipts. The production
`openrc-handoff.sh` itself passed an isolated QEMU run with the exact V19 stock
kernel: it verified the root archive hash, extracted Alpine, bound proc/sys/dev/run,
replaced PID 1 with OpenRC, preserved a worker from BusyBox, ran a test service,
and powered down cleanly. Latest receipt:
`linux-port/artifacts/openrc-pid1-handoff-vm-1792238269248471845/`.
The VM substitutes a passing guard fixture because it has no Lynx sensors.
This still is not a handset boot, and OpenRC does not yet manage Lynx's Wi-Fi
or SSH services. No phone was contacted and no partition was changed.

For a future supervised V20 boot, the host stages must run in this order:

```sh
python3 tools/lynx_wifi_v19_contact.py --listen --seconds 600
python3 tools/lynx_sensor_trial.py --listen --keep-running --seconds 300
python3 tools/resume_battery_session.py --start --runtime-power
python3 tools/arm_openrc_handoff.py --session CONTACT_RECEIPT \
  --runtime-power RUNTIME_POWER_RECEIPT --arm
```

The first listener receipt and runtime-power receipt must belong to that same
boot; the armer checks the V20 image hash, pinned native identity, token, boot
ID, live watcher scripts, and current sensor/gauge state before writing the
marker. The first three host-side steps and the complete fresh-boot sequence
remain untested together on Lynx. Keep the existing stock restore procedure
and bootloader/recovery path intact; do not treat the offline candidate or VM
pass as a reason to flash before that supervised hardware validation.

The stock OTA also identifies a real integration constraint for Wi-Fi: its
`wlan_drv_gen4m_6983.ko` matches the exact 5.10.149 kernel, but depends on the
MediaTek/Oplus connectivity stack (`conninfra`, `wmt_chrdev_wifi_connac2`,
`connfem`, `connadp`, `mddp`, `ccci_md_all`, `oplus_wificapcenter`,
`oplus_project`, `pmic_lbat_service`, and `emi-mpu`). Android init waits for
`vendor.connsys.driver.ready=yes` before inserting the radio modules. The OTA's
`wmt_loader` and `conninfra_loader` use Android's `/system/bin/linker64`, so
they cannot be assumed to run inside Alpine/musl. V19 already has its own
tested native module/firmware startup path; reuse that path rather than trying
to start the Android loader from OpenRC. The August OTA contains the `soc7_0`
firmware family and `WIFI_RAM_CODE_soc7_0_1_1.bin`; this inventory alone does
not establish which calibration or firmware files the Linux path should load.

## Development layer and recoverable checkpoint

During one verified continuous native session, the existing RAM chroot grew
from 23 to 49 signed Alpine packages. Python 3.14.8 passed ARM64, OpenSSL,
SQLite in-memory query, and thread/hash checks; Git 2.54.0 and Make 4.4.1
started successfully. All 23 earlier package versions were pinned during the
APK transaction. The command preserved the original boot ID and all three
thermal/battery watcher processes. It increased the `/run` tmpfs size limit
from 128 to 256 MiB; it did not preallocate that memory. The package install
itself used about 65 MiB in the chroot. Receipt and raw output:
`logs/live-alpine-development-1792183223446552019/`.

That development layer was RAM-only and was lost when Lynx left the session.
The earlier base Alpine checkpoint remains on Nexus at
`checkpoints/alpine-runtime-1792183113469592155/`; its gzip archive SHA256 is
`8777d923ad8473066026d2a62f3c050581be4b28c5bfa53d0dde0e9a8c83559c`.
The package/world inventory was stable across capture. Its exact Alpine tree
was reconstructed without extracting files onto Nexus and booted in an
isolated QEMU VM with the frozen V19 stock kernel. The APK inventory and world
file matched byte-for-byte, and the VM powered down cleanly:
`linux-port/artifacts/alpine-checkpoint-restore-1792234450094278990/`.
This restore proves the saved **base** userspace can be reconstructed; it does
not include Python, Git or Make, and it is not a phone boot or a write to a
phone partition. Earlier failed VM harnesses are retained beside the passing
receipt.

`tools/continue_alpine_development.py --resume-receipt RECEIPT` waits for the
guarded resume workflow to bring the native session and Alpine base back. It
then verifies the existing power watchers, installs the pinned development
layer, runs the read-only Python system report, captures a new checkpoint,
and tests that exact development checkpoint under QEMU. The workflow is bounded
and records partial failures; it does not reboot, flash, or stop the phone.
The current unattended continuation is recorded under
`logs/alpine-development-continuation-*`.

## Private evidence

- Download/signature receipt: `downloads/alpine-rootfs-3.24.2-1792179591745064903`.
- Base VM: `artifacts/emulated-alpine-rootfs-1792179704020333357`.
- Failed preflight: `logs/alpine-rootfs-trial-1792179843361874646`.
- Successful hardware trial: `logs/alpine-rootfs-trial-1792179882804930040`.
- Clock receipt: `logs/live-wall-clock-sync-1792180049910851789`.
- Native signed install/trace: `logs/live-alpine-package-diagnostics-1792180076545347560`.
- Cached package capture: `logs/live-alpine-diagnostic-apk-cache-1792180285539775454`.
- Final native runtime check: `logs/live-alpine-final-runtime-1792180315544413582`.
- Failed/successful offline VMs: `artifacts/emulated-alpine-rootfs-1792180385903910645`
  and `artifacts/emulated-alpine-rootfs-1792180457219474992`.
- Filtered offline bundle: `artifacts/alpine-offline-diagnostics-1792180536171444327`.

Downloaded rootfs/packages, raw traces and VM artifacts remain local. The
repository publishes our tooling and instructions, not those binary inputs.
