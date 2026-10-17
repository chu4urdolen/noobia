# Prepared stock-protocol gauge identity query

The hardware-proven raw reader remains unchanged. Its result was 2937 at
register 0x06; gauge identification is the next missing piece before using
that value as battery temperature.

The separate `lynx-gauge-identity.c` diagnostic follows the matching OnePlus
driver's `bq27541_hw_config` DeviceType path: one SMBus write-word of information
selector **0x0001** to control register **0x00**, followed by a bounded 20 ms
settling delay and one read-word of **0x00**. The result is cached as
`raw_device_type`. No other gauge commands are sent and there is no retry.
The new driver is named `lynx-gauge-identity`; its build artifact retains the
module filename `lynx-gauge-sample.ko` in a separate private build directory.

This query selects information; it does not initialize the full OEM battery
stack or change calibration, charging, protection, authentication or sealing
settings. TI describes Device Type under section 12.2.1 of the
[BQ28Z610 reference](https://www.ti.com/lit/ug/sluua65e/sluua65e.pdf). The public
TI MACData response convention and the OEM-compatible control-register reply
are not assumed interchangeable: this trial records the actual OEM-protocol
reply and compares it with the matching OnePlus header's family constants.
An unknown reply stays unknown; no guessed model or follow-on command runs.

Stock-header constants for later interpretation are BQ27541=0x0541,
BQ27411=0x0421, BQ28Z610 family=0xffa5, ZY0602=0x0602, and ZY0603=0xa5ff.
These identify the stock driver's reported family, not an independently
authenticated silicon identity or an external temperature calibration.

The module defaults to refusal and retains the exact fixed DT/client/adapter
guards from the raw reader. Source SHA256:
`92289b3be59b6ed71d7862e280874e87f54d16a9afb0c1634550e1bed33465d4`.
Module SHA256:
`93f4fc1e15ece375dfabdedff9dd460fc513a752845f1e902dd08d8248b06df6`.
Private basis: `artifacts/gauge-module-basis-1792105646594458259`.

Completed offline checks:

- Actual C with mocks: exact command/register whitelist, nine client refusals,
  default refusal, query-write error with no read/retry, read error, one query
  and cached sysfs access. Receipt `gauge-reader-logic-1792105646466821751`.
- Exact compiler/headers, every imported stock CRC, full LTO and strict CFI
  symbols verified by the build tool. No kernel/config regeneration or forced
  module loading.
- Actual stock-kernel ARM VM: default refusal, explicit driver registration,
  unload and clean shutdown, no CFI failure. Receipt
  `emulated-gauge-sample-1792105712214035956`. No gauge/probe callback in the VM.
- Actual host command fixtures: six cases passed in
  `gauge-command-check-1792105758653461063`. The first identity-command fixture
  caught an old binary hash in the generated command; that failed result is
  preserved in `gauge-command-check-1792105745459818986`.
- Identity, raw-reader and CPU coordinator self-checks pass independently.

`tools/lynx_gauge_identity_trial.py` pins the separate module/source/test receipts
and reuses the frozen sensor/CPU pack. `start_gauge_listener.py --run-supervised-trial --usb-unplugged-confirmed --identity-query`
starts its detached, bounded listener. The independent stop request is armed
before fallback acknowledgement. Sensors/CPU controls and the fresh temperature
guard precede the query; raw capture, unload and shutdown request follow.
No partition, boot image, charger, or thermal-limit setting changes.

Do not run both gauge profiles on the same boot. The existing once-only RAM
markers prevent retry. Start the listener before Noob powers Lynx on with USB
unplugged. Preserve all results; an unsuccessful/unknown identity response
requires offline review, not automatic probing of other commands or addresses.
