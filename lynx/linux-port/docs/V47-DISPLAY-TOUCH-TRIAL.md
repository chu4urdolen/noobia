# V47 display and touch investigation — 2026-10-23

## Baseline

V47 boots Alpine 3.24.2 with Wi-Fi and two SSH servers. The rescue `/init`
SHA-256 is `ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae`.
All experiments in this note loaded modules into RAM. No boot image, slot,
firmware partition, or persistent startup configuration was changed.

At baseline `/sys/class/drm` contains only `ttm` and `version`. There is no
`/dev/dri/card0`, framebuffer, or input device. The already loaded
`mediatek_drm` driver logs that `14017000.dsi` waits for a panel driver.

The active device-tree DSI endpoint points to `panel5@0`, compatible with
`oplus22823,tm,nt37705,cmd`. The matching August CPH2493 stock module is
`oplus22823_tm_nt37705_fhd_dsi_cmd.ko` (SHA-256
`498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98`).
The active touch node is SPI6 `synaptics_tcm_hbp@0`, compatible with
`synaptics,tcm-spi-hbp`, chip S3910. The matching candidate is
`synaptics_tcm2.ko`; it has **not** been loaded or tested.

## First panel fault

The panel module alone loaded but created no DRM card. Manually binding the
DSI controller deferred because the panel's MT6373 ADC channel was absent.
Loading stock `mtk-spmi-pmic-adc.ko` allowed a retry, which then deferred on
the MT6373 pinctrl GPIO. A second probe crashed in `regulator_set_voltage`
through `lcm_panel_vrfio18_aif_enable`. The local source caches a
device-managed regulator pointer in a static variable across failed probes;
this may explain the stale pointer. The raw retained trace is in
`logs/v47-display-reboot-evidence-1792788455606294814/`.

Lynx automatically rebooted to the exact V47 image and both SSH services
returned. We subsequently loaded the matching MT6373 pinctrl, MT6373 ADC,
and IOMMU supplier modules in RAM on the fresh boot; each completed and
health checks passed. Their receipts are
`logs/v47-display-supplier-pinctrl-mt6373-1792788718962620524/`,
`logs/v47-display-supplier-mtk-spmi-pmic-adc-1792788724981303650/`, and
`logs/v47-display-supplier-mtk_iommu-1792788734083283404/`.

## Second panel fault

With those three suppliers bound, the stock panel module loaded. A single
manual DSI bind then caused another kernel fault. The pstore trace identifies
the actual caller this time:

`mtk_drm_bind → mtk_drm_crtc_first_enable → mtk_dsi_io_cmd →
mtk_drm_set_mmclk → regulator_set_voltage`.

The regulator argument was `ERR_PTR(-517)`, meaning `-EPROBE_DEFER` was
passed to `regulator_set_voltage`. The OnePlus source for
`mtk_drm_mmdvfs_init()` gets the `dvfsrc-vcore` supply without checking the
return value; the subsequent clock setup uses it unconditionally. The live
`1c00f000.dvfsrc` device had no driver. Matching stock modules
`mtk-dvfsrc.ko` and `mtk-dvfsrc-regulator.ko` exist but were not loaded.
This is the next missing supplier, and a kernel driver error turns its normal
deferred-probe signal into a crash. The exact retained trace and test receipt
are in `logs/v47-display-reboot-capture-*/` and
`logs/v47-panel-after-suppliers-1792788786395742332/`.

V47 recovered on boot ID `4ac1739d-ccad-46d8-9de6-5ff622d8d67d`;
both SSH services and all eight Alpine services returned. Battery was 82%,
25.8°C, and ext4 reported zero errors. No DRM card, test image, or touch
coordinate is verified yet.

## Safe continuation

