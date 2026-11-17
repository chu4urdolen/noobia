# V50 touchscreen status trial and audio boundary

On V50 boot `2f55a194-dfd7-4664-b4cb-9d2275cc947c`, the matching stock
touchscreen stack registered `/dev/input/event0` as `touchpanel`. The new
double-buffered DRM status renderer started at 91%, matching the live gauge.
No later battery transition occurred during observation, so redraw on a
changing percentage still needs a separate check. No CMDQ errors were logged
for this trial. Noob confirmed that the panel darkened after ten seconds and
that touch lit it again. The executable and source are preserved under
`tools/lynx_drm_dmabuf_pattern.c` and in the stage receipt
`logs/v50-ui-stage-1793092958238973423/result.json`.

The modules were loaded only in RAM. An audio module experiment subsequently
rebooted the phone. Pstore from the next boot is preserved at
`logs/v50-audio-reboot-pstore-1793093632878559895/`. The kernel fault was a
NULL pointer dereference in `nvmem_device_read`, called from
`mt6338_codec_probe` during a deferred sound-card probe. Earlier logs reported
`-517` for the headphone calibration IIO channel and efuse. Audio was never
played and no sound card was registered. Do not load this sound stack again
until the probe path is fixed and reviewed.

V50 rebooted successfully as `36c2f8a9-7def-40d3-82ef-38fc1d4b102c`.
Pinned rescue SSH, Alpine SSH, Wi-Fi at `192.168.100.107`, all eight core
services, and ext4 health returned. Display/touch modules were gone after
reboot as expected. The black panel on this boot does not mean Alpine failed.

`tools/stage_v51_display_service.py` staged the 16 verified display/touch
modules, the renderer, and an OpenRC service on Alpine, without loading any
module or enabling the service. The service checks the complete `boot_a`
partition hash against the exact V51 candidate before display initialization.
On current V50, `--check-files` passed and `--status` refused with
`boot_a is not the exact V51 trial image`. The live V50 partition hash was
confirmed as `6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
The service remains disabled. A watched V51 boot, manual service start, and
then a second boot with the service enabled are still required to prove
automatic screen startup. Keep the exact V50 rollback image and procedure.
