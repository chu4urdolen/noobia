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
Clang CFI, and symbol versions. No matching clang is currently installed.
Do not force-load a module, invent symbol versions, or disable CFI to proceed.

`tools/audit_gauge_reader_prerequisites.py` saved the pinned gauge header and
I2C reference sources, inspected 522 stock modules, and found consistent genuine
imported CRCs for the I2C registration/read interfaces and module layout.
Private receipt: `artifacts/gauge-reader-prerequisites-1792102617787527051/result.json`.
These imported CRCs are useful evidence, not a complete symbol export table or
proof of module compatibility.

The next build work is matching Kbuild/compiler preparation, followed by an
offline module/CFI review and error-path test. Only then prepare another short
supervised RAM trial with temperature sensors, CPU controls, host capture, and
the independent shutdown request already active. V19 and stock undo remain
unchanged; battery sensing is still missing and extended operation stays held.
