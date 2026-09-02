# Nexus Noob tools

`noobctl` is a native C utility for serial NRP/1 commands. It holds DTR and
RTS low and waits through USB-UART reset:

    ./noobctl /dev/ttyUSB0 1 PING
    ./noobctl /dev/ttyUSB0 2 CAPS
    ./noobctl /dev/ttyUSB0 3 LOAD 01000700000000

`nexus_ble_bridge.sh` creates the native BlueZ GATT application sought by
outbound BLE Noobs. `noob_ble_fd` is a small diagnostic helper that writes one
NRP/1 frame into the notification socket acquired by bluetoothctl. No Python
runtime or packages are used.

The Nexus HCI controller is the Realtek 0bda:8771 adapter at
`00:E0:4C:23:99:87`.
