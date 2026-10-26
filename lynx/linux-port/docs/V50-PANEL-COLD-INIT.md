# V50 cold panel initialization candidate

The stock Nord 3 panel source at OnePlus kernel commit
`81ec42ad5e803be0cba619f9f7bb298db7d33d7b` sets both
`ctx->prepared=true` and `ctx->enabled=true` in `lcm_probe`. `lcm_prepare`
returns immediately when `prepared` is true. The first V50 UI modeset stayed
black and timed out waiting for CMDQ event 644; its trace contained no
successful panel preparation before the timeout. ESD recovery then
unprepared, reset, initialized, and prepared the panel. The later V50
color-bar and UI modesets both worked on the same boot and logged normal
panel preparation. This supports a bootloader handoff state mismatch. A
clean-boot trial has now shown that changing the panel flags alone is
insufficient.

`tools/build_v50_panel_cold_init.py` starts from the exact August stock panel
module SHA-256
`498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98`.
At `.text+0x121c` / file offset `0x221c`, `lcm_probe` uses `mov w8,#257`
followed by `strh w8,[x19,#144]`, initializing the adjacent `prepared` and
`enabled` flags to one. The candidate changes only the immediate to zero,
so both flags start false and the stock prepare path should run on the first
DRM modeset. Candidate SHA-256:
`364611c2bd63342f80da331d33e995aae3082fcd6ee5e453fb5137b8cc2d7c35`.
It is under `artifacts/panel-cold-init-v50-offline/` with a manifest.

Validation pinned the source commit, original module hash, kernel ABI,
symbol layout, paired flag store, and absence of relocation at the changed
instruction. The candidate differs at exactly two bytes within one AArch64
instruction; its symbols, relocations, dependency metadata, and vermagic
are unchanged. The ELF build-id remains stock, so use SHA-256 for identity.
No boot or recovery partition contains this candidate.

`tools/lynx_v47_display_bootstrap.py --target v50 --panel-candidate --apply`
can load it once into `/run` on a fresh V50 boot in place of the stock panel
module, after normal device, battery, thermal, and charger checks. The
candidate must not be tried on a boot where the stock panel module already
probed. If it causes trouble, reboot to clear all RAM-loaded display modules;
the V50 boot image, Alpine root, and charging service remain stock/unchanged.

One guarded V50 reboot was requested with
`tools/reboot_v50_panel_cold_trial.py`; receipt:
`logs/v50-panel-cold-reboot-1793053423592804755/result.json`. Observer:
`logs/v50-first-boot-1793053420966341270/events.jsonl`.
On fresh boot `2f55a194-dfd7-4664-b4cb-9d2275cc947c`, the candidate loaded
from RAM and registered the DRM card. The first eight-second UI commit returned
success to userspace, but the display remained dark, CMDQ event 644 timed out,
and ESD recovery performed the first successful `lcm_panel_poweron`,
`lcm_panel_reset`, and `lcm_prepare`. The trial restored brightness to zero,
left Alpine and SSH healthy, and wrote no boot partition. Receipts:
`logs/v50-display-bootstrap-1793053706942914202/result.json` and
`logs/v50-dmabuf-trial-1793053739045228442/result.json`. Do not install this
panel candidate as a permanent fix.

The matching `mtk_dsi.c` reveals a second bootloader handoff assumption.
`mtk_dsi_probe` sets `dsi->output_en=true` and `clk_refcnt=1` for DSI0 after
enabling PHY and clocks. `mtk_output_dsi_enable` returns immediately when
`output_en` is already true, skipping `mtk_preconfig_dsi_enable` and
`drm_panel_prepare`. Setting `output_en` false in isolation would leave the
clock reference at one, causing `mtk_dsi_poweron` to return early before its
panel power-on callback. Any fix must account for both the output state and
clock/panel power sequence. This is a source-based diagnosis, not a verified
hardware fix.
