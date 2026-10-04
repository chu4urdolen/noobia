# Neo diagnostics

Current host regression checks (no physical GPIO/I2C writes):

```sh
bash neo/tests/test-thread-display.sh
bash neo/tests/test-noob-files.sh
```

The first checks compact status labels, exact VM-name matching and missing-data
handling. The second uses a local TCP fixture to verify binary transfers,
extension routing, overwrite protection and path validation.

`native-registry.c` tests the Linux command parser/registry. `audio-tone.c` and
`ir-raw-probe.c` are manual hardware probes; do not launch them at boot.
`ssd1306-smoke.c` and MIT-licensed `friendlyelec-bakebit/` examples are historical
comparison artifacts, not drivers for Iris's SH1107 screen. The active display
driver is `neo/tools/iris-gif-oled`, composed by `noob-display`/`thread_display`.

Deployment and display details: `neo/tools/DISPLAY.md`, `FILES.md` and
`noob-neod-status.md`. Firmware-only VM diagnostics live in `iris/diagnostics`.
Generated binaries, private configurations and runtime logs are not source.
