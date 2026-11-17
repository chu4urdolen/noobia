# V34/V35 failure boundary and next evidence capture

## 2026-10-21 V36 update

V36 added a 40-second pause after Wi-Fi readiness and omitted the Alpine
handoff. It booted twice and reached pinned BusyBox SSH. The first boot reached
`health-bootstrap/ready` around uptime 150.7 seconds, then contact ended before
the parent's completion marker. The second reached the cooling watcher and a
passing health sample around uptime 165.1 seconds, then contact ended before
the child-ready marker. Raw samples, hashes, timeline, and incident summary
are under `logs/v36-cooldown-window-1792598257537328145/`. The last captured
battery temperatures were 27.0–27.1°C; neither final sample contains a
power-off request, kernel panic, or thermal shutdown. The later pstore read
still showed an older UFS token and does not explain either loss. A 40-second
cooldown therefore did not solve the contact loss, but these captures do not
prove that health startup itself caused it.

The exact V33 image was restored to `boot_a`, then a fresh unplugged boot
reached pinned SSH, passed the V31 RAM health trial, and ran Alpine/OpenRC as
PID 1 on boot ID `0e5eaa29-d233-4e12-a7b7-508926575156`. The same boot's
read-only baseline is at
`logs/v33-healthy-readonly-compare-1792600131784454288/`. It remained
reachable after uptime 211 seconds with ext4 root mounted, SSH listening, and
the charger offline. This narrows the problem to an autonomous-path difference
or an intermittent hardware/network condition; it does not identify which.
The next trial should capture a final local marker across a reset or distinguish
Wi-Fi-only loss from power-off before changing the health or Alpine code.

After the V35 trial, working V33 (`1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f`) was restored to `boot_a` and Alpine/OpenRC PID 1 was verified on boot ID `51126311-72bc-41d8-8ac0-7b4f5d1457cd`. A newer V33 verification appears above. The V33 boot remains host-assisted. Do not describe V34 or V35 as successful autonomous Linux boots.

## What the V34 capture proves

`logs/v34-health-window-1792583593671638978/` contains two different boot IDs. Both boots reached pinned rescue SSH, completed the stock storage/Wi-Fi bootstrap, and started the local V31 health child. Both loaded the identified battery monitor. The first boot's last successful sample was at uptime **109.81 s**; the second's was at **103.05 s**. The first already had a running cooling watcher with a 37.2°C sample and desired cooling state 0. The second had reached a 38.79°C cooling sample with desired state 0. Neither series contains the health-ready marker, a child result, an OpenRC guard result, or an Alpine PID 1 proof. The next SSH attempts timed out.

The available samples bracket the loss of contact around cooling-watcher startup, but they do not prove which subsequent command ran or why contact ended. A reset, a deliberate safety power-off, and a Wi-Fi/network failure remain distinct possibilities. The old UFS trace in `pmsg-ramoops-0`, `console-ramoops-0`, and `expdb` carries token `69adf9d14707d848063b861b8f248748`; it cannot be assigned to either V34 boot. The V34 collector's old `readlink` invocation produced only BusyBox usage text, and its captured samples did not include kernel tails. Those gaps prevent a stronger diagnosis.

`tools/analyze_health_window.py` parses the preserved raw snapshots locally and refuses a sample whose recorded hash differs. Its V34 timeline is saved at `logs/v34-health-window-1792583593671638978/timeline.json`; it independently groups eight complete samples for the first boot and four for the second. The two failed SSH samples have no boot ID and are retained separately. The V35 timeline has zero samples. No phone connection is needed to reproduce either result.

The V31 child writes its detailed `LYNX_HEALTH_BOOT` messages to stdout and `/dev/kmsg`, but its `say()` function does not write them directly to `/dev/pmsg0`. The parent `log()` writes to pmsg. This is an instrumentation gap, not an explanation for the contact loss. The retained pstore record's age also means pmsg persistence on these resets is unproved.

## What V35 adds

V35 kept the V34 Wi-Fi and health path but skipped the Alpine handoff. Its trial collector captured **zero** pinned SSH samples over about 297 seconds, and Noob then observed Fastboot. It did not establish that V35 executed Linux userspace, so it cannot isolate the V34 failure to health or Alpine handoff. Its exact flash, reboot, collector, and restoration receipts are linked from `SESSION-STATE.md`.

## Prepared capture for a later controlled trial

`tools/capture_v34_health_window.py` now uses BusyBox-compatible `readlink -f`, captures PID 1 status, health timer/event logs, a process table and the last 120 kernel messages, and hashes each raw sample. `tools/capture_v35_health_window.py` imports the same capture. Both collectors accept a bounded `--interval` option (0.5–30 seconds) for a denser critical window. A read-only smoke run on the restored V33 Alpine boot succeeded with every section present; raw output and receipt are at `logs/collector-v33-readonly-smoke-1792586062632995585/`. A second three-second collector run with `--interval 0.5` captured V33 and verified its raw sample hash at `logs/v34-health-window-1792586184657951253/`. The collectors do not modify partitions.

Before another image trial, start its pinned collector first, verify the expected candidate init hash from a sample, and keep the exact V33 and V19 rollback images available. If the candidate again loses contact, capture the newest pstore and bounded expdb prefix after restoring V33; compare boot tokens and hashes before attributing a trace. Do not retry V34/V35 unchanged solely on the strength of the stale pstore record. Any new image needs offline validation and a separate guarded `boot_a` trial when physical help is available.
