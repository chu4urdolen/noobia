# Lynx Consolidated Hardware Preflight Matrix & Full Port Coverage Report

**Device:** OnePlus Nord 3 5G (`CPH2493` / SoC `MT6983` "Dimensity 9000" / board project `22823` "Vitamin")
**Author:** Solo Dushich (D24, Round 7 queue, Banshee)
**Date:** 2026-11-21
**Status:** Docs-only deliverable — consolidates every landed preflight gate (D17–D23, B18–B26) into one cross-referenced matrix.
**Safety model (all gates):** strictly read-only spec audit + optional hermetic/live collectors; double gate `--live --allow-live`; forbidden-token, AST-import, and read-only whitelist scans in every test suite.

---

## 1. Platform Identity (verified on disk)

| Fact | Value | Source |
|---|---|---|
| Model | OnePlus Nord 3 5G, CPH2493 | all Round 6/7 preflight docs, stock DT |
| SoC | MediaTek MT6983 (Dimensity 9000) | `mt6983.dts`, `oplus6983_22823.dts` |
| Board project | `22823` ("Vitamin") | `cust_mt6983_vitamin_*.dtsi` |
| CPU cluster | 1× Cortex-X2 (3.05 GHz) + 3× Cortex-A710 (2.85 GHz) + 4× Cortex-A510 (1.80 GHz) — *doc-level: 2 "bigbig" LVTS rows* | `LYNX-THERMAL-ZONES-VALIDATOR-20261121.md` (LVTS map) |
| Display | 1440 × 3216 AMOLED, 120 Hz | `LYNX-DISPLAY-PANEL-PREFLIGHT-20261121.md` |
| Battery | 2S dual-cell, 7.4 V nom / 8.7 V chg, 80 W SuperVOOC | `LYNX-CHARGER-SUPERVOOC-PREFLIGHT-20261121.md` |
| Sub-PMICs | MT6375 (`&i2c5` @ `0x34`), MT6373 (AUXADC), MT6338 (codec/accdet) | charger / headset / AFE docs |

> Core count caveat: the queue and LVTS map list `cpu_bigbig1/2` + `cpu_big1..6` + `cpu_little1..4`; the cluster split is quoted from the thermal-zones doc (LVTS index 6,8 = bigbig; 1–5,7 = big; 9–12 = little) and is not independently re-derived in D24.

## 2. Master Preflight Matrix

Every row cites the on-disk Device Tree evidence recorded in the source doc, the gate's tool path, and the exact unit-test count from the consolidated runner snapshot (2026-11-21).

