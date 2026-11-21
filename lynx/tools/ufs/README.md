# UFS 3.1 Host Controller & Storage Subsystem Preflight Gate

Audits Device Tree bindings, high-speed M-PHY Gear 4 link status, and JEDEC JESD220E health descriptor telemetry for the OnePlus Nord 3 (`oplus6983_22823`).

## Hardware Mapping

- **UFSHCI Controller:** `ufshci@112b0000` (`compatible = "mediatek,mt8183-ufshci"`, IRQ 169)
- **PHY Submodules:** `peri_ufs_glb_*` & `peri_ufs_ln_*` @ `0x11fa0000`
- **Power Rails:** `mt6363_vufs18` (1.8V), `mt6363_vufs12` (1.2V)
- **Clocks:** `ufs_hd_haxi`, `ufs_fde`, `ufs`, `ufs_mbist`, `ufs_hf_fmem`
- **Resets:** `unipro_rst` (AO), `crypto_rst` (PDN), `hci_rst` (PDN)

## Health Telemetry

- `bPreEOLInfo`: 0x01 Normal, 0x02 Warning (80% consumed), 0x03 Urgent
- `bDeviceLifeTimeEstA`: 0x01 (0-10%) to 0x0B (exceeded) for TLC storage
- `bDeviceLifeTimeEstB`: 0x01 to 0x0B for SLC write booster / firmware

## Usage

```bash
# Validate offline fixture
python3 lynx_ufs_preflight.py --validate fixtures/ufs-preflight-healthy.json

# Read-only live interrogation (requires double gate)
python3 lynx_ufs_preflight.py --live --allow-live
```
