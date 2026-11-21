# D11 — Portable common health checks on Nexus itself (Solo Dushich, 2026-11-21)

Round-5 queue item **D11** (Gwyn, note #148): run the *portable* common
checks of `lynx/tools/health/portable_health.py` on **Nexus itself**, locally
and read-only, and document where that overlaps with Aigel's vitals board.
No edits to `aigel/` (read-only, cited below). No periodic job.

## What landed

| File | What | Status |
| --- | --- | --- |
| `lynx/tools/health/nexus_health_collect.py` | Local read-only collector: common facts (thermal, storage, network, services) + Nexus machine facts (GPU temp, Xid, ECC, RAM, SMART) into a `portable-health/1` snapshot; `--evaluate` reuses the shared pure evaluator and exits via `EXIT_BY_VERDICT` (ok 0 / warn 1 / fail 2 / unknown 3) | **OFFLINE TOOL, live-verified on Nexus** |
| `lynx/tools/health/test_nexus_health_collect.py` | 25 hermetic tests (injected readers, patched `_run`/`Path`; pass on a box with no GPU, no smartctl, no ollama) | **25 OK; health suite 139 OK** |
| `lynx/tools/health/examples/nexus-live-20261121.json` | Real live snapshot captured 2026-11-21T01:26Z | **live evidence** |

House guarantees (verified by test, not by trust):

- **read-only** — file reads plus bounded query commands only (`systemctl
  is-active`, `nvidia-smi` query, `journalctl -b`, `smartctl -H` with a single
  passwordless `sudo -n` retry, since `/dev/nvme*` is root-only). Nothing is
  written; no service touched; no RF.
- **bounded** — every subprocess has a per-command timeout (10 s; 15 s for
  journalctl/smartctl paths) and an 8 KiB output cap; at most 4 NVMe devices.
- **honest** — a reader that fails, times out, or finds no source leaves its
  fact **absent**; the evaluator then reports `unknown`, never `ok`. Tested:
  `test_reader_exception_leaves_fact_absent`,
  `test_all_readers_failing_gives_unknown_verdict_and_exit_3`,
  `test_services_timeout_is_absent`, `test_sudo_also_denied_is_absent`.

### Live snapshot, 2026-11-21 (evidence, not target)

`examples/nexus-live-20261121.json` + `--evaluate --text`:

```
nexus — verdict: warn
  unknown thermal            no thermal facts in snapshot   (no thermal_zone* on this box)
  ok      storage            {"free_mib": 1567249, "used_percent": 11.4}
  unknown network            no link_state in snapshot      (wired uplink; see v2 gap)
  ok      services           required [ollama, gpu_monitor], both active
  warn    nexus_gpu          1 NVIDIA Xid event(s)          (genuine journal evidence)
  ok      nexus_ram          {"available_pct": ~67-73}
  ok      nexus_smart        {"checked": 1, "failed_devices": []}
```

`xid_count: 1` is a real `NVRM: Xid` line in this boot's journal — the
collector surfaces it, it does not invent it.

## Overlap with Aigel's board

Aigel's verdict engine: [`aigel/tools/aigel_vitals.py`](/noobia/aigel/tools/aigel_vitals.py),
`derive_verdict()` (line 499). Portable checks: `portable_health.py` (same
dir). Both are [VERIFIED from source] today; the portable collector itself is
[D11, this commit].

### Where the two boards AGREE (same thresholds, same machine)

| Check | Aigel (`aigel_vitals.py`) | Portable (`portable_health.py`) | Agreement |
| --- | --- | --- | --- |
| RAM available | fail < 2 %, warn < 10 % (L517-521) | fail < 2 %, warn < 10 % (`nexus_ram`, L339) | **identical** |
| GPU temperature | fail ≥ 95 °C, warn ≥ 85 °C (L547-551) | fail ≥ 95 °C, warn ≥ 85 °C (`nexus_gpu`, L300) | **identical** |
| Xid events | > 0 in boot journal → warn (L566-567) | > 0 → at-least-warn (`nexus_gpu`) | **identical** |
| ECC uncorrectable | > 0 → fail (L571-575) | > 0 → fail (`nexus_gpu`) | **identical** |
| SMART overall-health | FAILED on any disk → fail (L582-584) | any `failed_devices` → fail (`nexus_smart`, L348) | **identical** |
| ECC absence honesty | RTX 5090 reports `N/A` → counter absent, no verdict (L319-347) | `N/A`/`0` → fact absent (read_ecc_uncorrectable) | **identical convention** |

### Where they DIFFER (recorded, not hidden)

| Check | Aigel | Portable | Note |
| --- | --- | --- | --- |
| **Disk space warn band** | warn ≥ 90 % used, fail ≥ 95 % (L530-534) | warn ≥ 85 % **or free < 512 MiB**, fail ≥ 95 % **or free < 128 MiB** (`check_storage`, L150) | Portable warns 5 points earlier and also judges free-MiB and `fs_errors` (fail > 0). e.g. a 92 %-used rootfs: **Aigel ok, portable warn** — a real disagreement [VERIFIED] |
| SMART depth | also fails on reallocated / pending sectors and media & data-integrity errors (L586-590) | overall-health only | Portable is *shallower*; Aigel is the stricter board |
| ECC correctable | > 0 → warn (L576-578) | not modelled | Aigel stricter |

### Aigel-only checks (no portable equivalent — by design)

- Lighthouse beacon: `nexus_ready=false` → fail (L512-513)
- CPU load1 per core: warn ≥ 2, fail ≥ 4 (L522-527)
- Noobia Wi-Fi interface DOWN → fail (L539)
- DNS 8.8.8.8 RTT: warn > 150 ms, fail > 400 ms (L540-543)
- GPU power limit vs policy → warn (L559-564)
- ≥ 10 error-level journal lines in window → warn (L554-555)
- "no sample readable" per store → warn (L596)

### Portable-only facts (Nexus context)

- **Services** required-set check (`check_services`, L228): `ollama`,
  `gpu_monitor` declared required; missing/failed → fail; empty required
  list → unknown, not ok.
- **Network** link model (wifi/usb) — on Nexus this is the wired uplink,
  which portable-health/1 cannot express, so the check is `unknown` **by
  design** (documented v2 candidate: an `eth` link state).
- **Thermal zones** — Nexus has no `thermal_zone*`, so the common thermal
  check is unknown; GPU temperature lives in the machine section (Aigel
  agrees: GPU temp, not board temp, is the meaningful number here).

## Deliberate scope limits

- No edits anywhere under `aigel/`; all Aigel claims above cite line numbers
  verified from source today.
- No cron/systemd/timer; the collector is a tool, invoked on demand.
- `journalctl` uses `sudo -n` only when plain access fails; a denied sudo
  costs one bounded call and leaves the fact absent (tested).
- `--max-age` staleness flagging reuses `portable_health.evaluate(max_age_seconds=...)`.

## How to use

```sh
# raw snapshot (JSON, portable-health/1)
python3 lynx/tools/health/nexus_health_collect.py

# evaluated board + exit code (ok 0 / warn 1 / fail 2 / unknown 3)
python3 lynx/tools/health/nexus_health_collect.py --evaluate --text

# tests (hermetic)
python3 -m unittest discover -s lynx/tools/health -p 'test_*.py'   # 139 OK
```