| # | Subsystem | DT node(s) | I2C / MMIO / GPIO | Rails / power domains | Driver status | Gate tool (`lynx/tools/`) | Tests | Source doc |
|---|---|---|---|---|---|---|---|---|
| 1 | CPU / thermal zones | `&lvts` / thermal-zones; `soc_max` (116.5 °C crit, 2.0 hyst), `cpu_bigbig1/2`, `cpu_big1..6`, `cpu_little1..4`, `quiet_ntc` | LVTS channels 0–12; NTC via PMIC AUXADC | SoC core supply; board NTC | LVTS array verified in DT; vendor trip governor names unverified | `thermal_zones/lynx_thermal_zones_validator.py` (B22) | 10 | `LYNX-THERMAL-ZONES-VALIDATOR-20261121.md` |
| 2 | PMIC (MT6375/MT6373/MT6338) | `mt6375@34` on `&i2c5`; `mt6373_adc`; `mt6338_accdet` | i2c5 @ 0x34; AUXADC VIN1 (panel), VIN3 (cam_temp), ACCDET | VIO18/VIO28, camera LDOs, AFE domain | MT6375/MT6373/MT6338 nodes verified in DT; covered by rows 3, 5, 6, 11, 13, 15 (no dedicated gate) | — | — | charger / flashlight / AFE / headset docs |
| 3 | Charger (MT6375, 80 W SuperVOOC) | `mt6375@34:chg` on `&i2c5` | i2c5 @ 0x34 | VBUS, OTG; 2S envelope 6800–8950 mV | Charger node verified; "SuperVOOC 80 W" is published-spec claim | `charger/` (B18): `lynx_charger_preflight.py` + charge-cap script | 6 (+1 script) | `LYNX-CHARGER-SUPERVOOC-PREFLIGHT-20261121.md` |
| 4 | Fuel gauge / battery health | `7-0055` (`battery_snapshot`) | i2c7 @ 0x55 | 2S cell pair, balance | TI BQ28Z610 verified in DT/stock; SOH warn <80 / crit <65 | `battery_health/` (B23) | 10 | `LYNX-BATTERY-HEALTH-EVALUATOR-20261121.md` |
| 5 | Modem (MD1 / CCCI) | CCCI subsystem; `/dev/ccci_*`, `/sys/kernel/ccci/boot` (md1:0–2) | CCCI shared channels | baseband clocks; `md1img` 77.17 MiB (sha256 `7cf648e7…c2fa7`) | CCCI path verified; RF isolation assessed, no live trial | `lynx_modem_preflight.py` | 14 | `LYNX-MODEM-CCCI-PREFLIGHT-20261121.md`, `LYNX-MODEM-RF-ISOLATION-20261121.md` |
| 6 | Audio smart amps (TFA9874 ×2) | `tfa98xx_L @ 0x34`, `tfa98xx_R @ 0x35` on `&i2c6`; `&audio_extend` (i2s-id 3, DAI `tfa98xx-aif-6-34/35`) | i2c6 @ 0x34/0x35; I2S3; reset `mt6373_pio 2/1` | amp supplies | `nxp,tfa98xx` DT verified; firmware container offline-only | `audio/` (Round 6): `lynx_audio_amp_preflight.py` | 6 | `LYNX-AUDIO-TFA9874-AMP-PREFLIGHT-20261121.md` |
| 7 | Audio AFE PCM & SCP DSP | `afe: mt6983-afe-pcm@1e100000` (IRQ 448), `snd_scp_ultra`, `sound` (`mediatek,mt6983-mt6338-sound`), `audio_sram@1e102000` | MMIO 0x1e100000/0x2000; GIC_SPI 448 | `MT6983_POWER_DOMAIN_AUDIO`, `topckgen/apmixedsys/infracfg_ao_clk` | AFE/machine DT verified; DAI link & sample-rate asserts = vendor-driver territory, **not asserted** | `audio_afe/` (D23) | 35 | `LYNX-AUDIO-AFE-PREFLIGHT-20261121.md` |
| 8 | AMOLED display | `&dsi0`: `panel5@0` (Tianma NT37705, active), `panel2@0` (BOE NT37701A, second-source) | GPIO 86 (reset), 148 (VDDR en), 36 (TE sw), 24 (TE out); pinctrl GPIO 84/85 | panel rails; `mt6373_adc` AUXADC VIN1 channel sense | panel DTS verified; `oplus_display_panel` flagged as *required module, not proven loaded* | `display/` (D17) | 29 | `LYNX-DISPLAY-PANEL-PREFLIGHT-20261121.md` |
| 9 | Touchscreen | `synaptics20171@4B` on `&i2c0` (`synaptics-s3908`, 400 kHz; 17 TX/38 RX, 10 pts, 60 Hz) | i2c0 @ 0x4B; IRQ GPIO 8, reset GPIO 3 | — | S3908 verified in DT; Goodix GT9886 is a *second-source* entry only (queue's `goodix_core` guess corrected) | `touch/` (D18) | 29 | `LYNX-TOUCHSCREEN-PREFLIGHT-20261121.md` |
| 10 | Camera main (IMX890) | `sensor0@36` on `&i2c8` (`i2c@11d05000`); names `ov64b_mipi_raw_22823` / `imx890_mipi_raw_21871` | i2c8 @ 0x36 | HW_ID rails: AVDD 2.804 V (ldo3), AVDD1 1.804 V (ldo6), AFVDD 2.804 V (ldo5), DOVDD 1.804 V (ldo7) | sensor + driver source on disk | `camera_deps/lynx_imx890_preflight.py` (D17-2) | 7 | `LYNX-CAMERA-IMX890-PREFLIGHT-20261121.md` |
| 11 | Camera front (S5K3P9SP) | `sensor1@10` on `&i2c9` (`i2c@11d06000`) | i2c9 @ 0x10 | DVDD 1.104 V (ldo1), AVDD 2.804 V (ldo4), DOVDD 1.804 V (ldo7) | sensor + driver source on disk | `camera_deps/lynx_s5k3p9sp_preflight.py` | 7 | `LYNX-CAMERA-S5K3P9SP-PREFLIGHT-20261121.md` |
| 12 | Cameras aux (IMX355 + GC02M1) | `sensor2@1a` on `&i2c2` (400 kHz); `sensor4@3d` on `&i2c9` (1 MHz) — **no `sensor3` exists** | i2c2 @ 0x1a; i2c9 @ 0x3d | IMX355: avdd ldo4 / dvdd ldo2 / dovdd ldo7; GC02M1: avdd ldo4 / dovdd ldo7 (no dvdd) | sensors verified; queue's "sensor2 + sensor3" corrected to sensor4 | `camera_deps/lynx_aux_camera_preflight.py` + dependency map (D19) | 30 + 6 | `LYNX-AUX-CAMERAS-PREFLIGHT-20261121.md`, `LYNX-CAMERA-DEPENDENCY-MAP-20261121.md` |
| 13 | USB-C DP Alt Mode & redriver | `&ps5170` on `&i2c6` (alias `ps5170@30`, `parade,ps5170`); `usb_dp_selector@10005600`; `&mt6375_typec` | i2c6 @ 0x28; `ps_enable/ps_disable` GPIO 204; SVID 0xff01 | VBUS/OTG via MT6375 | redriver + selector DT verified | `usb_dp/lynx_usb_dp_preflight.py` (B19) | 10 | `LYNX-USB-DP-ALTMODE-PREFLIGHT-20261121.md` |
| 14 | SCP low-power island | RISC-V SCP @ `0x1c700000`; TCM 2 MiB @ `0x1c400000`; `mtk_lpm` | 5 mailboxes (mbox0–4); 7 SPI IRQ; IPIs (C_SLEEP, SENSOR_CTRL, AUDIO_VOW, APCCCI, SCP_AOD) | always-on island | SCP mailbox DT verified; vendor SCP fw images not asserted | `lpm/lynx_lpm_preflight.py` (B20) | 10 | `LYNX-LPM-SCP-PREFLIGHT-20261121.md` |
| 15 | GNSS | MT6685-class integrated GNSS (GPS/GLONASS/Galileo/BeiDou/QZSS/NavIC, L1/L5 per doc) | `/dev/stpgps`; STP channel 0 | shared Wi-Fi/BT/GNSS PM (`stpgps`), `gps_scp.ko` assist | device node + module verified; exact IC id not statically proven | `gnss/lynx_gnss_readiness.py` (B12) | 8 | `LYNX-GNSS-FIX-TRIAL-READINESS-20261121.md` |
| 16 | Headset Type-C MUX | `fsa4480` (Type-C crossbar); `mt6338_accdet` (`mediated` via `mt6983-mt6338-sound`); input `mt6983-mt6338 Headset Jack` | `hs-det-gpio` GPIO 98; ACCDET on `mt6338_auxadc AUXADC_ACCDET` (efuse-calibrated, mic-vol 8) | PMIC ADC sense | FSA4480 + accdet DT verified; 3.5 mm jack **absent** = published-spec claim (no socket in DT/chassis check) | `headset/lynx_headset_collector.py` (B13) | 11 | `LYNX-HEADSET-TYPEC-ANALOG-DETECTION-20261121.md`, `LYNX-HEADSET-INSERTION-EVIDENCE-20261121.md` |
| 17 | NFC (SN110T) | NXP SN110T, `/dev/nq-nci` (NCI 1.0/2.0) | i2c6 @ 0x28 (per source doc); chip id `0xA4`, ROM `0x01` | power-rail sequencing | `oplus_nfc`/`nfc_i2c` probe path verified in doc | `nfc/lynx_nci_parser.py` + `lynx_nfc_validator.py` (B14) | 13 + 5 | `LYNX-NFC-NCI-RECEIPT-DECODER-20261121.md` |
| 18 | Haptics (LRA) | `vibrator0: vibrator@0` on `&odm` (`mediatek,vibrator`; `vib_timer 25`, `vib_limit 9`, `vib_vol 9`) | — | — | vibrator class node verified; queue's "MT6375 LRA driver" = **UNVERIFIED** (no such driver in snapshot) | `haptics/lynx_haptics_preflight.py` (D21, ACCEPT) | 31 | `LYNX-HAPTICS-LRA-PREFLIGHT-20261121.md` |
| 19 | Flashlight core | `flashlight_core` (top-level, `mediatek,flashlight_core`); `lm3642@63` on `&i2c6` (single `flash@0`, `fl_core_0`↔`flashlight_0` on `&mtk_composite_v4l2_1`); `cam_temp` NTC on `mt6373_adc` AUXADC_VIN3 | i2c6 @ 0x63; hwen GPIO 33 | torch LED supply | LM3642 + core DT verified (live-DT receipt boot `0fe847d2`: SINGLE_CHANNEL_ONLY); queue's dual-LED + MT6375 300/1500 mA = **UNVERIFIED/contradicted** (2nd rear circle = ams TCS3408 CCT/ALS) | `flashlight_gate/lynx_flashlight_gate.py` (D22, ACCEPT) | 35 | `LYNX-FLASHLIGHT-CORE-PREFLIGHT-20261121.md`, `LYNX-SECOND-REAR-LIGHT-ANALYSIS-20261121.md` |
| 20 | Consumer IR blaster | `consumerIr` (`oplus,kookong_ir_pwm`, `pwm-num` on mtk-pwm); `consumer_ir_core` (`oplus,kookong_ir_core`) | SoC PWM channel; `/dev/ir_remote` | — | core + PWM nodes verified; KooKong modules `oplus_bsp_ir_core.ko`, `oplus_bsp_kookong_ir_pwm.ko` cited from stock | `ir_blaster/lynx_ir_blaster_preflight.py` (B21) | 10 | `LYNX-IR-BLASTER-PREFLIGHT-20261121.md` |
| 21 | Alert slider (tri-state key) | MagnaChip MXM1120 down `0x0C` (GPIO 5, `downhall_tri_state_key_active`), up `0x0D` (GPIO 4); second-source Isentek IST8801 `0x18`/`0x19` | i2c0 (`0x11e00000`) @ 0x0C/0x0D (+0x18/0x19) | VIO18 / VIO28 | dual-hall mapping verified in stock-merged.dtb (per B25 doc) | `tri_state_key/lynx_tri_state_key_preflight.py` (B25) | 10 | `LYNX-TRI-STATE-KEY-PREFLIGHT-20261121.md` |
| 22 | UFS 3.1 storage | `ufshci@112b0000` (IRQ 169); M-PHY Gear 4 dual-lane PHY @ `0x11fa0000` | 5 clocks (ufs_hd_haxi, ufs_fde, ufs, ufs_mbist, ufs_hf_fmem); 3 syscon resets (unipro_rst, crypto_rst, hci_rst) | `mt6363_vufs18` / `mt6363_vufs12` | host + PHY DT verified; JEDEC JESD220E descriptors evaluated offline | `ufs/lynx_ufs_preflight.py` (B26) | 10 | `LYNX-UFS-STORAGE-PREFLIGHT-20261121.md` |
| 23 | Fingerprint | `spi7@11017000/fingerprint@0` (`oplus,fp_spi`), bus dev `spi7.0` | SPI7 CS0 | — | node active in V53 DT, **no driver bound**; `uff_fp_driver.ko` + `oplus_fp_common.ko` stock; exact optical IC (Goodix/FocalTech/Silead) **not statically proven** | `fingerprint/` (Round 6): `lynx_fingerprint_inventory.py` | 7 | `LYNX-FINGERPRINT-PREFLIGHT-20261121.md`, `LYNX-FINGERPRINT-SECURE-BOUNDARY-20261121.md` |
| 24 | Bluetooth (link state) | STP HCI / `hci_uart` bridge on BT controller | BT PM shared with GNSS (row 15) | controller power domain | controller power/link-state read architecture (V52 trial lineage) | `bluetooth/`: `lynx_bluetooth_link_state.py` + `lynx_bt_acceptance_gate.py` + proposal tests (B6 round) | 10 + 8 + 5 | `LYNX-BLUETOOTH-LINK-STATE-DESIGN.md`, `LYNX-BLUETOOTH-LINK-STATE-PROPOSAL-20261121.md`, `LYNX-BLUETOOTH-ATTENDED-ACCEPTANCE-TRIAL.md` |

**Subsystem gate test total: 372** (rows 1–24, excluding the env-blocked `test_lynx_ble_gatt_probe` GATT probe which needs `dbus_next`).

## 3. Unverified / corrected queue claims (consolidated)

Each gate documents its unverified claims at point of writing (precedent D17 → D19 → D21); consolidated here for the reviewer:

1. **Haptics:** "MT6375 LRA driver" (D21 queue) — no such driver in the on-disk snapshot; gate binds to the Linux vibrator class instead.
2. **Flashlight:** "dual-LED torch + MT6375 300/1500 mA limits" (D22 queue) — contradicted by live-DT receipt `0fe847d2` (SINGLE_CHANNEL_ONLY) and the TCS3408 second-rear-light analysis; not asserted.
3. **Audio AFE:** DAI-link / buffer / sample-rate assertions (D23 queue) — vendor-driver territory; no `drivers/sound` in snapshot; not asserted.
4. **Touchscreen:** queue's `touch_synaptics`/`goodix_core` modules corrected to Synaptics S3908 (Goodix only as second-source).
5. **Cameras aux:** queue's "sensor2 + sensor3" corrected — board has `sensor4@3d`, no `sensor3`.
6. **Headset:** 3.5 mm socket absence is a published-spec claim pending Noob's physical confirmation.
7. **Fingerprint:** exact optical IC not statically provable; driver unbound on V53.
8. **GNSS:** exact GNSS IC id not statically proven (STP channel + `/dev/stpgps` verified).
9. **Charger:** "80 W SuperVOOC" is published-spec; the gate enforces the DT-derived 2S voltage/thermal envelopes.
10. **CPU cluster split:** quoted from the LVTS map, not re-derived.

## 4. Consolidated runner evidence (snapshot 2026-11-21, post D23)

```
Overall: PASS
Suites: 94 total, 93 ok, 0 failed, 1 env-blocked
Env-blocked: test_lynx_ble_gatt_probe [missing python module: dbus_next]
```
(`lynx/tools/run_all_lynx_tests.py`; counts are a snapshot — Banshee's concurrent landings may add suites between runs.)

## 5. Coverage statement

All 18 subsystems named in the D24 queue are covered above: **CPU** (row 1), **PMIC** (row 2), **Charger** (3), **Fuel Gauge** (4), **Modem CCCI** (5), **Audio Smart Amps** (6), **Audio AFE** (7), **AMOLED Display** (8), **Touchscreen** (9), **Cameras — main IMX890 / front S5K3P9SP / aux IMX355 / macro GC02M1** (10–12), **USB-C DP & redriver** (13), **SCP Low-Power Island** (14), **GNSS** (15), **Headset Type-C MUX** (16), **NFC SN110** (17), **Haptics** (18), **Flashlight** (19). Plus the Round 7 bonus gates: **IR blaster** (20), **thermal zones** (row 1), **battery health** (row 4), **tri-state key** (21), **UFS storage** (22), **fingerprint** (23), **Bluetooth link state** (24).
