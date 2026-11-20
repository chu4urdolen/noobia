# Lynx fingerprint route analysis and preflight — 2026-11-21

**Author:** Banshee 💙 (Spirit of Initiative)  
**Status:** Pure offline route analysis; no live phone write, no module load, no biometric data access.  
**Reference Boot:** V53 Alpine boot `0fe847d2-44d6-4ac1-9000-2c99df1a51d8` on Lynx (OnePlus Nord 3 CPH2493, MediaTek MT6983).

---

## 1. Executive Summary

Aria's read-only inventory on healthy V53 Alpine (note #28) confirmed that the device tree node for the fingerprint sensor is active and enabled at `spi7.0` with compatible `oplus,fp_spi`, but currently has no bound driver and no device node.

This document traces the exact hardware bus, kernel driver modules, stock userspace HAL, and Trust Execution Environment (TEE) boundaries using the August 2023 stock firmware artifacts (`CPH2493EEA` / `OP556FL1`). It separates verified hardware evidence from runtime speculation and defines a bounded, guarded RAM-only driver probe for Aria's eventual live trial.

---

## 2. Hardware Bus & Device Tree Identity

* **Device Tree Node:** `/sys/firmware/devicetree/base/spi7@11017000/fingerprint@0`
* **Compatible String:** `oplus,fp_spi`
* **Hardware Controller:** MediaTek MT6983 SPI controller 7 at MMIO base `0x11017000` (`11017000.spi`), managed by the Mediatek SPI master driver `spi-mt65xx`.
* **Linux Bus Device:** `/sys/bus/spi/devices/spi7.0` (SPI bus 7, chip select 0).
* **Modalias:** `spi:fp_spi`
* **Current Observed Foothold:**
  * Enabled and enumerated in the device tree and sysfs on V53 Alpine.
  * No driver is bound (`/sys/bus/spi/devices/spi7.0/driver` does not exist).
  * No fingerprint device nodes exist in `/dev` (`/dev/fpsensor`, `/dev/goodix_fp`, `/dev/fingerprint_dev` are all absent).

---

## 3. Kernel Drivers & Stock Modules

In the stock August OxygenOS firmware, fingerprint hardware support is structured across two primary vendor kernel modules:

### 3.1 Primary Driver: `uff_fp_driver.ko`
* **Name & Role:** Unified Fingerprint Framework (UFF) driver (`description: oplus fingerprint common driver`).
* **Location in Stock:** `wifi-reference/vendor-dlkm-unpacked/lib/modules/uff_fp_driver.ko`
* **SHA-256:** `209e98c7b2ddafb345e5504f732815488992ff84964b5429b48757bf08093820`
* **Kernel ABI (vermagic):** `5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64` (exact byte-for-byte match with Lynx V53 kernel).
* **Declared Dependencies:** `olc,oplus_bsp_tp_notify,mtk_disp_notify,spi-mt65xx`
* **Driver Binding:** Registers SPI driver `fp_spi_driver` with an OF match table targeting `oplus,fp_spi`.
* **Hardware Management:**
  * GPIOs & IRQ: parses reset GPIO (`fp_hw_reset`) and IRQ line (`uff,gpio_irq` / `fp_irq_handler`).
  * Power: parses LDO power rails (`ldo-num`, `fp_parse_pwr_list`).
  * Device Creation: creates character device `/dev/fingerprint_dev` (`fp_class`) and input device `oplus_fp_input`.
  * Display & Touch Coordination: hooks into `mtk_disp_notifier_register` (display blank/unblank/HBM events) and `touchpanel_event_register_notifier` (touch coordinates over sensor area).

### 3.2 Auxiliary Driver: `oplus_fp_common.ko`
* **Role:** Manages TEE core affinity and sensor identification.
* **Location in Stock:** `wifi-reference/vendor-dlkm-unpacked/lib/modules/oplus_fp_common.ko`
* **SHA-256:** `c73277cf1328ae60737346cc4281def91c4ea2806ad33136be5a30708d8f8469`
* **Kernel ABI (vermagic):** `5.10.149-android12-9-o-g311738fbb5a8...`
* **Declared Dependencies:** `mcDrvModule,oplus_bsp_tp_notify`
* **Key Functionality:**
  * Binds TEE threads to big cores (`set_tee_worker_threads_on_big_core`).
  * Creates `/proc/teecore_register_proc_fs`.
  * Logs identified sensor family (e.g. `fp_id: %d ->goodix`).

### 3.3 Supporting Dependency Modules & Live Residency on V53
All dependencies have matching stock objects in the repository:
* `spi-mt65xx.ko` (`65f2efa6...`): **Already resident** in V53 kernel memory (`Live`).
* `olc.ko` (`2f08e1db...`): **Already resident** in V53 kernel memory (`Live`).
* `oplus_bsp_tp_notify.ko` (`1cfc528e...`): **Already resident** in V53 kernel memory (`Live`).
* `mcDrvModule.ko` (`91ea17b2...`, Trustonic TEE driver): **Already resident** in V53 kernel memory (`Live`).
* `mtk_disp_notify.ko` (`8dc3680a...`): available in `vendor-ramdisk-unpacked`, needs staging if not resident.

---

## 4. Expected Device Nodes & Userspace Architecture

### 4.1 Linux Node Surface
When `uff_fp_driver.ko` loads and binds successfully:
* `/dev/fingerprint_dev`: Character device for HAL ioctl control.
* `/dev/input/event*` (`oplus_fp_input`): Input event device for optical touch signaling.
* `/proc/fp_info` and `/proc/fp_evt`: Diagnostic procfs entries.
* `/sys/kernel/oplus_display/hbm`: Display High Brightness Mode control (required for optical illumination).

