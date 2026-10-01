# NanoPi NEO / Iris adapter work

The original NanoPi NEO boots Armbian community Debian 13 (kernel 6.18.54).
Its dedicated Ethernet link to Nexus uses NetworkManager's shared connection:
Nexus `10.42.77.1/24`; Neo currently receives `10.42.77.28` by DHCP.
Nexus can log in as `noob` with `/home/aria/.ssh/noobia_neo`. First-boot
recovery passwords are in the ignored, mode-0600 `neo/private/` directory.

Current hardware status (2026-10-01): Neo sees Iris's native USB port as
`303a:4000` and Linux binds `cdc_ncm`. The USB interface is
`enx32eda00c7e99`, with DHCP address `192.168.77.2/24` and gateway
`192.168.77.1`. Iris runs combined firmware `0.7.3-usb-control`.

The audio HAT is FriendlyElec's NanoHat PCM5102A. Its I2S0 device-tree overlay
is [nanohat-pcm5102a.dts](nanohat-pcm5102a.dts), installed on the Neo as
`/boot/overlay-user/nanohat-pcm5102a.dtbo` and selected by `user_overlays`
in `/boot/armbianEnv.txt`. The original boot settings are backed up as
`/boot/armbianEnv.txt.before-nanohat-20260928`. ALSA enumerates the card and a
48 kHz, 16-bit stereo `speaker-test` completed successfully; audible output
has not yet been confirmed by a human with speakers attached.

The separate Espressif USB-dongle experiment is archived under
`iris/adapter_wifi/`; it replaced the Noob runtime and was rolled back.
`iris/firmware/iris_combined/` is the integration project: Iris keeps her
Noob/VM and BLE command path while native USB offers Neo a routed network
interface. End-to-end checks passed: Neo pinged Iris over USB, pinged
`1.1.1.1` bound to the USB interface, resolved a hostname, and received HTTP
200 over HTTPS with curl bound to USB. With Ethernet disconnected, the USB
route carried the default route and `apt-get update` downloaded package
indexes successfully. DNS did not initially work in that Ethernet-free state;
setting `8.8.8.8` on the USB interface with `resolvectl` fixed it. That
override is runtime-only and may need to be reapplied after reboot. Iris still
answered BLE `PING`, `WIFI_STATUS`, and `VM_STATUS` during the network checks.
The USB adapter re-enumerated and renewed DHCP after reboot. Neo's dedicated
Ethernet link to Nexus remains available as a fallback; while both links are
up, their equal route metrics can make the chosen default route vary.

Neo can command Iris directly over that private USB link. The user-owned
`/home/noob/irisctl-usb` client speaks Noob `NRP/1` to
`192.168.77.1:4242`; no BLE bridge or service on Neo is needed. Examples:

    /home/noob/irisctl-usb ping
    /home/noob/irisctl-usb info
    /home/noob/irisctl-usb caps
    /home/noob/irisctl-usb call WIFI_STATUS
    /home/noob/irisctl-usb status
    /home/noob/irisctl-usb load program.nvm
    /home/noob/irisctl-usb run

`load`, `run`, and other mutating commands should only be used when the
current saved VM may be replaced. After flashing `0.7.3`, USB `PING`, `INFO`,
`CAPS`, `TIME_NOW`, `WIFI_STATUS`, and VM `STATUS` were verified. The listener
is bound to Iris's USB address; a connection to her Wi-Fi address on port 4242
was refused. This is an unauthenticated local control protocol, so do not
expose the USB subnet through another router or port forward.

This Armbian image provides `analog-codec`, not a generic I2S DAC overlay;
the former is for the H3's on-chip analog codec, not this external HAT.

## Ethernet-free SSH

Neo's SSH server listens on all interfaces, but Iris's USB-to-Wi-Fi NAT does
not forward inbound TCP. Neo therefore opens an outbound SSH tunnel to Nexus,
bound to its USB address `192.168.77.2`. The tunnel exposes Neo's SSH only on
Nexus loopback port 2222; it is not open on the LAN. On Nexus, use:

    /noobia/neo/ssh-neo

The private tunnel key stays on Neo at `/home/noob/.ssh/noobia_tunnel`. Nexus
authorizes it only for port forwarding to loopback port 2222. The reconnect
loop is `/home/noob/neo-reverse-ssh.sh`, configured by
`/home/noob/neo-tunnel.conf`; a user cron `@reboot` entry launches it before
login. Its source files are kept here as [neo-reverse-ssh.sh](neo-reverse-ssh.sh),
[neo-tunnel.conf](neo-tunnel.conf), and [noob-crontab](noob-crontab). The loop
retries every 15 seconds after disconnection and prevents duplicate instances
with `flock`. Nexus's Noobia Wi-Fi profile statically uses `192.168.100.6`;
if that changes, update `NEXUS_WIFI_ADDRESS` in Neo's config.
`journalctl -t neo-reverse-ssh` on Neo shows reconnect events.
