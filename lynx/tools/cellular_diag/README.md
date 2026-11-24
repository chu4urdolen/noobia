# Lynx Cellular & 5G Diagnostics Toolkit

Autonomous cellular diagnostics and 5G radio intelligence for Lynx (OnePlus Nord 3 MT6983).

## Subcommands
- `sim-check`: Inspect dual-SIM tray hardware, platform hot-plug EINT device nodes, and card status.
- `modem-status`: Audit CCCI MD1 baseband core state (`/sys/kernel/ccci/boot`), 53 CCCI character nodes, and kernel module linkage.
- `5g-bands`: Report full 5G NR (Sub-6 GHz SA/NSA) and LTE carrier band capabilities of the MediaTek M80 modem.
- `ccmni-stats`: Inspect MediaTek Cross-Core Modem Network Interfaces (`ccmni0` through `ccmni20`, `ccmni-lan`).
- `cell-recon`: Scan for mobile network operators and cell telemetry via ModemManager/QMI.
- `at-probe`: Non-blocking, safe AT channel probe (`/dev/ttyC0`).

## Concurrency Protection & Background Execution
- Uses non-blocking file locks in `/run/lynx/locks/cellular_<action>.lock`.
- Prevents running two instances of the same diagnostic concurrently.
- Supports `--fork` for non-blocking execution, streaming findings into `noobia-sense` syslog.
