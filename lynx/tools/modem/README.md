# Lynx Cellular Modem (CCCI) Preflight Tool

Read-only offline validator and safe telemetry probe for the MediaTek MT6983 cellular modem subsystem (MD1) on OnePlus Nord 3.

## Architectural Purpose
Enforces strict boundaries before any attended cellular trial:
1. Physical SIM card must be removed/unbound (`/sys/devices/platform/*SIM*` and `odm:oplus_sim_detect` driver absent).
2. Modem core must be in quiescent baseline state `md1:0` (`/sys/kernel/ccci/boot`).
3. Critical CCCI kernel interface character devices must exist (`/dev/ccci_ioctl0..4`, `/dev/ccci_md1_sta`, `/dev/ccci_fs`, `/dev/ccci_rpc`, `/dev/ttyC0`).
4. Stock modem firmware artifacts on Nexus must match exact cryptographic hashes (`md1img` SHA-256 `7cf648e7...`, `ccci_mdinit` SHA-256 `a288eb33...`).
5. Battery $\ge 50\%$ and thermal $\le 45^\circ\text{C}$.

## Usage
- Offline evaluation:
  `python3 lynx_modem_preflight.py`
- Validate fixture:
  `python3 lynx_modem_preflight.py --validate fixtures/modem-ready-status.json`
- Live read-only check (double-gated):
  `python3 lynx_modem_preflight.py --live --allow-live`
