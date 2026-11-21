# Lynx Low-Power Island SCP / LPM Preflight Gate

Strict read-only preflight and resource voter evaluator for the System Companion Processor (SCP) and Low-Power Module (LPM / SPM) on the OnePlus Nord 3 (Dimensity 9000, MT6983).

## Hardware Components
- **System Companion Processor (SCP):** Dual-core RISC-V coprocessor @ 0x1c700000 (`&scp`), 2 MiB TCM SRAM @ 0x1c400000, 5 hardware mailboxes (`mbox0`..`mbox4`).
- **Low-Power Module (mtk_lpm):** MediaTek SPM low-power management controller (`&mtk_lpm`).
- **Resource Voters:**
  - `bus26m` (id 0): 26MHz root crystal oscillator
  - `infra` (id 1): Infracfg peripheral interconnect bus
  - `syspll` (id 2): Main System PLL
  - `dram_s0` (id 3): LP-DDR5 Channel S0 self-refresh power state
  - `dram_s1` (id 4): LP-DDR5 Channel S1 self-refresh power state
- **Power States Tracked:** `mcusysoff`, `system_mem`, `system_pll`, `system_bus`.

## Safety Boundaries
- **Strictly Offline by Default:** Use `--validate <FIXTURE>` to evaluate saved snapshots.
- **Double-Gated Live Mode:** Live queries require `--live --allow-live`.
- **Zero Sleep Actuation:** Never commands system suspend, never forces SCP core reset or halt, zero module load/unloads.

## Usage
```bash
# Validate offline snapshot
python3 lynx_lpm_preflight.py --validate fixtures/lpm-baseline-active.json

# Validate with JSON output
python3 lynx_lpm_preflight.py --validate fixtures/lpm-deep-sleep.json --json

# Run unit tests
python3 -m unittest test_lynx_lpm_preflight.py
```
