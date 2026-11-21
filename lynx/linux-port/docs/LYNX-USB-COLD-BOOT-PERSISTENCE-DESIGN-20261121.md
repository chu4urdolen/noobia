# Lynx USB MTU3 ACM Cold-Boot Persistence Design

## 1. Platform Identity and Purpose

- **Device**: OnePlus Nord 3 5G (CPH2493)
- **SoC / Platform**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Kernel ABI**: `5.10.149-android12-9-o-g311738fbb5a8`
- **Controller**: MediaTek MTU3 (`11201000.usb0`)
- **Module**: Stock `mtu3.ko` (SHA-256 `d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467`)
- **Objective**: Design an offline OpenRC service architecture that brings up the MTU3 CDC ACM serial gadget at boot while preserving system stability, OpenRC ordering invariants, and Wi-Fi/SSH management lifelines.

> [!IMPORTANT]
> **Safety Boundary**: This document is strictly an offline architectural design. No OpenRC service is installed to the phone rootfs, no boot partition writes are performed, and no live gadget changes are made during this task. Aria owns live trial execution and deployment approval.

---

## 2. Boot Architecture: What Brings Up MTU3 and the ACM Gadget

The hardware trail receipt `lynx/logs/v53-usb-ram-1795214496222771892/result.json` proved that the MTU3 controller is populated under `/sys/bus/platform/devices/11201000.usb0` in device mode (`mtu3_mode = 3`).

Bringing the ACM gadget up automatically at cold boot requires four coordinated steps:
1. **Module Insertion**: Inserting stock `mtu3.ko` into the running kernel once root filesystems and core dependencies (`mtk-dvfsrc`) are ready.
2. **ConfigFS Hierarchy Setup**: Mounting `configfs` at `/sys/kernel/config` and creating gadget directory `usb_gadget/lynx`.
3. **USB Descriptors & Function Composition**:
   - Vendor/Product IDs: `idVendor=0x18d1`, `idProduct=0x0001` (CDC ACM).
   - Strings: Manufacturer `"Noobia"`, Product `"Lynx Nord 3 USB ACM"`.
   - Function: `functions/acm.usb0`.
   - Configuration: `configs/c.1` linked to `functions/acm.usb0`.
4. **UDC Binding**: Writing `11201000.usb0` to `usb_gadget/lynx/UDC`. This instantiates `/dev/ttyGS0` locally on Lynx and exposes `/dev/ttyACM0` on the connected host (Nexus).

---

## 3. OpenRC Service Design (`lynx-usb-gadget`)

