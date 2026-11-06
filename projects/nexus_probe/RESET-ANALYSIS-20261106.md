# Nexus reset timeline, 2026-11-06

Times are Europe/Sofia (EET). Values come from the fsynced five-second monitor at `/noobia/aria/logs/nexus-reset-monitor.jsonl`. This table was regenerated from the actual boot IDs after review; an earlier Dushich draft copied one boot's figures into every row and must not be used.

| Event | Boot ID | Sample window | Peak GPU W | Last GPU W | Max GPU °C | Samples ≥380 W |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 18:48 abrupt reset | `73ba8a20` | 18:25:25–18:48:48 | 389.3 | 389.3 | 44 | 3 |
| 18:56 clean poweroff | `a0467619` | 18:49:14–18:56:08 | 92.5 | 5.7 | 37 | 0 |
| 19:00 abrupt reset | `3a7483f0` | 18:58:03–19:00:45 | 437.9 | 355.8 | 51 | 5 |
| 19:30 abrupt reset | `6e8e1179` | 19:20:28–19:30:16 | 438.9 | 405.3 | 56 | 8 |
| 20:26–20:29 successful load | `c4ca7082` | 20:11:05–20:34:20 | 494.1 | 9.4 | 68 | 51 |

The 18:48, 19:00 and 19:30 boots ended without a clean shutdown record. The 18:56 stop has systemd poweroff records. The earlier 15:00 and 15:19 resets preceded the monitor, so their immediate GPU draw is unknown. The 15:00 reset also had no Ollama activity logged for roughly 27 minutes.

The measured abrupt resets coincide with high local GPU load, but **390 W is not a fixed trip point**: the stable current boot reached 494 W during a Dushich task. A separate 180.8-second local Ollama run at 20:26–20:29 completed 29 requests and 59,392 generated tokens. Its one-second monitor recorded mean 416.6 W, peak 441.17 W, 166 of 180 samples at or above 400 W, and maximum GPU temperature 68 °C. No NVIDIA Xid, kernel panic or thermal-critical event was found for this current boot.

These observations do not establish whether moving hardware or power connections fixed the failure. Five-second samples can miss short power spikes and rail voltage drops. Power delivery, GPU/board faults and a hard system failure remain hypotheses; the log alone cannot choose among them. A longer attended run and inspection of physical power connections while powered off would add evidence.