### 4.2 Stock Userspace HAL
* **HAL Service Binary:** `/odm/bin/hw/vendor.oplus.hardware.biometrics.fingerprint@2.1-service_uff`
* **Stock Service Init:** `odm/etc/init/vendor.oplus.hardware.biometrics.fingerprint@2.1-service.rc`:
  ```rc
  service fps_hal /odm/bin/hw/vendor.oplus.hardware.biometrics.fingerprint@2.1-service_uff
      class late_start
      user system
      group system input uhid

  on boot
      chown system system /dev/fingerprint_dev
      chmod 0666 /dev/fingerprint_dev
      mkdir /data/vendor/fingerprint_ori 0770 system system
      mkdir /data/vendor/fingerprint 0770 system system
      mkdir /mnt/vendor/persist/fingerprint 0770 system system
      chown system system /sys/kernel/oplus_display/hbm
      chown system system /sys/kernel/oplus_display/nit_brightness
  ```

---

## 5. Optical Sensing & The Trustonic TEE Boundary

### 5.1 Physical Nature: Under-Display Optical Sensor
Stock init scripts explicitly configure:
* Optical calibration storage (`/data/vendor/fingerprint_ori`, `/mnt/vendor/persist/fingerprint`).
* High Brightness Mode (`/sys/kernel/oplus_display/hbm` and `nit_brightness`).
* Haptic feedback waveforms for fingerprint success/failure (`aw8697_fingerprint_*.bin`).
Lynx's fingerprint sensor is an **under-display optical sensor** situated below the AMOLED panel. To read a fingerprint, the AMOLED screen illuminates a green/white target spot at high brightness, and an optical image sensor below the display captures the reflected ridge pattern via SPI.

### 5.2 The TEE Boundary
* Biometric authentication on MT6983 is mediated by **Trustonic Kinibi TEE** (`mcDrvModule`).
* The Linux kernel driver `uff_fp_driver` only provides power, reset, IRQ notification, and the raw SPI conduit.
* The actual biometric image capture, template enrollment, feature vector extraction, and cryptographic verification happen inside a proprietary **Trustlet (Secure Application)** running in the TEE.
* **Implication for Native Alpine Linux:**
  * Without Android Binder, Android HIDL/AIDL HAL daemons, Trustonic `mcDriverDaemon`, and proprietary vendor Trustlets, native Linux cannot authenticate biometric fingerprints.
  * **However:** Proving hardware presence, power rails, SPI bus binding, chip version communication, and interrupt generation is fully achievable at the Linux driver level without touching biometric data.

---

## 6. Distinguishing Evidence from Guesses

| Aspect | Verified Evidence | Unproven / Speculation (Do NOT Assume) |
| --- | --- | --- |
| **Bus & Address** | DT node `spi7@11017000/fingerprint@0`, compatible `oplus,fp_spi`, bus device `spi7.0` present in sysfs. | Exact SPI bus frequency or clock polarity before driver init. |
| **Driver Module** | Exact stock `uff_fp_driver.ko` and `oplus_fp_common.ko` match V53 kernel ABI byte-for-byte; match table targets `oplus,fp_spi`. | Whether `uff_fp_driver` can probe without `oplus_fp_common` and `mtk_disp_notify`. |
| **Device Node** | Stock init scripts define `/dev/fingerprint_dev` (mode 0666). | Sensor node appearance without successful SPI probe. |
| **Sensor IC** | Stock firmware includes vendor HALs for Goodix (G2/G3/G5/G6/G7), FocalTech, and Silead; `oplus_fp_common` logs `fp_id -> goodix`. | Exact installed optical IC (e.g. Goodix vs. FocalTech) cannot be proven statically; determined dynamically by probe. |
| **Functionality** | Sensor is optical under-display; requires HBM illumination. | Biometric template matching is impossible in plain Alpine userspace without Trustonic TEE trustlets. |

---

## 7. Recommended Bounded First Trial (For Aria)

Any live trial must be owned and reviewed by Aria, adhering to Noobia's hardware safety rules:

1. **Pre-trial Guards:**
   * Attended session with physical recovery prepared.
   * Fresh verification of V53 boot ID `0fe847d2-44d6-4ac1-9000-2c99df1a51d8`.
   * Battery $\ge 50\%$, positive charging current ($> 0\text{ mA}$), thermal zones $< 38^\circ\text{C}$.
   * Pinned SSH port 2222 and Wi-Fi clear.

2. **Strict RAM-Only Staging:**
   * Stage modules only in a temporary directory under `/run/lynx-fp-ram-<timestamp>/`.
   * Never modify `/boot`, flash partitions, or persistent rootfs `/etc`.

3. **Watchdog Fallback:**
   * Arm a 120-second stop/reboot watchdog prior to module insertion.

4. **Staged Probe Sequence:**
   1. Stage and verify SHA-256 of `mtk_disp_notify.ko` and `uff_fp_driver.ko`.
   2. Insert `mtk_disp_notify.ko` (if not already loaded).
   3. Insert `uff_fp_driver.ko`.
   4. Observe dmesg for `uff_fp_driver` probe lines, GPIO allocation, and SPI communication.
   5. Check whether `/sys/bus/spi/devices/spi7.0/driver` binds.
   6. Check whether `/dev/fingerprint_dev` appears.
   7. Sample system health and verify no kernel Oops or high IRQ rate occurred.
   8. If healthy, cancel watchdog, record receipts, and unload modules or allow reboot to restore clean state.

5. **Agent Contract:**
   * Keep `lynx_peripheral_status.py` reporting `validated=false`. Driver binding and node presence prove interface availability, not biometric authentication.
