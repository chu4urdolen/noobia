# Second review — B9v2 (9b45e5c), B10 (baa4558), B11 (f9a73aa) — Solo Dushich, 2026-11-21

Round-5 queue item **D12** (Gwyn, note #147/#148): Dushich second-reviews
Banshee's B10–B15 as they land; B9v2 (the post-D8 fix) is included since it
responds to my D8 REJECT. Gwyn remains the primary reviewer.

Verdicts: **B9v2 ACCEPT — B10 ACCEPT — B11 ACCEPT.**

---

## B9v2 `9b45e5c` — ACCEPT (closes D8)

Checked against the D8 fix spec
(`LYNX-USB-B9-RE-REVIEW-DUSHICH-20261121.md`, 5 steps):

| # | Spec requirement | Evidence in 9b45e5c |
| --- | --- | --- |
| 1 | initd: 6 sites → `timeout SECS PROG` | verified: `timeout 5 modprobe/insmod`, `timeout 3 mount`, `timeout 5 sh -c` (desc), `timeout 3 sh -c` (UDC) — all positional; comment cites BusyBox 1.37 positional syntax |
| 2 | validator accepts bounded positional + REJECTS `-t` | `lynx_usb_boot_persistence.py:79-82`: `forbidden_timeout_dash_t` on `timeout -t`; `missing_positional_timeout_in_script` otherwise |
| 3 | tests pin correct form | new `test_reject_timeout_dash_t`, `test_fixture_invalid_dash_t`; new fixture `fixtures/boot-persistence-invalid-dash-t.json` (negative case carries `timeout -t 5`) |
| 4 | doc cites BusyBox 1.37 usage + live evidence | design doc §3: usage `timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS`, live Lynx verification (v1.37.0, `-t` → "unrecognized option: t" exit 1) |
| 5 | suite green | `python3 -m unittest discover -s lynx/tools/usb` → **34 tests OK** (was 32) |

Not installed on Lynx; deployment remains Aria's. Second review complete.

## B10 `baa4558` — ACCEPT

IMX890 main-camera bring-up preflight (`lynx_imx890_preflight.py`).

**Safety (verified by reading the code, not the doc):**
- offline by default; live only with **both** `--live` and `--allow-live`
  (else refuses, exit error on stderr);
- live path is pure read-only shell over pinned SSH (`cat /proc/...`,
  `find /sys/firmware/...`, `ls -d /sys/bus/i2c/...`, `readlink driver`,
  `cat /proc/modules`) — no sysfs writes, no module load, no RF;
- bounded: `ConnectTimeout=5`, subprocess `timeout=8 s`, BatchMode, key-only;
- streaming/capture stay `HARD_REFUSE` under `lynx_camera_gate.py`.

**Hardware facts cross-verified against repo source (my check, not trust):**
- DT: `lynx/linux-port/sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi:428-480` → `sensor0@36`, `reg = <0x36>`, `sensor-names "imx890_mipi_raw_21871"`, `seninf_csi_port_3` — matches `EXPECTED_I2C_ADDR=0x36`, `EXPECTED_SENINF_PORT=3` ✓
- VCMs `camera_af_main@0a/@0b/@0c` (dtsi L394-415) and `camera_eeprom0@74` (L422-423) — matches `EXPECTED_VCM_ADDRS`, `EXPECTED_EEPROM_ADDR=0x74` ✓
- power rails `multi_reg_ldo3/6/5/7` + `GPIO194` DVDD + `GPIO202` RST (dtsi L456-472) — matches spec text ✓
- 9-step power sequence in the tool is **byte-for-byte** the driver's
  `pw_seq[]` array (`oneplus-nord3-sensor-power/common/imx890_mipi_raw_21871/imx890mipiraw_Sensor_21871.c` L4657-4669): `{MCLK 24 0, RST 0 1, AVDD 2804000 3, AVDD1 1804000 3, AFVDD 2804000 3, DVDD 1 4, DOVDD 1804000 3, MCLK_DC 4 6, RST 1 5}` ✓
- 6 required modules listed match mtk imgsensor stack naming ✓

**Tests:** camera_deps suite **20 tests OK** (incl. bound / unbound /
missing-DT fixtures; live path untestable offline by design).

Minor (non-blocking): doc's quoted `sensor-names` shows the `ov64b` fallback
first — matches source; readers should know the main sensor is the
*second* entry in that node.

## B11 `f9a73aa` — ACCEPT

S5K3P9SP front-camera preflight (`lynx_s5k3p9sp_preflight.py`), same design
shape as B10 (double-flag live gate, read-only, bounded).

**Hardware facts cross-verified (my check):**
- `cust_mt6983_vitamin_camera_v4l2.dtsi:490-531` → `sensor1@10`,
  `reg = <0x10>`, `s5k3p9sp_mipi_raw_22823`, `seninf_csi_port_0` —
  matches `EXPECTED_I2C_ADDR=0x10`, `EXPECTED_SENINF_PORT=0` ✓
- PHY: driver `s5k3p9spmipiraw_Sensor_22823.c` L213
  `.mipi_sensor_type = MIPI_OPHY_NCSI2`, L218 `SENSOR_MIPI_4_LANE` —
  tool accepts both `MIPI_DPHY` and `MIPI_OPHY_NCSI2` with 4 lanes —
  **more faithful than a D-PHY-only check** ✓
- MCLK 24 MHz via `CAMTG_SEL` (dtsi clock-names "24"/"mclk") ✓
- EEPROM `0x54` (`eeprom1@54`, dtsi L485-486) ✓

**Tests:** covered by the same **20-test OK** camera_deps suite run.

---

## Out of scope here

- B12 (GNSS) — Banshee's working tree shows in-flight GNSS ignore-rules;
  second review due when it lands.
- Live camera trials remain Aria's lane (attended, authorized); these tools
  are preflight/gate only and are **not installed** on Lynx.
