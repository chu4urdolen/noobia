# CPU cooling control verified without heating

The live read-only thermal survey found three `thermal-cpufreq-*` cooling
devices, with maximum states 23, 29 and 27. The CPU zones use `step_wise`, but
showed no trip points or cooling-device bindings. `soc_max` exposed only a
116.5°C critical trip. This does not establish an automatic passive throttling
policy. Our existing 60°C SoC/CPU watcher and 45°C battery watcher remain active.

The charger interface independently reported `online=0`, `status=Not charging`
with USB unplugged. The signed battery gauge current also indicated discharge.
No charger setting was written.

`cooling-control-trial.sh` performed a bounded test while SoC temperature was
below 45°C and both watchers were alive. It saved original cooling states,
armed an independent 30-second rollback and increased each state from zero to
one. No workload or temperature override was used.

| CPU policy | Original maximum | State-one maximum | Restored maximum |
| --- | --- | --- | --- |
| policy0 | 1.80 GHz | 1.70 GHz | 1.80 GHz |
| policy4 | 2.85 GHz | 2.75 GHz | 2.85 GHz |
| policy7 | 3.05 GHz | 3.00 GHz | 3.05 GHz |

Limits remained reduced through the ten-second observation and returned to
their exact originals afterward. SSH remained available. Battery readings
were 23.5°C and −58 to −60 mA; the recent SoC/CPU maximum was about 27.3°C.
The independent rollback subsequently completed too, confirmed in
`logs/live-cooling-rollback-verification-1792173548004003162`. Restoration skips a
device if another controller changed its state in the meantime.

This proves a direct cooling-state request changes the CPU policy limit. It
does not prove an automatic thermal trigger, performance under sustained
load, higher cooling states, or complete OEM thermal protection. The trial
leaves no permanent cooling cap and does not alter V19 or the temperature
watchers. The separate WFI fallback remains active for this RAM session.

Private evidence:

- `logs/live-thermal-policy-survey-1792173365809276850`: zones, frequency policies,
  charging status and cooling state inventory.
- `logs/live-cooling-control-trial-1792173442046650278`: before/limited/restored
  observations, verified native identity, raw streams and timestamps.

## Running soft-throttle policy

`thermal-cooling-watch.sh` now runs in RAM. It requests only the hardware-tested
state one at a valid SoC/CPU maximum of 45°C or higher, releasing its own limit
at 40°C or lower. Between those temperatures it retains the previous decision.
The limit is deliberately modest; it is not a replacement for the independent
60°C SoC/CPU and 45°C battery shutdown watchers.

The script requires both other watcher PIDs alive, at least one valid `soc_max`
and two CPU readings, a starting maximum below 40°C, and three initially
unthrottled CPU cooling devices. It refuses overlapping instances. An invalid
sensor set causes a logged hold, with no relaxation of an owned limit. It
does not override a stronger existing cooling state. If a device it owns
changes externally, it cedes that device for the rest of the run. These are
best-effort ownership checks, not an atomic arbitration protocol with other
controllers.

`test_thermal_cooling_policy.py` ran 33 actual shell decision cases covering
threshold boundaries, hysteresis, invalid readings, external stronger limits
and ownership loss. The identical hash-checked cases passed on Lynx's BusyBox
shell before startup. The cool-running daemon then reported readiness, fresh
readings and `desired=0`, leaving all three cooling states zero. We have not
heated Lynx to trigger an automatic hardware transition; direct actuation and
decision logic have been verified separately.

Source SHA256:
`5310290b6a8e981e2250910fb5b4b54428a1faa6b1f6177e36f5be2aade1233b`.

Additional private receipts:

- `artifacts/thermal-cooling-policy-check-1792173709322403443/result.json`:
  host cases and generated no-hardware-write native fixture script.
- `logs/live-native-thermal-cooling-decisions-1792173730554681342`:
  matching source hash and all 33 native cases passed.
- `logs/live-start-thermal-cooling-watch-1792173775271871468`:
  watcher ready, cool sensor reading, all cooling states unchanged.
- `logs/live-soft-throttle-steady-check-1792173851879619153`:
  ongoing watcher and independent watcher checks.

PID/ready/ownership files are under `/run/lynx/thermal-cooling-watch/`;
the log is `/run/lynx/thermal-cooling-watch.log`. A daemon exit leaves any
last owned soft limit in place. To remove it, first verify that the PID's
`/proc/PID/cmdline` is exactly the expected watcher, stop only that process,
wait for it to exit, then invoke:

```sh
sh /run/lynx/thermal-cooling-watch.sh --restore
```

Restoration refuses while the recorded PID is alive and releases only limits
still marked owned and still equal to state one. Reboot clears the RAM setup.
Neither this watcher nor the WFI fallback is baked into V19 or automatically
started by the existing battery resume worker yet. No elapsed-time shutdown
was added.

The updated bounded host collector also captures the soft-throttle log. The
new logger is `logs/battery-session-1792173826897633981`; the old logger was
stopped only after a hash-verified replacement sample, with exact owned PID
and command verification. Rotation receipt:
`logs/battery-logger-rotation-1792173851845332051.json`. This did not stop any
phone process. Logger expiry never powers off Lynx or stops her RAM watchers.
