# Lynx USB MTU3 boot loading — system analysis

- **Author:** Dushich, 2026-11-21 (queue #294 item 2, per Gwyn's #282 task).
- **Method:** offline from repo + stock artifacts; Lynx reads were single named
  reads only (boot `447eee99`), nothing recursive, no reproduction.
- **Status:** analysis only. Nothing staged, loaded, or installed on Lynx.
  This document proposes packet changes for Banshee/Aria; it does not install.

## 1. Evidence

### 1.1 Stock module artifacts (offline, repo)

`lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/`:

| Module | SHA-256 |
| --- | --- |
| `mtu3.ko` | `d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467` |
| `xhci-mtk-hcd.ko` | `5a871883c90b63b9fb2b218f0e1b87baf1e65abada8472ee38062316292febbb` |

- **Zero module dependencies.** `modules.dep` lines are bare
  (`/lib/modules/mtu3.ko:` and `/lib/modules/xhci-mtk-hcd.ko:` — nothing after
  the colon); no `modules.softdep` entries for either. `usb_boost.ko` depends
  on `mtu3.ko`, not the reverse. So a plain `insmod` by absolute path is
  complete — no `depmod`, no dependency chain.
- **No firmware files needed.** Neither `.ko` contains `request_firmware` or
  `.bin` references (string audit). Nothing to stage beside the modules.
- **OF aliases match the live DT.** `alias of:N*T*Cmediatek,mtu3 → mtu3`
  (DT node compatible is `mediatek,mtu3 mediatek,mt6983-mtu3`);
  `alias of:N*T*Cmediatek,mtk-xhci → xhci_mtk_hcd` (child
  `xhci0@11200000` compatible `mediatek,mtk-xhci`).
- **Stock load order is mtu3-first:** `modules.load` line 85 `mtu3.ko`,
  line 86 `xhci-mtk-hcd.ko`.
- **No USB-PHY driver module in the stock ramdisk** (no `usb-phy` alias;
  only `phy-mtk-ufs.ko`, `phy-mtk-xsphy.ko`, `usb_dp_selector.ko`,
  `extcon-mtk-usb.ko`). Whether the USB PHY driver is built into this kernel,
  or whether `mtu3` probe needs one at all, is unproven (see §3.3).

### 1.2 Lynx live (boot 447eee99, read-only)

- Kernel: `5.10.149-android12-9-o-g311738fbb5a8` (stock August, unchanged).
- **USB0 controller platform device exists and is unbound:**
  `/sys/devices/platform/soc/11201000.usb0`. (Not under
  `/sys/devices/platform/` or `/sys/devices/soc/` directly — those checks
  miss it.) No `mtu3`/`xhci` driver bound; the only USB-ish platform drivers
  present are the generic `xhci-hcd` and `mtk-xsphy`/`ufs_mtk_phy` (non-USB).
- **DT:** `soc/usb0@11201000` present with `usb-role-switch`, `dr_mode`,
  `mediatek,clk-mgr`, `phys`/`phy-cells`; child `xhci0@11200000`.
- **UDC:** `/sys/class/udc/` contains only `dummy_udc.0`.
- **USB PHY nodes unbound:** `11e43000.usb-phy0`, `soc:usb-phy1@11e30000`
  have no bound driver.
- **`/lib/modules/` is empty** — no modules staged on the phone at all;
  `mtu3`/`xhci_mtk_hcd` not in `/proc/modules`.
- **configfs:** in `/proc/filesystems`, and mounted at `/sys/kernel/config`.
- Dirs: `/etc/lynx` present (B37b disable switch path is OK);
  `/etc/noobia` **absent** (QT-1 disable switch would need
  `mkdir -p /etc/noobia` first — noted in my QT-1 review #315).
- Neither `lynx-usb-gadget` nor `noobia-quiet-trace` initd installed.

### 1.3 Earlier hardware evidence (repo, not new reads)

- **Attended milestone (Banshee #58, confirmed by Noob/Aria):** MT6983 mtu3
  peripheral mode enumerated on Nexus as `1d6b:0104 Lynx Nord 3`,
  `/dev/ttyACM0`, bidirectional serial with Lynx `/dev/ttyGS0`. The boot
  packet's job is to reproduce this **without** an attended session.
- **XHCI-LOAD-ORDER-FIX.md:** stock `mtu3` host-init stores the xHCI child's
  device-driver pointer **without a null check** (disassembly
  `stock-mtu3-host-init-disassembly.txt`, 0x54d4..0x54e0); a later role path
  dereferences it. Plausible kernel fault — **not proven** on this hardware.
  The QEMU-validated corrected image loads xHCI **before** MTU3 and
  **withholds MTU3 if xHCI is absent** from sysfs.
- **xHCI hardware trial:** after the corrected image, no USB endpoint and no
  `ttyACM` appeared; "do not declare the xHCI change a hardware fix."

## 2. What loading the stack at boot actually requires

### 2.1 Stage the two modules

Copy both `.ko` (SHA-pinned above) onto the phone, flat, matching the stock
ramdisk convention:

```
/lib/modules/$(uname -r)/mtu3.ko
/lib/modules/$(uname -r)/xhci-mtk-hcd.ko
```

Load by **absolute `insmod` path** — not `modprobe`. The phone has no
`modules.dep` tree to resolve against, and BusyBox `modprobe` semantics here
are unverified. With zero dependencies and no firmware, absolute `insmod` is
the complete and honest mechanism.

### 2.2 Load order and gate

1. `insmod /lib/modules/$(uname -r)/xhci-mtk-hcd.ko` (bounded:
   `busybox timeout -k 2 10 insmod ...`).
2. **Gate:** bounded wait (≤ ~5 s) for evidence xHCI is present
   (`grep -q '^xhci_mtk_hcd' /proc/modules`); if absent, **withhold mtu3**,
   log the honest state, and do not retry (no load storm at boot).
3. Only then `insmod .../mtu3.ko` (bounded, same pattern).

Rationale: stock's own `modules.load` is mtu3-first (85/86) — exactly the
order the disassembly analysis warns about. The corrected candidate image
inverts the order and gates it; we should adopt the same discipline in the
OpenRC service. This is a precaution against a *plausible, unproven* fault
path — say so in the packet, don't sell it as a fix.

### 2.3 Compose, then bind — and verify honestly

- Compose the ACM function under `/sys/kernel/config/usb_gadget/lynx`
  (bounded, idempotent; configfs is already mounted on the phone).
- Bind **only if** `/sys/class/udc/<target>` exists; write the target to
  `UDC` and then **read it back** (`cat .../UDC` non-empty). Directory
  existence of `functions/acm.usb0` proves composition, **not** binding.
- The real success criterion is host-side: Nexus enumerates
  `1d6b:0104 Lynx Nord 3` and `/dev/ttyACM0` appears (the attended
  milestone's evidence).

## 3. Honest not-ready state (why B37b cannot install as written)

1. **No modules on the phone.** `/lib/modules/` is empty; B37b's preflight
   `mtu3_ok` (kernel/drivers/usb/mtu3/ path) is false for this device.
2. **No bind target.** UDC list is `dummy_udc.0` only; nothing to bind to
   until mtu3 probes.
3. **USB PHY unbound / driver unproven.** DT `phys` references USB PHY
   nodes with no bound driver, and the stock ramdisk has no USB-PHY module.
   Whether `mtu3` probe succeeds without a bound USB PHY is unproven. This
   must be observed in the attended trial's kernel log; if a PHY driver is
   required, identify and stage it before claiming readiness.
4. **Binding is not yet proven on this hardware** (xHCI trial: no endpoint).
5. **B37b initd loads mtu3 only** — no xhci, no gate, i.e. the warned order.
6. **B37b verify step 2** (`functions/acm.usb0` exists) is a false-positive
   success for an unbound gadget (my #282 review stands).
7. **B37b preflight** expects module paths that do not exist on this device.

## 4. Proposed packet changes (for Banshee/Aria)

- **P1 — Preflight:** replace with the live facts above (flat module path,
  UDC state, USB0 platform device present-unbound, PHY unbound, configfs
  mounted). Keep it read-only.
- **P2 — Stage step:** SHA-pinned copy of both `.ko` into
  `/lib/modules/$(uname -r)/`, verify SHAs after copy.
- **P3 — Load sequence:** xhci → presence gate → mtu3, all bounded
  (`timeout -k 2 10`), withhold-and-log on gate failure (no retry loop).
- **P4 — Verify:** UDC read-back on Lynx; host-side enumeration
  (`1d6b:0104`, `/dev/ttyACM0`) as the pass criterion. Remove
  `functions/acm.usb0` existence as a success signal.
- **P5 — Two phases.** Phase 1 (offline-safe, reversible): stage modules +
  guarded load sequence + honest state file written each boot
  (`xhci=absent|present mtu3=skipped|loaded udc=absent|<name>`).
  Phase 2 (attended): bind trial with host-side verify. Enable
  auto-bind at boot **only after** a Phase 2 pass.
- **P6 — PHY risk note:** capture the kernel log of the mtu3 probe during
  the trial; if probe fails on PHY, identify the driver before re-trying.
- **P7 — Keep:** disable switch, rollback, `after sshd` ordering (all good
  in B37b; do not regress them).

## 5. Open questions

- Who drives the USB PHY on this kernel, and does `mtu3` require it bound
  (unproven; observe in trial)?
- What `dr_mode` on the DT node implies for the default role at boot
  (unproven; read stock `mtu3` source if it matters).
- UDC name on probe: expected `11201000.usb0` (v53 preflight and the
  attended trial both reference it) — confirm in the trial.
