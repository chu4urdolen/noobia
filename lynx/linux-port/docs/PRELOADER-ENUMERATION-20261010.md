# Lynx low-level USB enumeration confirmed

The two-minute passive udev monitor expired without events before the user
completed the physical sequence. It cannot establish absence of another mode.
The persistent kernel journal does record the later sequence:

- 03:18:50: Fastboot device 0e8d:201c disconnects.
- 03:19:41: device 22d9:0006 enumerates, product **OPLUS Preloader**,
  manufacturer OPLUS; cdc_acm binds ttyACM0.
- 03:19:49: the preloader USB device disconnects.
- 03:19:53: Fastboot 0e8d:201c returns, serial 89BYAY5L4T9HFUOV.

The user used the requested unplug/power-off/hold-both-volume/reconnect sequence
and subsequently reported Fastboot Mode. A low-level interface was therefore
observed for about eight seconds. This proves enumeration, not a handshake,
loader acceptance, partition readback or restoration capability.

The guarded readback probe already permits 22d9:0006. A new stock-mode GPT probe
is appropriate with a longer bounded connection window and the same physical
sequence. It must stop on session-authentication demand or blocked mutation.
No Linux flashing is permitted merely because enumeration succeeded.
