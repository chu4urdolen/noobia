# Native CPU frequency and cooling interfaces verified

The supervised RAM-only trial verified three CPU frequency policies over pinned
native SSH on the unchanged V19 image. Sensor initialization returned first;
the temperature guard passed before loading stock OMRG and CPU-frequency modules.
All four new module insertions returned successfully: `nvmem_mtk_devinfo`,
`soc_temp_lvts`, `oplus_omrg`, and `mediatek_cpufreq_hw`.

| Policy | CPUs | Governor | Observed kHz | Range kHz |
| --- | --- | --- | --- | --- |
| policy0 | 0–3 | schedutil | 500000 | 500000–1800000 |
| policy4 | 4–6 | schedutil | 400000 | 400000–2850000 |
| policy7 | 7 | schedutil | 3050000 | 1300000–3050000 |

Three `thermal-cpufreq-*` cooling devices appeared, with maximum cooling states
23, 29, and 27. Their observed states were zero. This proves registration, not
active throttling response. The largest core was at its maximum during the
snapshot; no claim of lower power consumption or solved overheating is made.
The second SoC sample was 38.574°C. Battery temperature remains unavailable.
The captured OMRG rule was disabled; the trial did not change that setting.

The independent 90-second shutdown request was armed before acknowledging the
boot token. Capture finished and explicit power-off was requested about 6.3
seconds after first contact. The SSH power-off command timed out after five
seconds, so physical power-off remains unconfirmed. A software timer cannot
guarantee shutdown if the kernel hangs.

No partitions were written. No battery/charging modules, manual governor
changes, thermal-limit writes, or stress tests were included. The global flash
hold remains active. RAM-only additions must be loaded again on another boot.

## Evidence and repetition

Private receipt: `logs/cpu-trial-1792101714003328176/result.json`. Raw capture
streams retain timestamps, lengths, and SHA256 hashes, including vendor bytes
that are not valid UTF-8. `tools/summarize_cpu_trial.py` verifies those hashes,
native identity, operation order, module returns, policies, bindings, cooling
interfaces, and unchanged baseline image. Its sanitized output is
[CPU-HARDWARE-RESULT.json](CPU-HARDWARE-RESULT.json).

For a reviewed, supervised repeat with Lynx cool and USB unplugged:

```sh
python3 tools/lynx_cpu_trial.py --self-test
python3 tools/lynx_cpu_trial.py --listen --usb-unplugged-confirmed --seconds 300
```

Start the listener and verify its ready receipt before the physical power cue.
The coordinator discovers the DHCP address and proves native identity using the
pinned host key before uploading anything. Keep the private, hash-pinned pack
`thermal-ssh-pack-1792101216718173026`; do not substitute a rebuilt pack without
review and matching guard tests. See [CPU-TRIAL-REVIEW.md](CPU-TRIAL-REVIEW.md).

The previous listener disappeared before phone contact. Its receipt remains
`logs/cpu-trial-1792101460405082506/result.json`; a fresh listener handled the
successful trial without a second button sequence. A stale ready receipt alone
does not establish that a listener is still running.

The known-good V19 image, private checkpoint, and stock boot restoration
procedure remain unchanged. Do not interpret this result as permission for
unattended operation or an extended thermal test.
