# Lynx camera control query crash, 2026-11-04

On V53, a guarded CAMSV capture completed a raw buffer while Alpine stayed
healthy. A later manual read-only query of the GC02M1 sensor subdevice,
`v4l2-ctl -d /dev/v4l-subdev4 --list-ctrls-menus`, caused a kernel Oops.
The command did not return usable output; SSH and Wi-Fi disappeared, and
Lynx was next observed in USB Fastboot. **Do not repeat this control query
on any sensor subdevice.** Read-only V4L2 ioctls can still invoke unsafe
vendor kernel code.

The persistent `console-ramoops-0` and `pmsg-ramoops-0` were copied from a
subsequent V50 BusyBox rescue boot to
`logs/v50-continue-early-diagnostics-1793796873162120648/pstore.stdout`.
At previous-boot uptime 5157.316 seconds, `Comm: v4l2-ctl` faulted in
`__memcpy`, called from `v4l2_g_ext_ctrls`, during `subdev_do_ioctl`.
The log reports an invalid kernel write address and `Oops: 96000047`.
This is direct evidence that the control enumeration crashed the kernel;
it is not evidence that the preceding frame capture crashed it. The bright
frame's CAMSV stream-on/off and post-capture health had completed about
two minutes earlier.

One normal `fastboot reboot` with V53 and another with the known V50 rescue
image returned to Fastboot without SSH. Fastboot's `continue` command was
accepted, reached authenticated V50 BusyBox SSH at `192.168.100.107:22`,
and later Alpine SSH at port 2222. The V50 observer recorded three healthy
Alpine samples at
`logs/v50-first-boot-1793796733439765509/events.jsonl`. V50's exact
boot_a SHA256 was verified from Linux as
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
The battery then reported 42% and positive charging current. The reason
`fastboot reboot` returned to Fastboot while `continue` booted remains
unproven; do not treat `continue` as a general fix for unrelated faults.

The verified V53 image was subsequently restored to boot_a with the
existing guarded tool, receipt
`logs/v53-boot-a-trial-1793797077448410236/result.json`. Fastboot `continue`
reached authenticated BusyBox and Alpine SSH. Alpine verified the exact V53
boot_a SHA256 `c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e`
with no service issues, receipt
`logs/v53-restored-continue-1793797376061989766.json`. No camera driver was installed at boot. The raw
frames, experimental camera module, and guarded trials remain under
`/noobia/lynx/`.

On this new boot, the ISP's IRQ-gate tool initially reported a false failure:
it assumed YUV-B would always be Linux IRQ 247, but the kernel assigned it
IRQ 246. The line had zero interrupts and Alpine was healthy. The still-armed
watchdog was manually disarmed after those checks. The tool now recognizes
the line by `cam_yuv_b` name and parses its current IRQ number. A separate
read-only 35-second verification of the already loaded module passed at
`logs/camera-isp-patched-trial-1793797587089689124/result.json`. This was
a trial-tool error, not a new camera-kernel fault.
