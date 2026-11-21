# Lynx GNSS Fix-Trial Readiness Checklist & Architecture

## 1. Executive Summary & Boundaries

- **Platform**: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 "Vitamin")
- **GNSS Subsystem**: MediaTek MT6685 / MT6983 integrated multi-constellation GNSS (GPS, GLONASS, Galileo, BeiDou, QZSS, NavIC) with dual-frequency L1/L5 support.
- **Trial Objective**: Prepare an offline preflight checklist, evaluation criteria, and a strictly read-only collector for GNSS fix readiness.
- **Trial Ownership**: **Aria runs the actual live fix trial last.** This document and tooling define the readiness gate, power constraints, driver/node dependencies, and NMEA receipt validation without executing unattended live RF trials or unauthorized daemon spawns.

---

## 2. Readiness Checklist Matrix

To declare Lynx ready for a live attended GNSS fix trial, all four gates must be satisfied:

```
+-----------------------------------------------------------------------+
|                       GNSS FIX-TRIAL READINESS GATES                  |
+-----------------------------------------------------------------------+
|  1. Driver & Node Gate                                                |
|     [x] conninfra & connadp loaded (connectivity backbone)            |
|     [ ] gps_drv (stp_chrdev_gps) inserted                             |
|     [ ] gps_pwr inserted (PMIC RF rail control)                       |
|     [ ] /dev/stpgps character device present (crw-rw---- 191, 0)      |
|     [x] /dev/ccci_c2k_agps present (modem AGPS assist)                |
+-----------------------------------------------------------------------+
|  2. Power & Thermal Safety Gate                                       |
|     [x] Battery capacity >= 35% nominal (cutoff >= 20%)               |
|     [x] Pack voltage >= 7400 mV (2S pack healthy)                    |
|     [x] Battery temperature <= 40.0 °C (hard cutoff at 45.0 °C)       |
|     [x] Zero battery gauge read errors (capacity/voltage/temp error=0)|
|     [x] Charger connected or USB hold asserted                        |
+-----------------------------------------------------------------------+
|  3. Sky-View & Signal Gate                                            |
|     [ ] Physical placement with unobstructed outdoor horizon (sky)   |
|     [ ] Minimum satellites in view >= 4                               |
|     [ ] Minimum tracking satellites with C/No >= 28 dB-Hz >= 4        |
|     [ ] HDOP <= 4.0 (horizontal dilution of precision)                |
+-----------------------------------------------------------------------+
|  4. NMEA Receipt Integrity Gate                                       |
|     [ ] Checksum verified on 100% of captured sentences               |
|     [ ] GNGGA / GPGGA fix quality indicator >= 1 (1=SPS, 2=DGPS)     |
|     [ ] GNRMC / GPRMC status 'A' (Data Valid / Active)                |
|     [ ] Monotonic UTC timestamp matching system real-time clock       |
+-----------------------------------------------------------------------+
```

---

## 3. Driver & Device Node Architecture

### 3.1 Kernel Driver Stack
The MediaTek GPS subsystem relies on a three-tier modular architecture:
1. **Connectivity Infrastructure (`conninfra.ko`, `connadp.ko`)**:
   - Manages shared Wi-Fi/BT/GNSS power management, sleep clocks, and EMI buffers.
   - *Status*: **Live and verified** in running kernel (`conninfra` refcount 3, `connadp` refcount 3).
2. **GPS Transport Driver (`gps_drv.ko` / `stp_chrdev_gps.c`)**:
   - Implements STP (Serial Transport Protocol) channel 0 for GNSS data.
   - Instantiates device node `/dev/stpgps`.
   - Manages DMA ring buffers (`bgf_gps_dma.h`) and L1/L5 UART/APB interfaces.
3. **GPS Power Controller (`gps_pwr.ko`)**:
   - Manages RF LNA (Low Noise Amplifier) power supplies and TCXO clock buffers (`gps_lna_drv.c`).
4. **Co-Processor Assist (`gps_scp.ko`)**:
   - Low-power offload path to MT6983 SCP (System Companion Processor).

### 3.2 Userspace Daemon Interface (`mnld`)
- The MediaTek Navigation Daemon (`mnld`) coordinates NMEA parsing, ephemeris injection, and AGPS:
  - Socket: `/dev/socket/mnld`
  - Output streams: NMEA 0183 (`$GNGGA`, `$GNRMC`, `$GPGSV`, `$GLGSV`, `$GAGSV`, `$BDGSV`, `$GNGSA`).

---

## 4. Power & Thermal Safety Gate

GNSS RF receivers increase baseline power consumption and thermal load on the PMIC:
1. **Gauge Telemetry Source**: `/sys/bus/i2c/devices/7-0055/battery_snapshot` (BQ28Z610 gas gauge).
2. **Verification Requirements**:
   - `gauge_device_type = 42495`
   - `capacity_percent >= 35` (reserve requirement for trial initiation; abort if `< 20`)
   - `pack_voltage_mv >= 7400` (nominal 2S battery pack voltage; minimum cell voltage 3.7V)
   - `temperature_millidegrees_celsius <= 40000` (40.0°C; abort trial if temperature exceeds 45.0°C)
   - `capacity_error = 0`, `voltage_error = 0`, `temperature_error = 0`

---

## 5. Sky-View & NMEA Fix Criteria

To distinguish a real optical/RF satellite fix from indoor noise or multipath reflection:
1. **Satellite Geometry**:
   - A 3D navigational solution requires at least 4 independent pseudo-range measurements.
   - Dual-frequency L1 + L5 operation provides sub-meter accuracy when tracking >= 6 satellites.
2. **Signal Quality (Carrier-to-Noise Ratio, C/No)**:
   - Deep indoor / shielded: C/No < 20 dB-Hz (no lock possible).
   - Marginal / window: C/No 20–28 dB-Hz (unstable lock).
   - Clear sky nominal: C/No >= 30–42 dB-Hz on at least 4 satellites.
3. **NMEA Sentence Validation**:
   - `$GNGGA`: Fix quality `1` (GPS SPS) or `2` (Differential GPS), satellites used >= 4, HDOP < 4.0.
   - `$GNRMC`: Field 2 == `'A'` (Data Valid). Field 2 == `'V'` (Receiver Warning / Invalid) is rejected.
   - Checksum: XOR of all bytes between `$` and `*` must match the 2-digit hex checksum.

---

## 6. Live Telemetry from Lynx (Boot `0fe847d2`)

Live read-only query on Lynx confirms:
- **Connectivity Infrastructure**: `conninfra` and `connadp` are loaded and operational.
- **Power Gate**: Battery capacity `100%`, voltage `8707 mV`, temperature `28.1 °C`, errors `0`. Status `Charging`. **PASSED.**
- **Drivers & Nodes**: `gps_drv` is not yet loaded; `/dev/stpgps` is not yet instantiated.
- **Overall Status**: **`QUIESCENT_SAFE`** — Hardware power and connectivity are 100% healthy; system is quiescent and ready for Aria's staged trial execution.
