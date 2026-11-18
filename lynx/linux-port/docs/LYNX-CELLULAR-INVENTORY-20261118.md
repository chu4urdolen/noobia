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

Before asking Noob to insert a SIM, identify the modem firmware and required
userspace, determine the actual physical slot mapping and insertion procedure,
and design a bounded status-only probe that cannot silently enable RF. Choose
a recovery path and record battery, thermal, Wi-Fi, and SSH health before any
modem trial. The SIM stays out until that preparation supports a specific
test.
