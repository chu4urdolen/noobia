# Nexus unexpected resets, 2026-11-06

## Evidence

- Boot `77aa8982…` ended at 15:00:55 EET; next boot began at 15:01:31.
- Boot `66411bee…` ended at 15:19:19 EET; next boot began at 15:19:51.
- Neither boot logged a clean shutdown, kernel panic, OOM, NVIDIA Xid, or
  thermal critical event. `/sys/fs/pstore` and `/var/crash` contained no crash
  dump. This is consistent with abrupt power loss or a hardware reset, but
  does not identify the cause.
- Ollama's last log in the first affected boot was at 14:33:51, about 27
  minutes before that reset. The second reset occurred during a Dushich/Ollama
  session. GPU inference is therefore not a sufficient explanation for both.
- Nexus has an RTX 5090 with a 575 W configured limit. Noob reports a native
  GPU power cable and a be quiet! Dark Power 14 1200 W PSU. This exceeds
  NVIDIA's 1000 W reference system recommendation, but says nothing about the
  outlet, power strip, physical connection, or a component fault.
- Two unrelated user services had restart storms: `noobia-council.service`
  had no executable; `noobia-transcription-worker.service` used a Python 3.12
  virtual environment through a Python 3.14 interpreter, so NumPy could not
  import. Both were stopped and disabled on 2026-11-06. Their failures do not
  establish a cause for a full machine reset.

## Ongoing measurement

`nexus-reset-monitor.service` is enabled as a user service and writes a sample
every five seconds to `aria/logs/nexus-reset-monitor.jsonl`, flushing each
record. It records boot ID, uptime, CPU/APU/NVMe temperatures, GPU temperature,
power draw and utilization, and available RAM. Inspect the last records of a
boot if another reset occurs. The monitor cannot measure wall power or PSU
rail voltage, and a five-second sample can miss a brief transient.

At 16:01 EET Nexus performed a clean systemd poweroff; it booted again at
18:25. This later stop is not an unexplained reset. The monitor's final sample
before poweroff showed CPU 30.6 °C and GPU 31 °C at 4.5 W. During a subsequent
small Dushich task on the new boot, GPU draw reached 386.75 W and 39 °C with no
reset. This short stable run does not exclude intermittent power faults.

## Next discrimination

1. Keep Council and transcription worker disabled until separately repaired.
2. After a clean shutdown, test a different known-good wall outlet without the
   current strip or extension. Check whether other devices on the circuit also
   lose power. Do not move live power connections.
3. If resets recur on another outlet, inspect the GPU and PSU connectors with
   power disconnected; then compare behavior at a conservative GPU power limit
   during an attended, logged test. Do not treat a successful short test as
   proof of long-term stability.

