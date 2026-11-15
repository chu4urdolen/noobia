# Deployment history

## 2026-10-04 — current

- Universal numeric/ASCII channel firmware flashed; hashes verified.
- Live diagnostic VM passed ASCII filename -> sequence -> SD_READ -> queue,
  returning 30 bytes. Neo OLED text also passed through an ASCII sequence.
- Police-on-all (138 bytes) restored with persistent autorun.
- Neo native display/file functions and common argument registry deployed.
- Status panel uses black text on white, an 80x80 mascot converted from the
  original before thresholding, and an exact-bytecode VM name lookup.
- User rebooted Neo. USB commands, Wi-Fi 192.168.100.8, BLE, VM restored autorun
  and the status-display worker recovered without intervention.
- Boot diagnostics: 38 ready, zero failures/pending; four physical outputs
  remain untested by automatic observation.
- Audio output and TV IR replay remain unproven; successful API calls are not
  evidence that a speaker sounded or a TV responded.

## 2026-10-02 — earlier deployment

- Combined ESP image flashed through Nexus UART USB; flash hashes verified.
- Hardware checks passed: PING, CALL_MIXED TIME_NOW with empty text,
  STATUS, VM_LAST_STATUS, WIFI_CONNECT. Wi-Fi assigned 192.168.100.8.
- Saved 107-byte VM restored with autorun enabled.
- Updated irisctl-usb and endpoint source/config/unit copied to /home/noob.
- Native USB reconnected; cdc_ncm interface has 192.168.77.2/24.
- Compiler and ir-keytable installed successfully through Iris Wi-Fi.
  Dependency resolution also updated libc/locales packages.
- Endpoint compiled on Neo, installed at /usr/local/sbin/noob-neod, and
  enabled as noob-neod.service. Runs as noob with input group access.
- Listener verified at 192.168.77.2:4243 only, not Ethernet or all interfaces.
- BLE PING passed while USB networking was active. BLE CALL NEO_CAPS
  completed the Nexus -> ESP -> USB TCP -> Neo -> ESP -> BLE round trip.
- Neo USB CALL_MIXED TIME_NOW with empty text passed; saved VM still running.
- CIR overlay enabled and Neo rebooted successfully. Boot configuration
  backup: /boot/armbianEnv.txt.before-cir-20261002.
- Verified sunxi-ir rc0, /dev/input/event1, /dev/lirc0. Initially only lirc
  protocol was enabled; noob-ir-protocols.service installed and enabled to
  configure decoders. No remote keys mapped to Linux actions (rc-empty).
- Initial '-p all' enabled kernel decoders but emitted optional BPF errors.
  Source updated to select kernel protocols explicitly instead.
- Scanner source updated to use stdbuf so events are delivered immediately.
  Revised binary compiled on Neo and installed. Kernel-only decoder service
  and udev rule installed and active; decoder setup completes cleanly.
- Original cable restored: ESP 303a:4000 and USB 192.168.77.2 interface return.
  SD reinserted: saved 107-byte VM restored with autorun and executes again.
- NEO_IR_SCAN_START, STATUS, READ, STOP passed through the ESP USB bridge.
  BLE NEO_IR_STATUS also passed. Idle read has no queued scancodes.
- Scanner stopped after smoke test. An actual remote-button event remains
  the next test. Replacement cable did not enumerate in observed checks.
