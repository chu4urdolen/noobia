# Lynx V46 charger read-only audit

Lynx was connected to Nexus while boot ID
`f6230cac-8d41-48da-bf28-2700e9ff56f1` ran the verified V46/Alpine
system. A fixed sysfs and `/proc/modules` inventory read no charger
registers and loaded no modules:
`logs/v46-charging-readonly-1792784990883851713/result.json`.
The identified ZY0603 gauge reported 83% capacity, +326 mA current,
27.2°C battery temperature, and 8346 mV pack voltage. Earlier readings
on the same connected boot were lower, so capacity was rising. The only
power-supply class entry still reported `online=0` and `Not charging`.
`mt6375_charger` and `charger_class` were loaded; `tcpc_mt6375`,
`mt6375_battery`, and `oplus_chg` were absent.

A second fixed read-only capture of the *live* device tree is
`logs/v46-charger-dt-1792785064671211449/result.json`. The MT6375
charger node includes these settings:

| Property | Device-tree value |
| --- | ---: |
| `chg_tmr` | 10 hours |
| `chg_tmr_en` | present / true |
| `te_en` | present / true |
| `cv` | 4200 mV |
| `ichg` | 2000 mA |
| `ieoc` | 150 mA |
| `aicr` | 500 mA |
| `vbus_ov` | 14500 mV |

The cached OnePlus MT6983 kernel source shows the MT6375 driver reading
these device-tree properties and applying them during probe. Its default
platform data comments identify `chg_tmr` as hours, and the field table
maps `chg_tmr_en` and `te_en` to charger-control bits. See
`linux-port/sources/oneplus-mt6983-kernel-13.1/drivers/power/supply/mt6375-charger.c`
near `mt6375_chg_dtprops`, `mt6375_chg_get_pdata`, and
`mt6375_chg_init_setting`. This source is from the matching model and
Android generation; exact binary equivalence to the August stock module
has not been demonstrated.

**The device-tree values are configured intent, not a live register proof.**
The charger driver or bootloader may change settings later, and the missing
OEM/Type-C modules mean the normal Android charging policy is incomplete.
The observed charging and cool battery are useful evidence, but they do not
verify charge termination, thermal derating, or safety-timer operation.
Do not write charger registers or load the missing modules as a diagnostic.