The live DT `dispsys_config@14000000/dvfsrc-vcore-supply` phandle is `0x4b`;
it resolves to `dvfsrc@1c00f000/dvfsrc-vcore`. The stock
`mtk-dvfsrc.ko` depends on the already loaded `mtk_scpsys`, and
`mtk-dvfsrc-regulator.ko` depends on `mtk_dvfsrc`. Both were loaded in RAM
on the recovered boot, separately. The DVFSRC device bound, the
`dvfsrc-vcore` regulator appeared, and all eight services and SSH remained
healthy. Receipts are `logs/v47-dvfsrc-supplier-mtk-dvfsrc-1792789100330635371/`
and `logs/v47-dvfsrc-supplier-mtk-dvfsrc-regulator-1792789106871134586/`.

Confirm all display suppliers and health before another panel probe. Do not
repeat a panel probe on a boot where it has already deferred: the panel
driver's static regulator cache may retain stale device-managed pointers.
Keep the V47 and V46 boot images and exact restoration instructions intact.

The RAM-only trial and capture tools are `tools/trial_v47_runtime_panel.py`,
`tools/trial_v47_bind_panel.py`, `tools/trial_v47_runtime_panel_adc.py`,
`tools/trial_v47_display_supplier.py`,
`tools/trial_v47_panel_after_suppliers.py`, and
`tools/capture_v47_display_reboot.py`, and
`tools/trial_v47_dvfsrc_supplier.py`. They contain pinned hashes and boot
IDs; **do not rerun them on a different boot without review**.

## Third panel fault after DVFSRC registration

On boot ID `4ac1739d-ccad-46d8-9de6-5ff622d8d67d`, all five identified
suppliers (MT6373 pinctrl, MT6373 ADC, IOMMU, DVFSRC and its regulator)
loaded separately and passed health checks. A single panel load completed;
the subsequent DSI bind caused a different kernel fault. The retained
trace at uptime 341 points to a NULL dereference in interrupt context in
`cmdq_flush_async_cb` of `mtk_cmdq_drv_ext`, reached from
`cmdq_thread_irq_handler`. The previous `dvfsrc-vcore` fault did not recur,
so registration changed the execution path, but no DRM card was verified.
The retained bytes are in `logs/v47-display-reboot-capture-1792789185210552992/`;
the trial receipt is `logs/v47-panel-after-suppliers-1792789153546757880/`.

Lynx rebooted automatically to V47 on boot ID
`00841cdb-6658-44d6-9f47-4770b047cad5`; rescue and Alpine SSH returned,
all eight services passed, and ext4 reported zero errors.

Source review of `mtk-cmdq-helper-ext.c` found that its callback table is
populated by `cmdq_util_set_fp`. The matching
`cmdq-platform-mt6983.ko` calls this in its module init; it was absent on
Lynx during the third fault. This identifies a plausible cause of the NULL
callback. The module loaded in RAM on the new boot with healthy services:
`logs/v47-cmdq-platform-1792789467245564860/`.

## First successful DRM registration

On boot `00841cdb-6658-44d6-9f47-4770b047cad5`, the CMDQ platform and
all five suppliers loaded separately in RAM. The same exact stock panel
module then bound successfully on the **first** DSI bind of that boot.
`/dev/dri/card0` appeared, and `card0-DSI-1` reported connected with
1240×2772 modes at 60, 90, and 120 Hz. All eight Alpine services, Wi-Fi,
both SSH paths, battery reporting, and ext4 health remained good. Receipts:
`logs/v47-panel-after-suppliers-1792789510304574129/` and read-only
`logs/v47-drm-query-1792789567959776316/`.

The connector's DPMS state was Off and no CRTC framebuffer was active. A
bounded 60 Hz `modetest` SMPTE pattern attempt opened the DRM card but
reported `failed to create dumb buffer: Out of memory`; it did **not**
render a verified image. The full trial is
`logs/v47-drm-pattern-1792789599469951501/`. The matching source uses
`dma_alloc_attrs` against an overlay DMA device for dumb buffers. A later
read-only memory sample showed about 15 GiB MemAvailable and 641 MiB CMA
free, so global RAM exhaustion is not established. DMA mapping or driver
allocation needs diagnosis before another draw attempt.

