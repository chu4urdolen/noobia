# Avoiding rejected CPU idle loops

The running stock kernel exposed deeper PSCI idle states but every successful
deep-state entry counter remained zero. Adding the `rejected` counters to our
capture revealed **12,943,805 failed entries in 30.42 seconds**, about 425,503
per second across eight CPUs. This is a failed-entry loop, rather than evidence
that the governor never selected those states.

The global CPU latency constraint read 2,000,000,000 microseconds, the kernel's
default, and no userspace process held `/dev/cpu_dma_latency` open. Per-CPU
`pm_qos_resume_latency_us=0` means no userspace constraint in this kernel's sysfs
interface; it does not mean an effective zero-latency requirement.

## Verified RAM fallback

`wfi-fallback-trial.sh` verified enabled WFI at state zero on every CPU, saved all
other states' original disable flags, armed a detached 45-second restoration,
then disabled only the deeper states for a 30-second trial. It never disabled
WFI, suspended the phone, changed frequencies, or touched partitions.

All three ten-second trial intervals had **zero rejected entries**. SSH and
the temperature watchers remained available. Gauge current snapshots changed
from −128 mA before the test to −102, −62 and −64 mA during it. Both the normal
exit and independent timed restoration completed; all original flags were
subsequently verified restored. Current returned to about −130 mA afterward.

We then applied `wfi-fallback.sh --apply` for the current RAM session. Another
30.41-second observation confirmed zero rejections. A longer trace
contained 23 distinct samples over 225 seconds: signed current −79 to −59 mA,
median −62 mA, battery temperature 24.0–24.9°C. The preceding power-save-on window
had 66 samples over 676 seconds, median −130.5 mA. These observations support
the fallback; unequal windows, polling and other diagnostic activity prevent
treating the difference as a controlled power or battery-life measurement.

The fallback is session-only and has no shutdown timer. Original flags remain
in `/run/lynx/wfi-fallback/original-flags`. Undo over pinned SSH:

```sh
tools/lynx-ssh 'sh /run/lynx/wfi-fallback.sh --restore'
```

Reboot also clears it. It is not baked into V19 or the automatic battery resume
worker. After a newly verified continuous session, use `lynx_live_command.py`
with that session's receipt, `--stdin-file linux-port/wfi-fallback.sh`, and
`--command 'cat > /run/lynx/wfi-fallback.sh && sh /run/lynx/wfi-fallback.sh --apply'`.
The helper preserves a fresh identity check, raw captures and timestamps.
The script refuses overlapping application and restores on a partial failure.

## Deeper sleep still needs investigation

The stock package contains exact-kernel `mtk-lpm.ko`,
`mtk-lpm-dbg-common-v1.ko` and `mtk-lpm-plat-v1.ko`. They were not loaded in the
captured running module list. Platform initialization in the published vendor
source initializes shared SRAM and power bookkeeping, installs CPU hotplug
callbacks, registers suspend handling, and calls
`lpm_smc_cpu_pm(VALIDATE_PWR_STATE_CTRL, MT_LPM_SMC_ACT_SET, PSCI_E_SUCCESS, 0)`.
Missing platform initialization is a plausible explanation for rejected PSCI
entries; the precise rejecting callback/firmware reason is not yet proven.

These modules are not read-only probes. The core and platform exit functions
are empty despite persistent callback registration in initialization, so
ordinary `rmmod` cannot be assumed to provide a complete undo. Review the
full dependency chain and secure-firmware prerequisites before a controlled
trial. Leave the validated WFI fallback available while doing that review.

The published source commit is
`81ec42ad5e803be0cba619f9f7bb298db7d33d7b`; stock binaries report
`g311738fbb5a8`. Source findings guide investigation but are not proof that
these two builds are identical.

## Saved evidence and tools

Private raw receipts under `logs/`:

- `live-idle-paired-observation-1792172753457126879`: failed-entry baseline.
- `live-wfi-fallback-trial-1792172856667668114`: bounded trial and normal undo.
- `live-wfi-rollback-check-1792172907224246832`: independent undo and original flags.
- `live-enable-wfi-fallback-1792172983731470335`: current session application.
- `live-wfi-session-observation-1792172984704283588`: follow-up zero-rejection interval.

`artifacts/idle-power-source-review-1792173148909952121` preserves ten source
excerpts, exact commit, file hashes and three stock module hashes/metadata.
No low-power module was inserted during this investigation.

`idle-observation.sh` gathers paired observations. Opening the latency misc
device briefly adds its default request; the read returns the aggregate value,
and closing removes that request. No constraint is written.
`summarize_idle_observation.py` verifies raw hashes and computes counter deltas.
Idle time is accounted on exit: entries spanning snapshot boundaries can make
short-window time ratios exceed one. Use rejection counts and longer intervals
instead of interpreting transition ratios as instantaneous CPU utilization.
`summarize_battery_window.py` verifies raw sample hashes and field errors,
deduplicates cached snapshots, and reports discrete sample distributions.
