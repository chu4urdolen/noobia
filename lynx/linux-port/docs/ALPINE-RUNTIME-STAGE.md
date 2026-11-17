# Optional offline Alpine runtime stage

The Linux userspace setup now has one repeatable stage: unpack the signed
Alpine base into a new RAM directory, install the exact seven verified
diagnostic packages without repository access, expose read-only proc/sysfs,
and verify a traced child. It returns to the existing outer runtime. It never
replaces PID 1, changes Wi-Fi, starts a service, loads a driver or writes a
partition.

Cold installation passed in an isolated exact-stock-kernel VM. Verification
and repeated reuse passed on Lynx's existing Alpine environment, preserving
the same boot, original PID 1 and all three watcher PIDs. A fresh installation
through this combined stage has not yet run on the phone. The original native
base and package installation proofs remain separate hardware evidence.

## Prepare and test offline

From `/noobia/lynx`:

```sh
python3 tools/prepare_alpine_runtime_stage.py \
  --rootfs-receipt ROOTFS_RECEIPT \
  --package-receipt OFFLINE_PACKAGE_RECEIPT --test-vm
```

Use the signed rootfs receipt and filtered package export documented in
[ALPINE-USERSPACE.md](ALPINE-USERSPACE.md). Preparation creates a new private
artifact directory and does not contact the phone. It reads the base through
the strict in-memory archive verifier and validates all seven package hashes
against the successful offline APK VM. The package bundle accepts only the
exact regular-file members; unexpected paths, duplicates and wrong hashes
are rejected. APK still verifies its package signatures when installing.

The staged inputs contain the base archive, filtered APK archive, actual
stage and observability scripts, exact package specifications, checksums of
the base BusyBox/musl loader/APK executable, and a checksum list of the inputs.
All binary inputs remain private. The rootfs and APK archives are unchanged;
there is no remote package resolution during startup.

The optional VM test uses unchanged V19 static BusyBox as outer PID 1,
128 MiB tmpfs `/run`, no NIC or attached disk, and the exact stock kernel.
It executes the actual stage source, cold-installs, verifies, rejects an
existing rootfs, wrong boot identity, symlink input directory and tampered
input, and checks that outer PID 1 and a pre-existing fixture process survive.
This fixture process is not a thermal protection test. The VM then reads
live proc data through the chroot and powers off.

Expanded test: 11 checks passed in about nine seconds. Console output is saved
as it arrives, including partial output on timeout. Failed VM stages exit to
a VM-only poweroff trap; that trap is not part of the phone stage. The first
test had already passed installation and verification, but its final probe
used `free` outside the deliberately minimal PATH and killed VM init. That
failure is retained; the corrected probe explicitly invokes Alpine BusyBox.

## Verify an existing phone environment

```sh
python3 tools/configure_alpine_runtime.py --session SESSION_RECEIPT \
  --stage-receipt STAGE_VM_RECEIPT --verify-existing
```

With no action flag, the tool only prints usage and makes no contact. An
action requires a successful stage VM receipt, matching console hash/kernel,
and current source/input bytes identical to those exercised in that VM.
The wrapper obtains fresh pinned native SSH proof and verifies the power
runtime before and after. It pins the boot ID, requires fresh valid battery
data, battery below 35°C and at least 20% charge, and charger offline.

The first run uploads the input files into a new private directory under
`/run/lynx/alpine-stage-*`, after a RAM-space check. Upload bytes are hashed
before extraction. Subsequent runs reuse that directory only if its manifest
and every listed file match exactly. Partial or incompatible state is refused,
never overwritten or cleared. The upload archive and partial failed work are
retained locally and in RAM for review; this uses additional tmpfs space.

`--verify-existing` does not install packages or create mounts. It verifies
base executable hashes and exact diagnostic package versions, requires the
read-only proc/sysfs mounts already present, and writes a short trace in the
chroot's `/tmp`. It can create the input staging directory on its first run.
It is not a wholly read-only operation. Original outer proc/sysfs mount entries,
PID 1 executable, boot ID and watcher PID inventory must remain unchanged.

The first wrapper attempt failed before contact because it passed a relative
session path to a child running from another directory; paths now resolve
before child launch. A second attempt reached read-only preflight and stopped
on a missing host import before upload. Both failures are saved. The corrected
run and subsequent input reuse passed without installing or restarting
anything on the phone.

## Install after an otherwise-needed V19 boot

```sh
python3 tools/resume_battery_session.py --start --usb-unplugged-confirmed --runtime-power \
  --alpine-stage-receipt STAGE_VM_RECEIPT
```

This remains a host-assisted procedure, not an image change. Offline stage
validation happens before the listener starts. The existing workflow then
discovers native SSH, confirms the battery gauge, installs its monitor and
watcher, and establishes runtime power protections. It starts the host logger
before the optional Alpine work, explicitly synchronizes Linux wall time from
Nexus without writing RTC, then calls the stage with `--install`. Without the
new argument, the prior resume behavior remains available.

Wait for the listener-ready receipt before any physical boot action. Do not
reboot the current useful session merely to exercise this path. The combined
hardware cold-start sequence remains untested; the prepared layers have
separate VM, fixture or hardware evidence with the limits described here.

`--install` refuses any existing or partial rootfs rather than repairing it.
It requires at least 32 MiB free in `/run` after staging, unpacks the verified
base, creates basic chroot device nodes, and performs the signed offline APK
transaction with a 30-second TERM timeout. The host stage command is also
bounded; a timeout retains partial state for inspection. No cleanup, shutdown
or reboot is triggered by stage failure. Earlier SSH, watchers and host logger
remain running; failure is recorded in the resume receipt.

`test_alpine_resume_sequence.py --stage-receipt STAGE_VM_RECEIPT` uses fixture
subprocess replies to test ordering and failure handling without contacting
the phone. Thirteen checks passed for default behavior, successful Alpine
setup, clock failure, Alpine failure, logger receipt retention, and flag
propagation to the detached worker. These do not validate actual gauge
discovery, driver startup or host logger operation.

## Evidence and remaining boundary

- Initial failed VM: `linux-port/artifacts/alpine-runtime-stage-1792181938707011626`.
- Cold-stage VM: `linux-port/artifacts/alpine-runtime-stage-1792182067017586771`.
- Expanded refusal checks: `linux-port/artifacts/alpine-runtime-stage-1792182224695177330`.
- Host input rejection checks: `linux-port/artifacts/alpine-stage-input-check-1792182105649581952`.
- Failed host attempts: `logs/alpine-runtime-verify-1792182105396077127` and
  `logs/alpine-runtime-verify-1792182118685111977`.
- Successful phone verification: `logs/alpine-runtime-verify-1792182146999702470`.
- Verified input reuse: `logs/alpine-runtime-verify-1792182198922562268`.
- Resume fixture: `linux-port/artifacts/alpine-resume-sequence-1792182261633323623`.
- Phone postcheck: `logs/live-alpine-stage-final-health-1792182291044366468`.

The final phone check showed the same boot and watcher PIDs, battery 22.2°C,
80% charge, no battery field errors, and about 33 MiB free in `/run`.
This is a point-in-time observation, not a complete thermal safety claim.
V19, stock restoration, recovery foundations and slot B remain unchanged.
The Linux flash hold is still active. Persistent rootfs placement and a
replacement handset PID 1 remain later work.