The phone remained on this same boot for at least 12 hours 40 minutes.
At that point Alpine and all eight services still passed, ext4 had zero
errors, battery was 26% and 26°C, and the hottest reported thermal sensor
was 33°C. Live display experiments were stopped to conserve charge.
An identity-checked OpenRC poweroff was then requested using
`tools/lynx_poweroff.py`; SSH and ping disappeared. Receipt:
`logs/lynx-poweroff-1792834943387190230/result.json`.
**Panel binding and card registration are proven only for this RAM-loaded
session; automatic display startup is not configured. Touch remains untested.**

## 2026-10-24 DMA-BUF draw and touch registration

On boot `c72ff027-0ff6-46ef-9191-df3bd26ce8ec`, the guarded RAM-only
display bootstrap bound the matching panel and registered `/dev/dri/card0`.
The native `tools/lynx_drm_dmabuf_pattern.c` allocated 13,750,272 bytes from
`/dev/dma_heap/system`, imported the DMA-BUF through DRM PRIME, and created
framebuffer 112. This bypassed the driver's failing dumb-buffer allocation.
Its first `--show 8` caused a kernel NULL dereference at address `0x8` in
`mml_topology_create+0x178/0x220`; pstore is in
`logs/v47-display-reboot-capture-1792841381513253192/`. Lynx rebooted
automatically, then rescue and Alpine SSH and all eight services recovered.

The exact August stock `mtk-mml-mt6983.ko` was absent in that trial. Its
`tp_ops_mt6983` and `mml_topology_register_ip` symbols explain the NULL
topology pointer. Its SHA-256 is
`473c429e8b71aded1fe2f6f9128210e7fdd62df32f1d9cae234a92ac818578a5`.
`tools/lynx_v47_display_bootstrap.py` now verifies and loads it before
binding the DSI device. The new boot
`897cad51-2ae4-479a-98bc-9ab8a052b9a9` passed that bootstrap and a
single three-second DMA-BUF `drmModeSetCrtc` trial returned exit 0. Receipt:
`logs/v47-dmabuf-trial-1792841692650566029/`. **This does not prove pixels
appeared.** Kernel dmesg recorded a display CMDQ timeout, no valid trigger
loop, and a later `mm_infra` power-off timeout. The phone remained on the
same boot, with SSH, all eight services, and ext4 health intact. The charger
state was not checked during this trial; later it reported `online=0`.
Do not repeat the modeset until the CMDQ timeout is explained. A physical
screen observation was requested but has not yet been received.

Touch was investigated separately on the same boot. The enabled SPI6 node is
`synaptics,tcm-spi-hbp`; the legacy `synaptics-s3910` node is disabled. Exact
stock `spi-mt65xx`, `olc`, `oplus_bsp_fw_update`, `oplus_bsp_tp_custom`, and
`synaptics_tcm2` modules were loaded into RAM, each followed by Alpine health
checks. The first Synaptics init declined registration with
`tp_judge_ic_match fail` because `oplus_bsp_tp_custom.dsi_display0` was empty.
The matching panel string was already in `/proc/cmdline` but was not passed
to the late-loaded module by `insmod`. Setting that parameter and retrying
Synaptics once registered `touchpanel` as `/dev/input/event0`. The driver
detected application firmware build 4079330 (`S3910PA0B0-15.2`) and
registered an interrupt handler. No firmware update command was issued.
Receipts: `logs/v47-touch-bootstrap-1792841832300370742/` and
`logs/v47-touch-match-1792841912592214403/`. Input event coordinates and
physical response are still unverified. The reproducible touch bootstrap now
passes the exact existing panel match string when loading the helper.

These display and touch modules are **RAM-only**. A fresh V47 boot returns to
the original Alpine system, and V47/V46 boot images and stock restoration
remain unchanged. The reusable tools are `tools/lynx_v47_display_bootstrap.py`,
`tools/trial_v47_dmabuf.py`, `tools/lynx_v47_touch_bootstrap.py`, and the
same-boot correction `tools/lynx_v47_touch_match.py`.
`tools/lynx_touch_events.c` is a bounded read-only event decoder. It compiled
natively in Lynx's isolated development root and can report coordinates from
`/dev/input/event0` when someone taps the glass. The driver reports
`ABS_MT_POSITION_X` 0–12399 and `ABS_MT_POSITION_Y` 0–27719, ten times the
panel's pixel dimensions. A 20-second capture without a confirmed physical
tap saw zero events; that does not test touch response.

