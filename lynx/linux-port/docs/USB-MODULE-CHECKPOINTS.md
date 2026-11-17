The first ACM-only BusyBox console trial exposed no host USB endpoint in the
180-second observation, and the console capture contained zero bytes. This
does not identify the kernel stage reached. The verified stock boot image was
restored to boot_a without rebooting:
`logs/boot-a-busybox-console-trial-1791667721697489275.json`.

Two separate offline diagnostic images now retain the proven native BusyBox
baseline and the exact stock kernel. The `suppliers` image inserts the support
modules through xHCI; `with-mtu3` adds the final MTU3 controller module. Neither
configures a gadget or requests a USB role change. Each first requires the
proven reset-driver bindings and properties, stops on any unsuccessful module
insertion, checks those reset guards again, then requests one standard Linux
RESTART2 bootloader return. There is no repeated reboot or partition write in
their init code.

A controlled software return with corroborating reset evidence would show
that all listed insmod calls returned successfully. It would not establish
that every platform driver bound or that USB works. A missing return cannot
distinguish an insertion error, probe hang, or later reset failure. Preserve
these distinctions when reporting results.

Artifacts are in `artifacts/busybox-usb-module-checkpoints/`. Their reports mark
them as not flash eligible until independent validation is complete. Host
fixtures passed all six cases, including failed insertion stopping before
the following module, delayed enumeration, missing state, and a bounded
30-second enumeration timeout. Both exact images executed native PID1 in
isolated QEMU and refused further hardware-dependent work because the real
watchdog/reboot-mode devices were absent. This validates refusal behavior,
not MT6983 hardware module loading.

With-MTU3 independent fixed-image/module checks and unlocked/locked AVB policy
checks passed in `docs/usb-module-checkpoint-validation.json`. The host timing
collector passed three fixtures demonstrating that initial or uninterrupted
Fastboot presence cannot count as a software return. One authorized hardware
checkpoint has now been issued; see SESSION-STATE for its live receipt and
current installed image. The suppliers-only image has not been flashed.

Absence of userspace USB-role calls does not mean the controller performs no
role setup: the published MTU3 probe initializes its OTG switch internally.
This checkpoint isolates the later init-script gadget/configuration work, but
cannot isolate all controller role behavior. A negative result must not be
reported as proof that USB role handling is uninvolved.

The separate `init-busybox-usb-console-enumeration-draft` now checks UDC state
for `configured` after gadget binding, rather than treating a successful bind
as host enumeration. Its 30-second deadline requests the existing guarded
Fastboot fallback on failure. It remains an unbuilt draft. This does not bound
a kernel module probe that never returns or prove that a host opened ttyGS0.

The original failed console image, its exact source, its validator, the
successful three-module native proof, and every capture remain unchanged.
