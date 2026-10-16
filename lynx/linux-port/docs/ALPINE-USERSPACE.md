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