## CMDQ timeout diagnosis and corrected battery guard

The retained CMDQ dump shows the trigger-loop thread stopped on its first
`EVENT_STREAM_BLOCK` wait. The event-loop thread was also stopped at its
first instruction, a nonblocking event clear. Multiple configuration
threads timed out. The DRM driver's `No valid trigger loop` message appeared
later, after the panel had begun unpreparing, so that phrase is a consequence
of shutdown, not proof that the loop never existed.

The matching stock `modules.load` also includes `tinysys-scmi.ko` followed
by `mtk-mminfra-debug.ko`; neither was loaded during the draw trial. The
OnePlus kernel source for `mtk-mminfra-debug` registers the multimedia
power-domain notifier. With this phone's `mminfra-bkrs=1` and `init-clk-on`
device-tree settings, that notifier enables the multimedia clocks and
initializes the GCE RFIFO. This is a plausible cause of the nonadvancing
CMDQ threads, not yet a verified fix. The guarded display bootstrap now
includes both exact stock modules before the panel binds. Do not rerun it
on the already-probed boot.

At a later read-only check the battery had fallen to 38% and the MT6375
charger reported `online=0`, `Not charging`, despite a positive signed
gauge-current sample. The positive sample alone therefore did **not** prove
charging. The first guard correction required `online=1`, but source review
then showed that V47 itself powers off whenever a charger reports online.
The display and touch trial tools now require `online=0`, at least 50%
battery, and their temperature limits. An identity-checked orderly poweroff
was requested; receipt
`logs/lynx-poweroff-1792853724641835014/`. No additional display trial was
run. Noob reported a cable-triggered restart and removed the cable; the
follow-up seven-minute watcher saw no Alpine or SSH return. Network absence
supports shutdown but is not physical proof.

## 2026-10-25 V48 follow-up: MMInfra HRE restore BUG

The V48 guarded RAM-only bootstrap loaded `tinysys-scmi.ko` and
`mtk-mminfra-debug.ko` before panel binding. DRM registered the connected
1240×2772 DSI connector, and the DMA-BUF program imported a framebuffer.
The first three-second modeset rebooted Lynx. Host receipts and pstore:
`logs/v48-display-bootstrap-1792959952071736454/` and
`logs/v48-dmabuf-trial-1792960004528604050/`.

The new pstore call trace reaches `mtk_mminfra_pd_callback+0x204/0x260`
through `cmdq_mbox_enable`, during `mtk_dsi_encoder_disable`. The matching
OnePlus source at `drivers/misc/mediatek/mminfra/mtk-mminfra-debug.c:215`
contains an unconditional `BUG_ON(1)` when the HRE restore register at
`0x1e800280` differs from `0xfff`. The source calls
`scmi_tinysys_common_set` for MMInfra restore immediately before this
check, but the captured pstore does not show the SCMI return or register
value. We cannot yet distinguish an unavailable SCMI provider, a failed
restore, or another missing initialization step. The stock `modules.load`
puts these suppliers late (lines 186–187), after several display modules;
loading both in our bootstrap was therefore necessary to test, but did not
make modeset safe.

Lynx recovered through BusyBox and automatic Alpine handoff on boot
`89ee3cfd-fb7c-4c66-94ec-7ae1a12d6f73`, with eight services healthy and
no ext4 errors. No boot partition was written. Hold further modesets until
SCMI provider binding and HRE restore diagnostics can be checked without a
display commit. The trial tool now starts a pinned SSH `/dev/kmsg` stream to
a host-side file before modeset, so the next permitted experiment can retain
messages that pstore may omit. This capture path passed Python syntax and
device-node preflight; it has not been used for another display modeset.