Official specifications: [NVIDIA RTX 5090](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/),
[Dark Power 14 1200 W](https://www.bequiet.com/en/powersupply/5996).

## Later resets and measured GPU draw

The monitor started after the 15:00 and 15:19 abrupt resets, so there is no
GPU power measurement immediately before either one. Ollama's last logged
activity was about 27 minutes before the 15:00 reset; the 15:19 reset happened
during an Ollama/Dushich session.

On the new outlet, boot `73ba8a20…` ended abruptly around 18:48:48. Its last
two monitor samples were 388.29 and 389.27 W, with Ollama inference in progress.
After the next boot, Nexus powered off cleanly at 18:56:15 while the GPU was
idle at about 5.7 W. This is not an unexplained reset.

Boot `3a7483f0…` then ended abruptly around 19:00:45 during Ollama inference.
GPU draw reached 437.94 W at 19:00:19; Nexus survived at least another 26
seconds. Subsequent samples were 386.61, 390.95, 389.23, 393.94, and finally
355.77 W. GPU temperature peaked at 51 °C before the last sample, and CPU
temperature was 52.6 °C at the last sample. A separate short Dushich run
reached 386.75 W and completed without a reset.

Thus 390 W is not a demonstrated trip point. The two measured abrupt resets
coincide with sustained high GPU load, but one survived a higher measured draw
and one earlier reset lacked active Ollama logs. A five-second sample also
cannot reveal subsecond power spikes or voltage drops. The cause remains open:
power delivery, a component fault, or a hard system/GPU failure are plausible.
Ollama was disabled and stopped after the 19:00 reset pending investigation.

## OCK trial, 19:22–19:26 EET

Noob enabled the PSU's OCK control and restarted Ollama. Three bounded Dushich
coding runs then completed without a Nexus reset. The first reached a measured
438.94 W; later samples included 390.78, 396.36, and 396.90 W. The first
handoff failed because Dushich tried to launch the bridge from inside his task;
the second completed and committed a sparse-file helper; the third passed six
tests but failed its commit requirement. Aria reviewed and corrected the third
handoff's byte counter and test coverage, then committed the two files in
Dushich's isolated workspace as `598829c`.

This is evidence that short inference bursts above 390 W now work, but it does
not establish that OCK fixed the abrupt resets or identify the original fault.
The monitor remains active. No full Lynx storage backup was started in this
trial.

## Reset after OCK, 19:30 EET

During the next Dushich task, Nexus abruptly reset again. The 19:29:51–19:30:16
samples showed Ollama GPU draw of 419.00, 398.05, 324.27, 297.14, 345.31,
and 405.29 W. GPU temperature reached 56 °C and CPU 53.25 °C in the final
sample. The task produced no event log or report; its only file was empty and
was removed. OCK therefore did not prevent this failure under sustained local
inference. The authenticated inference proxy and Ollama were disabled and
stopped after the reboot; the reset monitor stayed active. Lynx was reachable
through SSH, and no full storage backup had started.

## Tests after hardware rearrangement, 20:18–20:40 EET

After Noob moved hardware/power connections, Nexus completed two bounded
Dushich coding runs without a reset. The monitor saw a 494.13 W GPU peak on
this boot. A 180.8-second local Ollama run then completed 29 requests and
59,392 generated tokens; its one-second log recorded 416.6 W mean draw,
441.17 W peak, and a 68 °C maximum GPU temperature. A second 305-second run
completed 49 requests and 100,352 generated tokens, with 423.4 W mean draw,
441.83 W peak, and 68 °C maximum GPU temperature. The second run had 300 of
306 one-second samples at or above 400 W. Neither run reset Nexus, and no
NVIDIA Xid or thermal-critical kernel message was found during them. Receipts
are in `aria/logs/nexus-load-20261106-2027/` and
`aria/logs/nexus-load-20261106-2037/`.

This is stronger evidence of stability under sustained GPU inference after
the hardware rearrangement, but it does not prove which connection or
component caused the earlier abrupt resets. OCK alone had already failed to
prevent the 19:30 reset. A Dushich draft miscopied the same power figures
into multiple boots; the corrected per-boot review is in his isolated
workspace at `projects/nexus_probe/RESET-ANALYSIS-20261106.md`, commit
`a7ea6bd` by Aria after review.

An additional bounded test at 20:42–20:44 ran four CPU hash workers alongside
local Ollama inference for about two minutes. It completed 19 requests and
38,912 generated tokens without a reset. The one-second GPU log recorded
399.1 W mean, 425.35 W peak, 67 °C maximum GPU temperature, and 77 of 120
samples at or above 400 W. The five-second system monitor recorded a maximum
CPU temperature of 71.875 °C during this interval. No test workers remained
afterward. Receipt: `aria/logs/nexus-load-20261106-cpu4-gpu/`.

All three attended load runs on this boot finished successfully, totaling
about ten minutes of inference. This increases confidence in the changed
physical setup but cannot prove long-term stability or identify the failed
component. Ollama remains manually active but disabled for automatic start;
the LAN inference proxy remains stopped and disabled. The reset monitor is
active.

## 2026-11-08 Dushich retry and GPU limit

Nexus reset abruptly while an offline Lynx audit task had begun and Ollama was
loading `gpt-oss:20b`. The previous journal ended without a clean shutdown.
The last visible Ollama activity alone does not establish the reset cause.
After reboot, Aria set the RTX 5090 power limit to 400 W, the lowest limit
accepted by this GPU (`nvidia-smi` rejected 300 W). The identical bounded
Dushich task then completed with four passing tests and no reset. A later
Lynx agent request through the Nexus inference proxy, including a nested
Codex CLI call, also completed without a reset. These runs support keeping
the 400 W cap as a trial setting but do not prove it prevented the earlier
failure. The cap is runtime-only and will need reapplication after a Nexus
reboot. Ollama is now enabled at boot at Noob's request; the authenticated
LAN proxy was started manually for the Lynx trial and remains disabled at
boot.

The 400 W cap was then made a startup dependency for `ollama.service` via
`noobia-gpu-power-limit.service` (source under `aria/inference/`). The service
ran successfully and is enabled. The authenticated inference proxy was also
enabled after the successful Lynx Codex trial. The dependency order and live
400 W reading were verified; behavior across the next reboot remains untested.

## 2026-11-09 attended 600 W Dushich load trial

At Noob's request, the startup power-limit script was changed from 400 W to
600 W and `noobia-gpu-power-limit.service` was restarted. `nvidia-smi` reported
600 W, the card's maximum, while Ollama and the inference proxy stayed active.
Dushich started a bounded offline Lynx camera audit task
`20261109T203151Z-eed8f3cd`. An initial live sample during that task reported
548.60 W GPU draw, 100% utilization, and 43 °C. The five-second
`nexus-reset-monitor` log remains the durable record. The first Dushich camera
audit failed its independent tests and was not adopted. A second bounded
reset-monitor analyzer task passed three tests and committed in Dushich's
isolated workspace (`216d1422ca73`). Nexus stayed up during both tasks. The
five-second monitor sampled at most 527.71 W in the first task while an
independent `nvidia-smi` sample read 548.60 W. Neither run establishes the
cause of earlier resets or long-term stability at 600 W.
