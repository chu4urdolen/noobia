# Hardware Watchdog (MTK-WDT) Preflight Gate

Audits Device Tree bindings, driver registration, and unattended reboot-mode recovery configurations for the MediaTek MT6983 hardware watchdog (`watchdog@1c007000`) on the OnePlus Nord 3 (`oplus6983_22823`).

## Hardware Facts

- **MMIO Node:** `watchdog@1c007000` (`compatible = "mediatek,mt6983-wdt"`, reg `0x1c007000 0x1000`)
- **Syscon Sub-node:** `reboot-mode` (`syscon-reboot-mode`, offset `0x24`)
- **Timeout Range:** 1..32 seconds

## Usage

```bash
# Validate offline fixture
python3 lynx_watchdog_preflight.py --validate fixtures/watchdog-preflight-ready.json

# Read-only live interrogation (requires double gate)
python3 lynx_watchdog_preflight.py --live --allow-live
```
