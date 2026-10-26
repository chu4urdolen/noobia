# V51 DSI cold-boot candidate — offline, unflashed

The matching Nord 3 kernel source at commit
`81ec42ad5e803be0cba619f9f7bb298db7d33d7b` assumes DSI0 was
already active in Little Kernel. `mtk_dsi_probe` takes an extra runtime-PM
reference, powers the PHY and clocks, and sets `output_en=true` with
`clk_refcnt=1`. Our native Linux boot often reaches this driver with the
panel dark. On its first userspace modeset, `mtk_output_dsi_enable` sees
`output_en` and returns before `mtk_preconfig_dsi_enable`, panel power-on,
and `drm_panel_prepare`. The first V50 modeset timed out waiting for CMDQ
event 644; ESD recovery then performed the missing panel preparation. A
second modeset on the same boot displayed color bars and the status screen.
See `V50-PANEL-COLD-INIT.md` and `V50-DISPLAY-UI.md`.

`tools/build_v51_dsi_cold_init_module.py` starts from the exact August
CPH2493 stock `mediatek-drm.ko` (SHA-256
`2096fbf733dd314d584e1a93e8ccef42888cb99fc149a58c05b12c709dc3926c`).
It changes three AArch64 instructions in `mtk_dsi_probe`:

1. Skip the probe-time runtime-PM get associated with the LK handoff.
2. Skip the probe-time PHY/clock enable sequence.
3. Initialize `output_en` and `clk_refcnt` to zero.

The intended result is that the first real modeset runs the driver's normal
`mtk_dsi_poweron` path, including panel power-on, PHY/clock enable, DSI
preconfiguration, and `drm_panel_prepare`. This is a source-based hypothesis;
it has **not** been tested on hardware. The module builder pins source commit,
stock module SHA, function location, instruction bytes, kernel ABI, and ELF
symbols/relocations. The resulting branch targets were checked separately
with `llvm-objdump`. Candidate SHA-256:
`d7d522ee81fcc41fe4e4f86f34857475ec3d3ae170b37184ff6420420f822dd8`.
The ELF build ID remains stock, so use the SHA-256 for identity.

`tools/build_v51_dsi_cold_boot_image.py` adds only this candidate as
`lib/modules/mediatek-drm.ko` to the V50 rescue supplement. The existing
module load list is unchanged. V50 `/init` extracts the supplement with
`cpio -idmu` before loading the radio/display module list, so the new member
is expected to override the stock module in RAM. The image rebuild changes
only the supplement, the primary ramdisk's supplement size/hash fields, and
the boot header's ramdisk length. Its kernel, command line, other archive
members, and image tail passed roundtrip checks. The original vendor boot,
recovery partitions, slot B, and Alpine persistent root are untouched.

Offline V51 image:
`artifacts/dsi-no-lk-v51-image-offline/nord3-dsi-no-lk-v51-untested.img`
SHA-256 `338f1280cbdc68e8896ff6b5ebb37fd79d0497280159ac35c962dd311f98847c`.
The exact working V50 rollback image is
`artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img`
SHA-256 `6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.

No V51 flash or fresh-boot display trial has occurred. Keep the current V50
status screen running until Noob is ready to watch a boot trial. Before any
flash, run `python3 tools/lynx_boot_a_v51_trial.py --prepare` to verify the
exact V50 restoration command, and start a rescue/Alpine observer. The offline
prepare check passed. If V51 fails to reach pinned rescue SSH, stop and
restore V50 via Fastboot; do not alter other partitions.
