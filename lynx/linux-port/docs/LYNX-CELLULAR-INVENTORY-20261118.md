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
