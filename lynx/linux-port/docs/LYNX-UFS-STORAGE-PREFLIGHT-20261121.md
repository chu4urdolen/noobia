# UFS 3.1 Host Controller & Storage Subsystem Preflight Gate

**Subsystem:** Universal Flash Storage (UFS 3.1) Host Controller & Storage Engine
**Platform:** OnePlus Nord 3 (`oplus6983_22823` / MediaTek Dimensity 9000 MT6983)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/ufs/`

---

## 1. Hardware Architecture & Device Tree Mapping

The OnePlus Nord 3 features high-performance UFS 3.1 solid-state storage governed by the MediaTek MT6983 UFSHCI controller and JEDEC JESD220E specification.

### 1.1 Host Controller & Reset Management

From `stock-merged.dtb`:
- **UFSHCI Controller Node:** `ufshci@112b0000`
  - Base MMIO: `0x112b0000`, size `0x2300`
  - Compatible: `mediatek,mt8183-ufshci`
  - Interrupt: SPI 169 (`0xa9`)
- **AO / PDN Configuration & Syscon Resets:**
  - `ufs_ao_cfg@112b8000`: Provides `unipro_rst` via `ti,syscon-reset`
  - `ufs_pdn_cfg@112bc000`: Provides `crypto_rst` (bit 0) and `hci_rst` (bit 1)
- **Power Domain:**
  - `disable-unused-pd-ufs0_shutdown` (MediaTek scpsys power domain)

### 1.2 Clocking & Power Rails

- **Required Clocks:**
  1. `ufs_hd_haxi`: High-speed AXI interconnect bus clock
  2. `ufs_fde`: Flash Data Engine cryptographic core clock
  3. `ufs`: Main controller core clock
  4. `ufs_mbist`: Memory Built-in Self Test clock
  5. `ufs_hf_fmem`: High-frequency memory PHY clock
- **Voltage Regulators:**
  - `mt6363_vufs18`: 1.8V analog rail (regulator `VUFS18` on MT6363 PMIC @ 4)
  - `mt6363_vufs12`: 1.2V core digital rail (regulator `VUFS12` on MT6363 PMIC @ 4)

### 1.3 High-Speed Physical Layer (UFS PHY)

The UFS interconnect utilizes dedicated multi-block PHY submodules mapped at `0x11fa0000`:
- Digital Global: `peri_ufs_glb_dig@11fa0000`
- Analog Global: `peri_ufs_glb_ana@11fa1000`
- MIB: `peri_ufs_glb_mib@11fa2000`
- PLL: `peri_ufs_glb_pll@11fa3000`
- CDR (Clock & Data Recovery): `peri_ufs_glb_cdr@11fa4000`
- TX Digital/Analog: `peri_ufs_ln_dig_tx@11fa8000`, `peri_ufs_ln_ana_tx@11fa9000`
- RX Digital/Analog: `peri_ufs_ln_dig_rx@11faa000`, `peri_ufs_ln_ana_rx@11fab000`
- Link Protocol: M-PHY Gear 4 (HS-G4) Dual Lane, delivering up to 23.2 Gbps theoretical raw link throughput.

### 1.4 JEDEC JESD220E Health Descriptor & Telemetry

Storage longevity and wear leveling are tracked via standard UFS Health Descriptors:
- **Pre-EOL Information (`bPreEOLInfo`):**
  - `0x01`: Normal (consumed reserved blocks < 80%)
  - `0x02`: Warning (consumed reserved blocks 80% to 90%)
  - `0x03`: Urgent (consumed reserved blocks > 90%)
- **Device Life Time Estimation A (`bDeviceLifeTimeEstA`, User TLC Area):**
  - `0x01`: 0% – 10% device life time used
  - `0x02` .. `0x0A`: 10% increments up to 100%
  - `0x0B`: Exceeded maximum estimated lifespan
- **Device Life Time Estimation B (`bDeviceLifeTimeEstB`, Enhanced/SLC Area):**
  - Same 0x01..0x0B scale for SLC Write Booster and firmware partition endurance.

---

## 2. Preflight Gate Implementation

The `lynx_ufs_preflight.py` tool audits:
1. Device Tree bindings and clock/reset/power rail mapping.
2. High-speed PHY enumeration and Gear 4 link negotiation.
3. JEDEC health descriptor telemetry against wear thresholds.
4. Read-only sysfs inspection (`/sys/class/block/` and `/sys/devices/platform/soc/112b0000.ufshci/`).
5. Enforces safety invariant: Zero block-device writes, zero formatting, zero partition tampering.
