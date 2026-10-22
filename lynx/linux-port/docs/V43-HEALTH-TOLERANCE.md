# V43 three-sample health observation — offline candidate

Three checksum-verified V42 boots reached `HEALTH_READY`, then wrote
`HEALTH_FAIL_POSTCHECK` within one second. The parent requested power-off
after a single rejected supervisor `--once` sample. The already running
independent supervisor instead requires **three consecutive failures** before
requesting power-off. The specific failed inner condition is not yet known.

V43 derives from the exact V42 image. Only primary `/init` changes. In the
post-readiness observation window, a passing `--once` check resets the parent
failure counter; a rejected check increments it and logs the count. The parent
requests power-off and saves `HEALTH_FAIL_POSTCHECK` only after three
consecutive rejections, sampled five seconds apart. The independent supervisor,
thermal and battery watchers, charger guard, 420-second outer power-off timer,
and final power-off at uptime 300 remain. The stock kernel, command line,
health child, and entire supplementary payload remain byte-for-byte V42.
There is no Alpine handoff in this candidate.

Private image:
`artifacts/health-tolerance-v43-offline/nord3-health-tolerance-v43-untested.img`,
SHA-256 `4c088d2b4aca070510291322b9a809947100cecf0909bc458727914f5afbd875`.
The builder and independent validator receipts are beside it. Validation
checked the exact two-site `/init` delta, BusyBox syntax, unchanged supplement,
stock kernel, V33/V19 rollback hashes, and pinned AVB model in unlocked and
locked cases. The guarded trial `--prepare` passed. A one-second pinned
collector dry run against live V33 captured one sample and correctly rejected
it as V43: `logs/v43-health-window-1792667833465627951/result.json`.

**V43 has not been flashed or booted.** V33 Alpine was last verified running
unplugged. For a trial, start `tools/capture_v43_health_window.py` before the
guarded `tools/lynx_boot_a_v43_trial.py` flash of **only `boot_a`**, then
separately reboot and promptly unplug USB. The collector also captures the
last parent `--once` output when reachable. Restore exact V33 only to
`boot_a` afterward, verify Alpine, and read the checksummed stage record.
Preserve slot B, bootloader, recovery, and all other partitions.
