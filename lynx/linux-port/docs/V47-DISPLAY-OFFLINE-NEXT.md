# Lynx V47 display: offline preparation after orderly poweroff

Lynx is off following the identity-checked OpenRC poweroff receipt
`logs/lynx-poweroff-1792834943387190230/result.json`. Do not reconnect or
wake her solely for these offline checks; the last battery sample was 26%.

## What the completed live trial proved

On boot `00841cdb-6658-44d6-9f47-4770b047cad5`, the matching August stock
modules for CMDQ platform, DVFSRC, DVFSRC regulator, MT6373 pinctrl, MT6373
ADC, IOMMU, and the Tianma NT37705 panel were loaded in RAM in that order.
One DSI bind registered `/dev/dri/card0` and a connected 1240×2772 DSI
connector with 60, 90, and 120 Hz modes. Lynx stayed on Alpine with Wi-Fi,
both SSH paths, eight services, and no recorded ext4 errors for over twelve
hours. The exact receipts and earlier kernel crash traces are in
`V47-DISPLAY-TOUCH-TRIAL.md`.

The 60 Hz `modetest` color-bar command **did not draw**. Its DRM dumb-buffer
allocation returned `ENOMEM`, even though a later sample showed about 15 GiB
MemAvailable and 641 MiB free CMA. The stock driver allocates dumb GEM
buffers with `dma_alloc_attrs` on an overlay device. Its separate PRIME
import path accepts a DMA-BUF scatter-gather table. Thus global RAM
exhaustion is unproved; the failure may be in the overlay DMA allocation or
mapping. A new allocation path needs a controlled test.

## Prepared tools

`tools/lynx_v47_display_bootstrap.py` is a reusable host-side sequencer.
Default mode checks the pinned V47 identity, matching stock module hashes,
kernel ABI, battery, and active panel device-tree compatible without changing
the phone. `--apply` requires at least 45% battery, the MT6375 charger
reporting `online=1` and `Charging` or `Full`, a battery below 30°C,
all reported sensors below 45°C, and a fresh
boot with no panel probe. It loads the exact successful module order in RAM, checks health
after every step, and binds DSI once. It has passed Python syntax and CLI
checks, but **has not been run** on a new hardware boot.

`tools/lynx_drm_dmabuf_pattern.c` is a bounded alternative to the failed
dumb-buffer allocation. It uses the stock system DMA heap, brackets CPU
writes with `DMA_BUF_IOCTL_SYNC`, imports the DMA-BUF through DRM PRIME,
creates an XRGB8888 framebuffer, and can show color bars at 60 Hz for at
most 15 seconds. It provides three explicit modes:

- `--probe`: DRM and connected DSI query only.
- `--allocate`: DMA heap, PRIME import, and framebuffer creation; no modeset.
- `--show 8`: display color bars for eight seconds, then disable the test CRTC.

The C code compiled with `-Wall -Wextra -Werror` against extracted libdrm
headers on Nexus. It has **not been compiled for aarch64 or run on Lynx**.
On Lynx it will need the signed Alpine `libdrm-dev` and `linux-headers`
packages in the native build environment, or an equivalent aarch64 build.
The host header package used for syntax verification is retained under
`tools/build-deps/`; no host package was installed globally.

The kernel's DMA heap and DRM PRIME interfaces support this allocation and
import design, but the driver can still reject the particular buffer. This
is a hypothesis to test, not a working framebuffer claim. References:
[DMA heap userspace API](https://docs.kernel.org/userspace-api/dma-buf-heaps.html),
[DMA-BUF CPU synchronization](https://docs.kernel.org/driver-api/dma-buf.html),
and [DRM PRIME import UAPI](https://www.kernel.org/doc/html/v6.6/gpu/drm-uapi.html).

## Touchscreen preparation

Update 2026-10-24: The trial below was completed. The exact stock stack
registered `/dev/input/event0` after passing the existing command-line panel
match string to `oplus_bsp_tp_custom`. See `V47-DISPLAY-TOUCH-TRIAL.md` for
receipts. Touch coordinates remain unverified. The display DMA-BUF path can
allocate and set a CRTC, but dmesg reports a CMDQ timeout, so visible output
is not yet established. Do not repeat the modeset without diagnosing that
timeout.

The active device-tree node is SPI6 Synaptics S3910. The matching stock
candidate is `synaptics_tcm2.ko`; it was never loaded. SPI controller
`spi-mt65xx.ko` and touch dependencies `olc`, `device_info`,
`oplus_bsp_fw_update`, and `oplus_bsp_tp_custom` were absent in the V47
module snapshot; `mtk_disp_notify` and `oplus_bsp_tp_notify` were present.
The touch module's source connects and powers the controller during probe.
Its startup reflash queue is commented out, but a failed application
firmware setup can switch the touch controller into bootloader mode.
Accordingly, the first touch trial should wait for a charged, healthy boot
and should not be bundled with the next display allocation test.

## Next charged session

1. Power Lynx on and establish V47 rescue and Alpine SSH. Check battery and
   storage health. Keep the V47 and V46 boot images untouched.
2. Run the bootstrap tool in default check mode; inspect its receipt. Use
   `--apply` only if its exact V47 and battery guards pass.
3. Query DRM and compile the DMA-BUF tool on the native aarch64 build root.
   Run `--probe`, then `--allocate`. Capture errors and kernel logs before
   considering `--show`.
4. If import and framebuffer creation pass, attempt one short `--show` trial.
   Verify the CRTC result, SSH, battery, and physical screen separately.
5. Work on SPI touchscreen separately, beginning with read-only DT and
   module dependency checks, then one controlled RAM-only controller probe.

No display modules were made persistent, and no boot partition was changed
in the display investigation. The black screen is expected while Lynx is
off and after any fresh V47 boot until the display stack is loaded again.
