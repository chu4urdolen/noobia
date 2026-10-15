# Power controller and clock review

The immediate goal is native Noobia Wi-Fi and key-only SSH. UFS is needed to
read the verified second-stage userspace and radio payload from boot_a.

The published `init_scp` initializes every declared domain before the single
provider is registered. A clock lookup failure in an image/camera/display
domain can therefore prevent the UFS domain from being discoverable. The stock
merged DT has 54 clock specifiers for this controller. Exact stock ELF match
tables identify five missing early suppliers: cam, img, mdp_grp, mm, vcodec.
`scpsys-clock-suppliers.json` records each specifier and match-table object.

The existing bootstrap already loads mrdump, aee_aed and clk-common. The first
VM test omitted the AEE prerequisites and failed on unresolved symbols; that
receipt is preserved. The corrected isolated stock-kernel ARM64 test loaded
all eight modules successfully and powered off without a kernel exception:
`artifacts/emulated-native-power-clocks-v2-cortex-a710-1791923200142625988/result.json`.
This verifies loading/ABI, not MediaTek MMIO access or physical binding.

Two checks must remain distinct:

- `mt6983_scpsys_probe` ignores the return of `mtk_register_power_domains` in
  the published reference. A bound driver does not prove provider registration.
- Clock probes can ignore gate-registration failure, and the shared helper
  continues after individual registration errors. A loaded clock module or
  registered provider does not prove that every requested clock is available.

Clock registration temporarily suppresses gate `is_enabled` reads through
`is_registered=false`. The camera raw-register dump is a separate exported
debug function, not part of the reviewed probe. This reduces a suspected
registration-time MMIO hazard; later gate operations still access hardware.
The stock power-domain registration also initializes domains not marked
BYPASS_INIT_ON. We are using its normal matching driver path, not writing
registers through a custom helper or changing domain tables.

The published generic PM attachment path calls
`driver_deferred_probe_check_state` when a provider lookup fails. It can return
ETIMEDOUT and emit `deferred probe timeout, ignoring dependency`. That literal
exists in the exact stock kernel. Ordinary domain power-on failure is converted
to EPROBE_DEFER in this reference. The handset's -110 therefore does not by
itself prove a physical controller timeout. The warning itself has not yet
been retrieved or separately identified on the handset.

Wi-Fi v5 adds exactly these five stock modules before scpsys, uses the already
tested `fw_devlink=permissive` argument, and retains the prepared Wi-Fi/SSH
payload, factory-calibration read-only policy and recovery metadata. The kernel
is unchanged. The final ramdisk is 1644684 bytes with 4096 bytes of aligned
space remaining before the existing metadata boundary. Final image checks and
the collector readiness check remain mandatory before any handset trial.

The reviewed source revision is 81ec42ad5e803be0cba619f9f7bb298db7d33d7b,
not the exact stock build commit. Exact compiled module hashes and match tables
support the mapping; runtime consequences still require a controlled trial.
