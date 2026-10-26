# Lynx V50 charging investigation — 2026-10-26

V50 booted Alpine at `192.168.100.107` with 25–26% battery. While connected
to Nexus, the MT6375 charger supply reported `online=0`, `status=Not charging`
and `usb_type=Unknown`. Battery and thermal readings were valid. The user was
asked to connect a known-good wall charger; its result is pending.

The matching August stock `tcpc_mt6375.ko` was absent from V50's loaded
modules although `tcpc_class` and `pd_dbg_info` were present. The platform
device `11e01000.i2c:mt6375@34:tcpc` was unbound. In stock
`mt6375-charger.c`, the `online` property reads the attach state, and the
charger can use Type-C attach events. This made missing TCPC registration a
specific hypothesis, not proof of a charging fault.

`tools/trial_v50_tcpc_mt6375.py` verified the stock module's SHA-256 and
kernel ABI, V50 identity, health, charge and thermal guards, existing
dependencies, and unbound device. It loaded exactly one module into `/run`
on the current boot. The module bound successfully, registered
`type_c_port0`, and Alpine health remained clean, but `online` stayed zero.
Receipt: `logs/v50-tcpc-trial-1793035993530146574/`.

Stock `tcpci_late_sync.c` calls `tcpc_device_irq_enable` for registered TCPC
devices. `tools/trial_v50_tcpci_late_sync.py` independently checked its hash,
ABI, boot identity, dependency state and battery guard before loading it once
into RAM. The kernel logged `tcpc irq enable OK!`; Alpine stayed healthy, but
`online` still read zero 12 seconds later. Receipt:
`logs/v50-tcpci-late-sync-1793036063881947249/`.

Both modules are RAM-only on this boot. No boot partition or Alpine startup
file changed. They may be needed for complete charging support, but neither
established that a power source is physically connected. Do not infer charger
hardware failure from `online=0` yet. Next: observe the same supply with a
known-good wall charger connected. If attach appears, verify positive charge
trend before making the module sequence persistent. If it does not, inspect
the remaining stock Type-C/charging dependencies and VBUS ADC read-only.

The next stock `mtk_chg_type_det.ko` source registers a notifier on
`type_c_port0` and forwards Type-C plug events to the charger supply. Its
`mtk_ctd` platform device was present and unbound. A third guarded RAM-only
trial loaded the matching module after TCPC and late-sync. It bound and logged
`bc12_sel = 0`, but no plug event had occurred yet and `online` remained zero.
Alpine health passed at 27% battery. Receipt:
`logs/v50-chg-type-det-1793036475594836645/`. No persistence or boot image
change was made. A single unplug/replug or known-good wall charger attachment
is the next controlled input; stop adding modules until that event is seen.
