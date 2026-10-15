# Reviewed next step: sensor then stock CPU frequency driver

Hardware follow-up: this trial has now succeeded. See
[CPU-TRIAL-RESULT.md](CPU-TRIAL-RESULT.md) for verified policies, cooling
interfaces, raw-evidence checks, and remaining thermal limitations.

This is a short supervised RAM-only trial on the unchanged V19 boot image.
Order: pinned SSH, independent stop timer, proven calibration/LVTS sensor stage,
fresh CPU/SoC temperature guard, then stock OMRG and CPU-frequency modules.
No flashing, charging/gauge driver load, manual governor change, stress test,
thermal-limit write or automatic unload is included.

The CPU driver registers with the kernel cpufreq framework. Stock configuration
uses the built-in schedutil governor and enables CPU thermal cooling support.
Probe reads firmware frequency tables and maps the8CPUs into three hardware
domains containing4/3/1CPUs. It enables normal hardware DVFS and uses bounded
hardware-state polls (300ms per policy in the published reference). A successful
insertion alone does not prove that policies or cooling devices appeared.

OMRG is a required stock companion. The published CPU and thermal variants
have different default rule-enable behavior, so no default is assumed. Runtime
checks pin the stock DT rule and require upper-limit-only coupling: a new
`down_limit_enable` property causes refusal. No OMRG sysfs setting is changed.
The test captures actual rule state and frequency policies for offline review.

The pack verifies the CPU performance-domain phandles, domain counts, relevant
CPU node properties, provider registers, OMRG rule properties and stock ABI.
The CPU stage additionally requires one valid soc_max reading and at least two
valid CPU readings, all strictly above0and below50000millidegrees. This is a
conservative diagnostic cutoff, not a battery safety guarantee.

Pack: thermal-ssh-pack-1792101216718173026,2296156bytes/44modules.
SHA25643ef800701f518317780b6c8afe1623740be0f22799822f0e912ff2286aba5de.
Native stock-kernel ARM test1792101259998565584 passed six runtime refusal
cases and ten temperature cases (good, connectivity-only, hot SoC/hot CPU,
zero, negative, invalid, unreadable, duplicate SoC and insufficient CPU samples).
No kernel module was inserted in these VM checks.

`tools/lynx_cpu_trial.py` pins this pack and reuses the supervised coordinator.
It captures snapshots before/after, a second idle sample, cooling-device state,
kernel logs, OMRG rule state and existing I2C client names/bindings. Capturing
I2C metadata sends no raw I2C transfer and helps later battery-driver review.
After capture it requests power-off; the90second independent stop request
remains armed. A kernel hang can still defeat software shutdown, so Noob must
remain present for physical intervention if needed.

## Battery review finding

The stock DT marks the MT6375 gauge path `DISABLE_MTKBATTERY` and also exposes
an external `oplus,bq27541-battery` at address0x55, with a BQ28Z610 flag and
SOC calibration/smoothing settings. The external gauge probe in the published
OPLUS source calls hardware configuration and SOC-parameter routines, so it
cannot be treated as a temperature-only read. The full battery/charging bundle
remains excluded. Review the matching chip path before adding battery sensing;
do not probe arbitrary addresses or program gauge parameters for this test.

Pinned references saved locally under docs/power-management-sources-1792101036780548667:
OnePlus kernel commit81ec42ad5e803be0cba619f9f7bb298db7d33d7b and modules
commitb7485501b2c4e0abae154e44c3861bd0fc6d605a. Exact OEM binary provenance
is not independently established; actual trial modules remain unmodified stock.
