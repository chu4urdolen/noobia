# Iris combined firmware

This ESP-IDF build runs Iris's existing Noob runtime and a USB NCM Wi-Fi
adapter in one image. Iris-specific registration and pins remain in
`iris_noob`; reusable Noob services and both BLE backends (Bluedroid and
NimBLE) remain in `esp/common`. This build selects NimBLE. The small
`esp/common/idf_usb_net` component provides the USB LAN, DHCP at
`192.168.77.1/24`, and NAT; it does not include the full `iot_bridge` manager.
The physical Wi-Fi radio is shared, while USB networking and BLE command
transport have separate interfaces.
The Noob TCP server binds only to Iris's USB LAN IP, not Wi-Fi; it is still
unauthenticated and must remain on a private link.

Startup order matters: camera (using S3 PSRAM-DMA), SD, mic, and Wi-Fi
initialize before NimBLE, followed by USB LAN. Saved Wi-Fi credentials are
used for an asynchronous connection at boot. The main task has a 12 KB stack
because native Wi-Fi commands run through the Noob dispatcher there. NimBLE
uses PSRAM for its pool. These settings are in `sdkconfig.defaults`.

Verified on Iris, 2026-09-29:

- Built and flashed `0.7.3-usb-control` over CH340 UART.
- Camera, SD, mic, Wi-Fi, NimBLE GATT, and USB LAN initialized at boot.
- BLE `PING`, `WIFI_STATUS`, `VM_STATUS`, `SD_LIST`, and `CAMERA_CAPTURE`
  returned through the normal Noob protocol. A photo was saved as
  `/captured/cam_00000002.jpg`.
- `WIFI_CONNECT` over BLE joined Noobia and returned `192.168.100.8`;
  after the auto-connect build rebooted, `WIFI_STATUS` again reported that IP.
- Neo enumerated Iris as `303a:4000` with Linux `cdc_ncm`, received
  `192.168.77.2/24` by DHCP, and used Iris as gateway `192.168.77.1`.
- Bound to that USB interface, Neo reached `1.1.1.1`, resolved DNS, and
  received HTTPS 200 from `example.com`. BLE and the saved VM still responded.
- Neo called `NRP/1` commands over TCP at `192.168.77.1:4242`: `PING`,
  `INFO`, `CAPS`, `TIME_NOW`, `WIFI_STATUS`, and VM `STATUS` passed. The same
  port refused connections to Iris's Wi-Fi address.

After a Neo/Nexus restart, Neo automatically re-enumerated Iris, renewed DHCP,
and reached the internet through a USB-bound ping; Iris rejoined Wi-Fi and
answered BLE. Not yet verified: long-running BLE/Wi-Fi coexistence, USB
unplug/replug behavior, and all native sensor/VM paths in this combined image.
Neo also retains an Ethernet default route with the same metric as USB; after
restart its ordinary default route selected Ethernet. Connect Neo to
Iris's native USB-C port, not the CH340/UART port. The known-good pre-dongle
full-flash backup is
`/noobia/iris/backups/iris-before-wifi-dongle-2026-09-28.bin`.