The reference init script is maintained in [`lynx/tools/usb/lynx-usb-gadget.initd`](file:///noobia/lynx/tools/usb/lynx-usb-gadget.initd).

```sh
#!/sbin/openrc-run
description="Lynx USB MTU3 ACM Gadget persistence service"

DISABLE_SWITCH="/etc/lynx/disable-usb-gadget"
GADGET_DIR="/sys/kernel/config/usb_gadget/lynx"
UDC_TARGET="11201000.usb0"
MODULE_PATH="/lib/modules/$(uname -r)/kernel/drivers/usb/mtu3/mtu3.ko"

depend() {
    after bootmisc modules sshd
    provide usb-gadget
}
```

### 3.1 Ordering Constraints Against Wi-Fi and SSH

To prevent boot hangs and maintain unattended recovery safety:
1. **Declare `after bootmisc modules`**: Ensures `configfs` kernel support and required clock/power regulators are enumerated before gadget creation.
2. **Declare `after sshd` (Strict Non-Delay Invariant)**:
   - The service must **never** declare `before sshd`. SSH is Lynx's primary recovery route, so USB gadget startup must never precede or delay `sshd`.
   - By starting `after sshd`, remote SSH access on port 2222 is fully active and listening before USB gadget initialization begins.
3. **Bounded Execution Timeouts**:
   - Both driver insertion (`modprobe mtu3` / `insmod`) and UDC binding are wrapped with explicit bounds (`/bin/busybox timeout -t 5` and `timeout -t 3`). If the MTU3 controller or ConfigFS hangs, the operation aborts within seconds rather than locking PID 1.
4. **Decoupled from Wi-Fi**:
   - The service must **never** declare `need net` or `need lynx-wifi`. USB serial is a local hardware transport and must remain completely decoupled from Wi-Fi networking.
   - If `mtu3.ko` fails to load, `configfs` cannot be mounted, or UDC binding fails, the service emits warnings (`ewarn`) and exits cleanly (`return 0` soft-fail). It must **never** fail with a blocking exit code that halts OpenRC runlevel execution.
   - Wi-Fi SSH (`192.168.100.107:2222`) remains the primary, uncompromised recovery lifeline.

---

## 4. Emergency Local Disable Switch

To protect against persistent reboot loops or corrupt USB state, the service implements an emergency file-based disable switch:

- **Switch Path**: `/etc/lynx/disable-usb-gadget`
- **Behavior in `start_pre()` and `start()`**:
  ```sh
  if [ -f "$DISABLE_SWITCH" ]; then
      ewarn "USB gadget startup disabled via $DISABLE_SWITCH"
      return 0
  fi
  ```
- **Inhibition Guarantee**: If the switch exists, the service exits immediately as a successful no-op. No module is loaded, no ConfigFS directories are created, and no UDC is bound.
- **Activation / Deactivation**:
  - Disable: `touch /etc/lynx/disable-usb-gadget`
  - Re-enable: `rm -f /etc/lynx/disable-usb-gadget`

---

## 5. Teardown Procedure (`stop()`)

Clean teardown is essential to allow runtime module unloading or re-enumeration:
1. **Unbind UDC**: Write empty string to UDC:
   ```sh
   echo "" > /sys/kernel/config/usb_gadget/lynx/UDC
   ```
2. **Unlink Functions**: Remove symlink `configs/c.1/acm.usb0`.
3. **Clean Descriptors**: Remove `configs/c.1/strings/0x409`, `configs/c.1`, `functions/acm.usb0`, `strings/0x409`, and `usb_gadget/lynx`.
4. **Device Node Teardown**: Unbinding the UDC cleanly removes `/dev/ttyGS0` without kernel oops or dangling references.

---

## 6. Rollback & Failsafe Procedure

If an unattended reboot or hardware test indicates USB instability:
1. **Single-Command Disarm**:
   ```sh
   rc-update del lynx-usb-gadget default
   touch /etc/lynx/disable-usb-gadget
   ```
2. **Zero Bootloader Mutations**: Neither `boot_a` nor `vendor_boot_a` is modified. The phone's stock kernel, initramfs, and fastboot fallback routes remain 100% intact.

---

## 7. Offline Tooling and Test Verification

- **Validator Tool**: [`lynx/tools/usb/lynx_usb_boot_persistence.py`](file:///noobia/lynx/tools/usb/lynx_usb_boot_persistence.py)
  - Audits OpenRC init scripts for shebang, dependency structure, ordering invariants (strictly rejecting `before sshd` and requiring `after sshd`), bounded execution timeouts, disable switch checks, and teardown commands.
  - Classifies system telemetry into `PERSISTENT_ENABLED`, `PERSISTENT_DISABLED_SWITCH`, `RUNTIME_ONLY`, `UNCONFIGURED`, and `INVALID_ORDERING`.
- **Unit Test Suite**: [`lynx/tools/usb/test_lynx_usb_boot_persistence.py`](file:///noobia/lynx/tools/usb/test_lynx_usb_boot_persistence.py) (15 tests).
- **Test Fixture Matrix**:
  - `boot-persistence-valid-enabled.json`: Service enabled, ordering valid (`after sshd`), UDC bound.
  - `boot-persistence-disabled-switch.json`: Service enabled in runlevel but inhibited by switch.
  - `boot-persistence-invalid-ordering.json`: Service ordering violates dependency safety.
  - `boot-persistence-runtime-only.json`: Gadget active in runtime without runlevel installation.
  - `boot-persistence-unconfigured.json`: Quiescent baseline state.

All 32 unit tests across the USB suite pass with 100% offline determinism.
