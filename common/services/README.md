# Shared Linux services

Service entry scripts live here, one per service, with matching systemd unit
source files in [`units/`](units/). Each unit invokes the absolute script path
in this directory. Keep inhabitant-specific implementation in that inhabitant's
`/noobia/<Noob>/` directory when appropriate; the service entry script can call
it.

## Aigel health services (Nexus)

Five self-contained health services, each **exactly one script + one unit**,
all running on one shared sampling engine:

| Service        | Script            | Unit                      | What it samples                                            | Background store                          |
|----------------|-------------------|---------------------------|------------------------------------------------------------|-------------------------------------------|
| `cpu_report`   | `cpu_report.sh`   | `units/cpu_report.service`| per-core CPU usage (two snapshots 1 s apart) + top summary | `/var/log/noobia/aigel/cpu_report.log`    |
| `net_report`   | `net_report.sh`   | `units/net_report.service`| interface stats, active TCP, DNS latency (ping 8.8.8.8)    | `/var/log/noobia/aigel/net_report.log`    |
| `disk_report`  | `disk_report.sh`  | `units/disk_report.service`| usage of every real mount point                           | `/var/log/noobia/aigel/disk_report.log`   |
| `mem_report`   | `mem_report.sh`   | `units/mem_report.service`| RAM usage (and VRAM)                                       | `/var/log/noobia/aigel/mem_report.log`    |
| `gpu_monitor`  | `gpu_monitor.sh`  | `units/gpu_monitor.service`| sets GPU power limit (500 W default), then samples power, utilization, temp, VRAM | `/var/log/noobia_gpu/YYYY-MM-DD_HH.csv`   |

> `noobia_wifi_guard` (script + unit) is a separate, unrelated watchdog and is
> not part of these five.

## Unified sampling schedule

Every service samples on the same three-phase cadence and runs **until the
next service restart (boot)**, appending each sample to its background store:

1. **Hot** — sample every `--interval` (ms) for the first `--period` (s).
2. **Medium** — sample every **60 s** until 1 h after start.
3. **Hourly** — sample every **1 h** until the service restarts.

Defaults: `--interval 1000 ms`, `--period 300 s` (i.e. 1 s for 5 min).

**Cadence notes**
- The sampling interval is enforced on a **monotonic** clock (`/proc/uptime`), so NTP
  adjustments to the wall clock never corrupt the cadence. The stored timestamp is the
  **wall** time (`date -u`) of each sample, which is therefore the true time (and can
  occasionally look non‑monotonic if the wall clock was stepped by NTP).
- The effective gap between stored samples is `max(interval, sample_time)`: a sample
  only starts once the previous one finished. `cpu_report` takes two snapshots 1 s
  apart, so its hot‑phase cadence is ≈ 2 s; the others sample in well under a second.
- `net_report` bounds its 8.8.8.8 probe with `timeout 1` so an occasional slow/lost
  reply cannot stall the sampling loop; such a sample is reported as `unreachable`.

### Arguments and precedence

```
--interval <ms>   hot-phase sample interval (default 1000)
--period <s>      hot-phase duration        (default 300)
```

Precedence: **CLI arguments > policy file > built-in defaults.**

### Environment / test knobs

- `AIGEL_CONFIG` — policy file (default `/noobia/aigel/config.json`), JSON keys
  `sample_interval_ms`, `sample_period_s` and `power_limit_w` (read with `jq` when
  present).
- `AIGEL_LOG_DIR` — report store dir (default `/var/log/noobia/aigel`).
- `AIGEL_GPU_LOG_DIR` — GPU store dir (default `/var/log/noobia_gpu`).
- `AIGEL_GPU_POWER_LIMIT_W` — GPU power limit enforced by `gpu_monitor` at
  startup (default `500`; RTX 5090 allowed range 400–600 W, factory default
  575 W).  Precedence: this variable > `power_limit_w` in the policy file >
  `500`.  The setting does not survive reboots, so the service re-applies it
  on every start; it never aborts startup if the GPU/driver is unavailable.
- `AIGEL_MED_MS` / `AIGEL_HOUR_MS` / `AIGEL_HOURDUE_MS` — override the phase
  thresholds for testing (defaults `60000` / `3600000` / `3600000` ms).

Example hot-phase smoke test (run a report for a few seconds with a private
store and accelerated phases, then inspect the cadence):

```bash
AIGEL_LOG_DIR=$(mktemp -d) AIGEL_MED_MS=300 AIGEL_HOUR_MS=5000 AIGEL_HOURDUE_MS=700 \
  timeout 8 ./cpu_report.sh --interval 100 --period 2
```

## Running all five by hand

[`run_all.sh`](run_all.sh) starts every service script in the foreground with
the same `--interval`/`--period` arguments, optional `--real-time` name
prefixing and `--duration <s>` auto-stop — useful for smoke tests and
side-by-side inspection.  It is a manual tool, not a unit.

```bash
sudo -n ./run_all.sh --interval 500 --period 10 --duration 30
```

## Store format

- **Report services** append one single-line sample per event, ISO-8601
  timestamp prefixed: `2026-11-18T00:00:00.123Z <payload>`.
- **gpu_monitor** appends CSV rows to a per-hour file:
  `timestamp,power_w,util_pct,temp_c,vram_used_mb,power_limit_w,event`. On a
  clean boot after a graceful shutdown the current-hour file is dropped; on an
  unexpected (crash/power-loss) boot it is kept as an incident report. A D-Bus
  listener records a `SHUTDOWN` row on `PrepareForShutdown`.

## Installing

The units are `Type=simple`, `Restart=always`; the service keeps running until
stopped/restarted, and its `--interval`/`--period` come from the policy file
unless you add them to `ExecStart` (systemd does not expand `${VAR:-default}`
in `ExecStart`).

```bash
units/install_services.sh --dry-run          # inspect what would be installed
sudo -n units/install_services.sh            # copy units + daemon-reload
sudo -n systemctl enable --now cpu_report net_report disk_report mem_report gpu_monitor
sudo -n systemctl restart cpu_report net_report disk_report mem_report gpu_monitor
sudo -n systemctl status  cpu_report net_report disk_report mem_report gpu_monitor
```

`install_services.sh` copies the unit files and runs `systemctl daemon-reload`;
it does **not** enable, start, restart, or stop any service — do that explicitly
as above.
