# Repeatable RAM power setup

The current Linux session has a verified WFI fallback and a running one-step
soft-throttle watcher. `configure_runtime_power.py` now packages the exact
hardware-tested scripts and can verify or adopt that setup without restarting
any existing process or overwriting saved original settings.

From `/noobia/lynx`, using the receipt for the currently discovered and verified
continuous session:

```sh
python3 tools/configure_runtime_power.py --session RECEIPT --verify-only
python3 tools/configure_runtime_power.py --session RECEIPT --apply
```

With no action flag, the tool prints instructions and makes no contact.
`--verify-only` reads the current state. `--apply` installs missing matching
scripts in RAM, applies WFI fallback if absent, and starts the soft-throttle
watcher if its state directory is absent. Existing complete state is verified
and retained. Existing incomplete state or mismatched source causes refusal;
the tool does not erase markers, overwrite originals, restart a dead watcher,
or silently adopt a different script.

Each run verifies pinned native SSH identity before and after configuration,
records and compares the kernel boot ID, validates the original battery/CPU
watcher PIDs against their command lines, and requires a recent error-free
battery snapshot. WFI verification checks eight CPUs, enabled WFI, disabled
deeper states and the saved original flag inventory. Source hashes are pinned
to the hardware-reviewed versions. Captures, payload bytes, hashes, timestamps
and failures are preserved under `logs/runtime-power-setup-*`.

The installer does not change Wi-Fi power-save mode; it records its current
value. That setting remains a separate reviewed operation. It performs no
flash, reboot, charging change, suspend request or unconditional shutdown.
If a later setup stage fails, existing useful services remain running and the
receipt identifies the failed stage; saved state is retained for diagnosis.

## Resume integration

For the next otherwise-needed boot of unchanged V19:

```sh
python3 tools/resume_battery_session.py --start --usb-unplugged-confirmed --runtime-power
```

Wait for the existing listener-ready receipt before any physical boot action.
The optional stage runs after battery monitoring and both temperature watchers
are established, and before starting the host logger. Without `--runtime-power`,
the previous resume behavior is retained. The worker propagates the option
through its detached launch and records the runtime setup receipt.

No reboot was performed to test this integration. Verification and repeated
application passed on the already-configured phone; a complete fresh-boot
execution of the new combined workflow remains untested. Separate hardware
trials already verified initial WFI application and soft-watcher startup.

An [optional offline Alpine stage](ALPINE-RUNTIME-STAGE.md) can now follow
power setup using `--alpine-stage-receipt STAGE_VM_RECEIPT`. It requires
`--runtime-power`, starts host logging before Alpine, and preserves the earlier
runtime if userspace setup fails. Its cold installation passed in a VM;
the complete fresh-boot hardware sequence remains untested.

## Validation

`test_runtime_power_setup.py` runs the actual generated shell against a private
synthetic filesystem. Eleven cases cover successful read-only verification,
idempotent application, mismatched source, stale/error battery data, absent or
partially restored WFI state, wrong/dead watcher process, missing readiness and
missing CPU inventory. Protected settings/originals remain unchanged in all
these cases. Embedded script bytes are checked against their pinned hashes.
This fixture does not simulate a fresh daemon installation or hardware.

The first fixture run failed because sequential path replacement corrupted
the mock `/proc/sys` path. Single-pass substitution corrected the fixture;
the failed receipt was retained. No installer was used on Lynx until corrected
cases passed.

Private evidence:

- `artifacts/runtime-power-setup-check-1792178126960507552`: initial fixture failure.
- `artifacts/runtime-power-setup-check-1792178354357084826`: eleven passing cases
  and embedded source hashes.
- `logs/runtime-power-setup-1792178227391006803`: live verification success.
- `logs/runtime-power-setup-1792178354915012108`: live repeat application success;
  original watcher PIDs 17580/18190/25373 retained.

The one-hour logger finished normally while development continued. Complete
RAM watcher history was recovered in
`logs/live-power-watch-history-1792178187548078626`, and a new four-hour bounded
logger started at `logs/battery-session-1792178187012953274`. Its ending does
not stop the phone or any RAM watcher. The recovered snapshot was 21.8°C,
83% charge and −62 mA signed gauge current, with no field errors.
