# V31 RAM-only cooling startup retry

On the V19 rollback boot recorded at
`logs/local-health-ram-trial-1792430224336258363/result.json`, the pinned
SSH and unplugged fresh-boot checks passed. The health bootstrap loaded the
thermal and battery modules, but its cooling watcher did not become ready.
The retained stream shows CPU/SoC readings around 40.0–40.5°C during this
phase and a 26.9°C battery sample. The launcher's safe power-off request
timed out over SSH; the independent phone-side timer remained armed. The
phone then became unreachable. Physical power-off has not been confirmed.

`autonomous-health-start-v31.sh` preserves the reviewed module order,
preflight, battery checks, 180-second independent timer, and original
`thermal-cooling-watch.sh`. It changes only watcher startup: after the
existing passive-cooling check, it makes at most three launch attempts,
five seconds apart. It retries only when the watcher has exited and has
created **no** cooling state directory. A live worker without a ready marker
or any partial cooling state fails immediately. Failed attempts append to
the RAM log. This addresses the narrow interval in which temperature can
rise between the bootstrap's check and the watcher's own <40°C check; it
does not raise a thermal limit or weaken the guard.

The exact V31 source passed shell syntax and synthetic host/local startup
fixtures. Each fixture made the first watcher launch refuse cleanly, then
confirmed that the second launch became ready. A third fixture created
partial state and confirmed that V31 refused without retrying or marking
health ready. Receipts:

- `linux-port/artifacts/autonomous-health-start-check-1792430456291629151/result.json`
- `linux-port/artifacts/autonomous-health-start-check-1792430466420875201/result.json`
- `linux-port/artifacts/autonomous-health-start-check-1792430435474100271/result.json`

`tools/launch_local_health_ram_trial_v31.py --prepare` passed offline. It
keeps the original reviewed health-input archive and local handoff, uploads
the V31 start script to the same RAM destination expected by that handoff,
and verifies its hash before running. A fresh V19 boot, pinned SSH, USB
disconnection and fresh-boot safety checks are still required for `--run`.
V31 has **not** been run on Lynx. No phone partition or boot image contains
this change.
