# Battery temperature: offline reader prerequisites

The CPU trial found the unbound I2C client `7-0055`, named `bq27541-battery`.
The matching stock DT describes `/i2c@11d04000/bq27541-battery@55`, compatible
`oplus,bq27541-battery`, with `qcom,batt_bq28z610` and SOC adjustment properties.
The separate MT6375 gauge node contains `DISABLE_MTKBATTERY`. These describe
the intended hardware; they do not independently identify the installed chip.

The saved OPLUS driver probes more than temperature: it configures the gauge
and can call routines that modify SOC parameters. Loading the full stock
charging bundle is therefore unsuitable as an assumed read-only diagnostic.
No gauge/charging driver or raw I2C transaction was used in the CPU trial.

## A narrow read path

The matching OPLUS header uses register `0x06` for the BQ27541-family temperature
path and `0x02` for BQ27411. Its temperature conversion uses tenths of kelvin.
TI documents BQ28Z610 temperature as a read-word command at `0x06/07`, in 0.1 K,
available while sealed. See section 12.1.4 of the
[TI BQ28Z610 technical reference](https://www.ti.com/lit/ug/sluua65e/sluua65e.pdf).
The published OPLUS code also supports compatible alternative gauges, so a
plausible register value alone will not be treated as validated battery sensing.

The exact stock kernel has `CONFIG_I2C_CHARDEV` unset. A userspace `i2cget`
command or manually created `/dev/i2c-7` node cannot provide the missing kernel
interface. A small, reviewed kernel reader is a possible route. It must target
the exact DT/client and use a fixed read-command whitelist, with no gauge
unsealing, calibration, charging control, or arbitrary-register interface.
It is not yet built or ready for hardware.

## Exact headers recovered without another phone boot

`tools/extract_stock_kheaders.py` verified the saved stock boot hash, decoded its
kernel, and located the embedded XZ archive at Image offset 27525811. It verified
8739 regular header files and the exact release
`5.10.149-android12-9-o-g311738fbb5a8`.

The 3774320-byte compressed archive has SHA256
`a4d9e0f432ccc34a4b2a71f3f952354172e18ce0e5de2bde6719bc9f60a383f8`.
Private receipt: `artifacts/stock-embedded-headers-1792102559855818099/result.json`.
Six OEM symlinks were inventoried without following or extracting them; several
reference vendor files outside the archive subset. The original strict refusal
is preserved in the preceding extraction receipt. Do not blindly unpack it into
a build tree or assume those external includes are present.

This saves another hardware cycle and provides genuine generated headers.
Headers alone do not provide Kbuild, Module.symvers, or a compatible compiler.
The stock configuration uses Android clang 12.0.5/r416183b, full LTO, strict
Clang CFI, and symbol versions. No matching clang was installed at that audit;
the subsequent preparation below supplies it.
Do not force-load a module, invent symbol versions, or disable CFI to proceed.

`tools/audit_gauge_reader_prerequisites.py` saved the pinned gauge header and
I2C reference sources, inspected 522 stock modules, and found consistent genuine
imported CRCs for the I2C registration/read interfaces and module layout.
Private receipt: `artifacts/gauge-reader-prerequisites-1792102617787527051/result.json`.
These imported CRCs are useful evidence, not a complete symbol export table or
proof of module compatibility.

## Subsequent build and offline tests

The exact Android compiler was retrieved from Google's official prebuilt
repository, using an immutable commit resolved from its Android 12 release
branch. Its version matches Android 7284624, clang 12.0.5/r416183b. The download,
hashes, identity output, and pinned sparse source checkout stay private under
`tools/gauge-build-inputs-1792103708378707350`. A slow full-source download was
stopped with its partial file preserved once the sparse checkout succeeded.
The bootstrap tool now defaults to compiler-only downloads.

`prepare_gauge_module_basis.py` combines unmodified pinned Kbuild scripts with
the exact embedded headers. An additive wrapper builds only the required host
tools and module linker script. External-module mode keeps the basis read-only
and does not regenerate the stock configuration or rebuild its kernel.

The partial symbol table uses genuine import CRCs from stock modules, paired
with unambiguous export declarations in the pinned reference source. Unknown or
ambiguous entries remain absent. The logging helper export macro is checked
explicitly. It is not presented as a recovered complete stock Module.symvers.
Per-symbol provenance and header/source inventories are saved privately.

`lynx-gauge-sample.c` is a one-shot raw diagnostic. Default module initialization
refuses. Explicit enablement still requires the exact DT node, compatible,
BQ28Z610 property, adapter 7 and address 0x55. One read-word of register 0x06 is
cached; sysfs reads do not issue further gauge transactions. The standard read
includes a register-selector byte, but no configuration data write. There is no
address scanning, retry, calibration, charging control, worker, or automatic
module alias. The cached word remains model-unverified and is not registered
as a battery temperature or used for thermal safety decisions.

Source SHA256: `c646f5c5897d3dcced770ec3c3c981ce2a59bff61ab7d1b913acf1ba54ed37c4`.
Module SHA256: `9b40f97120dc87329ef42aa74742dca51ddb56f40e78dcfa6df7b7c37662e374`.
Private successful basis: `artifacts/gauge-module-basis-1792104554981554338`.

Verification completed:

- Actual C logic compiled with mocked kernel interfaces: nine probe refusals,
  default initialization refusal, one read, read-error/no-retry, cached sysfs,
  and sentinel preservation. Receipt `gauge-reader-logic-1792103944676969260`.
- Exact compiler, stock vermagic, every imported CRC, GPL license, no aliases,
  full LTO/CFI flags, CFI check/jump-table symbols: verified by the build tool.
- Actual load/unload in an isolated ARM VM with the exact stock kernel:
  default refused; explicit registration and clean unload succeeded; no CFI
  failure or panic. Receipt `emulated-gauge-sample-1792104678354338978`. The VM
  has no gauge and does not test the probe callback or physical read.
- Actual host command text executed against six fixtures: successful sample
  and unload; already-bound client, changed module, temperature guard failure,
  dead timer, and failed raw read. Receipt `gauge-command-check-1792104959339213259`.

Failed attempts remain saved: an early mock declaration error, first basis
missing macro-expanded logging exports, and a static audit looking for a CFI
section even though the linker retained CFI as symbols in combined text. The
corrected audit checks actual CFI symbols; protections were not disabled.

## Prepared hardware trial

`tools/lynx_gauge_trial.py` verifies those exact receipts and reuses the proven
sensor/CPU pack unchanged. Order: pinned SSH, independent stop timer before
fallback acknowledgement, stock sensors/CPU stages, fresh temperature guard,
fixed-client/unbound/hash checks, RAM module upload and one sample, unload,
host capture, then power-off request. No boot image or partition write.
All operations retain timestamped raw stdout/stderr, including failed reads.

`tools/start_gauge_listener.py` starts a bounded detached listener and verifies
its actual readiness/PID. This avoids losing a session-bound listener while
waiting for the user's power cue. Start it before asking Noob to power Lynx on
with USB unplugged. Do not start another listener while one owns the collector
port. V19 and stock undo remain unchanged. Battery sensing is not yet proven
on hardware; extended operation stays held.
