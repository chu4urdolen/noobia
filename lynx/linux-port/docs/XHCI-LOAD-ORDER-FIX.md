# Matching xHCI driver required before MTU3 initialization

The native 34-module image omitted `xhci-mtk-hcd.ko`. This is a concrete module
coverage error, not a confirmed cause of the hardware boot failure. Physical
native PID1 and kernel crash-log evidence remain unavailable.

The exact stock base DTB has an enabled `/soc/usb0@11201000/xhci0@11200000`
child compatible `mediatek,mtk-xhci`; the USB parent has `mediatek,clk-mgr` and
`usb-role-switch`. The matching stock xHCI module aliases include that compatible,
its module name is `xhci_mtk_hcd`, and its kernel release/symbol versions match.
It has no additional `modules.dep` dependency.

Published OnePlus code initializes host-side child devices before the role switch.
It stores a platform-driver pointer derived from the child device's driver without
checking that the child has a bound driver. Initial clock-manager role setup calls
the host-unregistration path. Loading MTU3 without its xHCI driver can therefore
leave an invalid pointer for that later path. This is a plausible kernel fault;
it is not proof that this path executed in our failed hardware trials.

The exact stock module corroborates the host-pointer operation: saved disassembly
`stock-mtu3-host-init-disassembly.txt`, instructions 0x54d4..0x54e0, loads the
device-driver pointer, subtracts 0x28 and stores it without a null-driver check.
The published role code guards the stored pointer for zero, not an invalid
negative container pointer. Compatible-string audit leads for frequency meter
and hang detection were not automatically added: string presence alone does not
establish a required provider.

The corrected offline candidate is
`artifacts/busybox-August-usb-device-xhci/nord3-busybox-candidate.img`, 64 MiB,
SHA256 `6ec551d5f4742fdb6c06d5e5f012ef934fa8663d0010fb7957bee3d81242e5d9`.
It loads 35 exact stock modules, placing xHCI immediately before MTU3 after the
other hardware suppliers. If the xHCI module does not appear in sysfs after
insertion, init withholds MTU3. The explicit peripheral-mode helper also requires
the xHCI module. This does not establish that the physical child probe succeeds.

The exact image, stock vendor-before-generic ramdisk combination and unchanged
stock kernel executed native PID1 and an interactive ARM64 shell in QEMU, loading
all 35 modules without a custom USB boot argument. Thirteen peripheral-mode helper
guard tests passed. Independent image validation and unlocked/locked upstream AVB
models passed their expected checks. Original OEM boot-local metadata is retained
with the expected modified-data hash mismatch; native OEM signature approval is
not claimed. Actual OnePlus LK and physical MT6983 behavior remain unproven.

Evidence: `usb-module-coverage-audit.json`, `usb-device-xhci-guard-tests.json`,
`usb-device-xhci-arm64-validation.json`, `usb-device-xhci-avb-model.json`,
and `artifacts/emulated-usb-device-xhci/`.

`tools/lynx_boot_a_usb_xhci_trial.py` defaults to offline readiness and pins this
candidate, verified stock undo, matching baseline receipts and fresh Fastboot
identity/slot/size checks before a write. It permits only boot_a writes, one normal
reboot after a successful trial write, or stock boot_a restoration. No companion
partition, slot B, erase, lock or authentication bypass is included.

At preparation time Lynx remains enumerated as OPLUS Preloader after the completed
stock-loader availability check; the stock loader can await its unsent file.
The new Linux image has not been flashed. Last persistent boot_a remains the
successfully restored August stock image. A physical reset to Fastboot is needed
before any new native trial.

References: [OnePlus host initialization](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/usb/mtu3/mtu3_host.c),
[OnePlus role switching](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/usb/mtu3/mtu3_dr.c).

## Hardware trial

The user reached Fastboot after waiting for recovery, using Volume Down + Power
to start, then connecting USB once Fastboot was on screen. Host enumerated
0e8d:201c; fresh serial/product/unlocked/slot-A/bootloader/size checks all passed.
The corrected image write to boot_a and the normal reboot both returned OKAY:
`logs/boot-a-usb-xhci-trial-1791652936719946783.json`.

Complete 60-second passive observation:
`logs/lynx-usb-observation-1791652951320637469.json`.
No phone USB endpoint or ttyACM appeared. No native Linux hardware marker has
been retrieved. The omission is corrected offline, but the trial result does
not establish whether the kernel started, another supplier deferred, or a
different boot failure occurred. Do not declare the xHCI change a hardware fix.

The corrected native image remains the last recorded boot_a write. Stock undo
has not yet been issued after this trial and requires physical return to Fastboot.
No other partition or slot was changed during this trial.

The user returned quickly to Fastboot. Fresh preflight passed and verified stock
boot_a undo returned OKAY, with no reboot:
`logs/boot-a-usb-xhci-trial-1791653164047994118.json`.
This supersedes the preceding installed-image statement; stock boot_a is again
the last recorded persistent write. Reviewed bootloader log export succeeded:
`logs/pllk-1791653196269209324.json` (312821 raw bytes, 181468 reconstructed).
