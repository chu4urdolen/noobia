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
daemon as a modem-start candidate; the `boot` sysfs attribute's behavior
needs source review. Do not execute the daemon, write that attribute, or open
CCCI character nodes as an exploratory status check. The safe next work is to
map their protocol and recovery path offline before a guarded modem startup
trial.

## 2026-11-21 V53 readiness follow-up

On current V53 Alpine boot `0fe847d2-44d6-4ac1-9000-2c99df1a51d8`, a
read-only check found `/sys/kernel/ccci/boot` reporting
`md1:0 | md2:n/a | md3:n/a | md4:n/a | md5:n/a`. The same-boot kernel log
still reported `md_state = 0` for `ccci_0_200`. Bootloader CCCI metadata
still reported `LK load MD success!` and one enabled modem. CCCI modules and
53 CCCI-named device nodes exist, but no cellular OpenRC service was running.
SIM hot-plug platform nodes were present and unbound. Lynx health, Wi-Fi, and
ext4 remained clear at 100% capacity. No CCCI character node was opened, no
modem-start control was written, no radio action was requested, and no SIM
was installed.

The [matching OnePlus MT6983 source state enum](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/misc/mediatek/include/mt-plat/mtk_ccci_common.h#L442)
labels 0 `INVALID`, 1 `GATED`, and 4 `READY`. This is a source-based
interpretation of the live numeric value, not proof that every byte of the
running module matches that public source. The live value does not report a
ready modem.

The same source places modem start behind
[CCCI ioctl handling](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/misc/mediatek/eccci/fsm/ccci_fsm_ioctl.c#L454):
`CCCI_IOC_SEND_START_MD_REQUEST` sends a start request, while
`CCCI_IOC_DO_START_MD` queues actual startup only for a process named
`ccci_mdinit`. The [sysfs `boot` write path](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/misc/mediatek/ccci_util/ccci_util_lib_sys.c#L141)
returns the write count even if its callback fails; the
[matching callback](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/misc/mediatek/eccci/ccci_modem.c#L981)
returns `-EACCES`. Thus a successful shell write would not itself prove modem
startup. **Do not write this attribute as a probe.**

The stock `ccci_mdinit` executable is an Android 31 AArch64 ELF with
`/system/bin/linker64` and Android libraries including `libnvram.so` and
`libccci_util.so`. Its strings reference `/dev/ccci_md1_sta`,
`/dev/ccci_ioctl0`, modem startup, and runtime-data exchange. This binary is
not an Alpine service as-is. The exact userspace sequence, modem firmware
dependencies, controlled stop path, and failure recovery need a bounded
offline design before any live start. Keep the SIM out until a specific
attended test is ready; first prove modem readiness without a SIM.

The installed read-only `lynx_cellular_status` agent tool now exposes
`md1_state_code` alongside CCCI node count. It still reports
`validated=false` and does not open a CCCI device. Four offline fixture tests
passed; the live tool returned code 0 on this boot, and same-boot health
remained clear after its guarded update.
