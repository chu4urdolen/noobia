# Lynx cellular inventory, 2026-11-18

Noob confirmed that Lynx currently has no SIM installed. This is a read-only
inventory on V53 Alpine boot `6613079f-ae1f-4e05-8123-0988b423d6da` at
28% battery with positive charging current. `lynx-status --assert-ready`
reported no issues. No modem command channel was opened, no radio was
activated, and no SIM was inserted.
Receipt: `lynx/logs/cellular-inventory-1795013611358468923/result.json`.

- Loaded modules include `ccci_md_all`, `ccci_auxadc`, `ccci_util_lib`, and
  `mddp`.
- `/dev` contains CCCI control, status, RPC, IMS, and data device names,
  including `ccci_md1_sta` and `ccci_ioctl0` through `ccci_ioctl4`.
- The platform tree has `MD1_SIM1_HOT_PLUG_EINT`,
  `MD1_SIM2_HOT_PLUG_EINT`, and `odm:oplus_sim_detect` device nodes. No
  `driver` link was observed under those three nodes on this boot.
- No cellular OpenRC service appeared in `rc-status -a`.

These are kernel and device-node inventory findings. They do not establish
that modem firmware booted, that either SIM slot works, or that cellular
registration is safe or available. Do not infer SIM presence or a usable
radio from the CCCI device names.

## Offline stock references

Dushich's bounded offline inventory found an `md1img` partition entry in
`linux-port/artifacts/stock-cph2493-August-eu-ota/payload-partitions.json`
(80,928,768 bytes; SHA-256
`7cf648e726d4ef57e9e82eb918c113156c73f0f4118f1011973c022af10c2fa7`).
The stock kernel configuration in the same artifact directory enables
`CONFIG_MTK_CCCI_DEVICES`, sets `CONFIG_MTK_MD1_SUPPORT`, and builds
`CONFIG_MTK_ECCCI_DRIVER` and `CONFIG_SIM_DETECT` as modules. Those are stock
image and build facts, not evidence of a live modem on Alpine.

The local [OnePlus Nord 3 manual](../../downloads/OnePlus_Nord_3_5G_User_Manual_EN.pdf)
specifies an original Nano-SIM and a tray ejector procedure. It refers to a
second SIM but does not identify the tray position that maps to SIM1. The
physical slot mapping and Alpine hot-plug behavior therefore remain unknown.

Before asking Noob to insert a SIM, establish whether the modem firmware has
booted on Alpine, identify required userspace, determine the physical slot
mapping and hot-plug path, and design a bounded status-only probe that cannot
silently enable RF. Choose a recovery path and record battery, thermal,
Wi-Fi, and SSH health before any modem trial. The SIM stays out until that
preparation supports a specific test.

## Live V53 metadata check after repeater recovery

After Noob restarted the Noobia repeater, Nexus reconnected and pinned Alpine
SSH answered on the same boot ID as the Bluetooth trial. At 19:46 UTC Lynx
reported 98% battery, 27.5°C, and no health issues. Aria staged Dushich's
`lynx_cellular_inventory.py` in `/run`, checked its SHA-256, ran it once, and
removed the RAM copy. The result again found loaded CCCI modules, CCCI
character nodes, and the three SIM platform names. No CCCI character node was
opened, no RF action was requested, and post-check health passed on the same
boot. Receipt: `lynx/logs/cellular-tool-v53-1795031287939552537/result.json`.

A bounded live kernel-log read at 19:51 UTC showed `mddp_rx` repeatedly
reporting `port ccci_0_200 read data fail when md_state = 0`, about once per
second. Five raw lines are saved in that receipt directory as
`modem-kmsg.txt`. The saved early V53 boot stream also contains
`mddpw_drv_get_mddp_feature before MD ready!`. These observations do not prove
modem firmware boot or a functioning radio; they strengthen the need for a
status-only modem readiness investigation before inserting a SIM.

## Bootloader and userspace boundary

On the same V53 boot, read-only CCCI sysfs attributes reported
`LK Load MD:[Enabled]`, `LK load MD success!`, one modem configured, and
`md_en=E-D-D-D-D (1->5)`. The raw read is saved beside the inventory as
`modem-sysfs.txt`. This is evidence that the bootloader loaded modem material,
but does not establish that the modem reached its running state under Alpine.
The repeated `md_state = 0` read failure and earlier `before MD ready` message
remain unresolved.

The stock `init.cccimdinit.rc` defines a `ccci_mdinit` service, and strings in
the matching stock `/vendor/bin/ccci_mdinit` include `trigger modem to run!`,
`modem boot up`, and `/sys/kernel/ccci/boot`. That supports treating this
daemon and the writable `boot` sysfs attribute as modem-start controls. Do
not execute the daemon, write that attribute, or open CCCI character nodes as
an exploratory status check. The safe next work is to map their protocol and
recovery path offline before a guarded modem startup trial.
