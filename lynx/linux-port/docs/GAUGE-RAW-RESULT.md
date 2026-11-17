# Custom native gauge reader verified on Lynx

The first custom gauge module ran successfully on Lynx's unchanged stock kernel
and V19 BusyBox environment. Pinned SSH identity passed. The proven sensor and
CPU stages returned successfully before the one-shot reader was loaded into RAM.

The fixed read of register 0x06 at the stock `7-0055` gauge client returned
**2937**. Both the cached sysfs value and kernel log report that same word:

```text
LYNX_GAUGE_RAW register=0x06 word=2937 model_unverified=1
```

If the expected tenths-of-kelvin format is confirmed, this corresponds to about
20.6°C using the stock OPLUS conversion. This remains a candidate temperature,
not independently identified or calibrated battery telemetry. The gauge model
has not yet been queried. A plausible number alone does not settle that.

The actual hardware probe returned in about 1.55 ms. The module loaded, exposed
its cached raw word, and unloaded successfully. No retries, gauge configuration,
charging controls, authentication changes, or partition writes were performed.
The normal SMBus read sends the register-selector byte before receiving data.

The independent shutdown timer was armed before normal fallback cancellation.
Explicit power-off was requested about 6.87 seconds after first beacon contact.
The SSH shutdown command timed out after five seconds; actual physical shutdown
is not inferred from that. No further phone commands followed the request.

Private evidence: `logs/gauge-trial-1792105072191821745/result.json` and its
timestamped stdout/stderr streams. `tools/summarize_gauge_trial.py` verified all
saved stdout lengths/hashes, native identity, stage results, timer ordering,
module hash, matching raw/kernel words, and unload marker. Analysis is preserved
beside the raw streams. The successful module SHA256 is
`9b40f97120dc87329ef42aa74742dca51ddb56f40e78dcfa6df7b7c37662e374`.

The detached listener remained alive across the user turn and found Lynx after
roughly 119 seconds. The first brief observer window ended before the beacon;
the independent listener completed the trial and preserved all results anyway.
This is why a completed receipt, rather than an observer's last line, determines
the outcome. No second power/button sequence was needed.

See [the reader preparation](BATTERY-READER-PREPARATION.md) for build provenance,
stock-kernel VM checks, logic tests, and the narrow transaction scope. The next
investigation is the documented device-identification query, not loading the
full OEM charging bundle. V19, recovery/slot B, private checkpoints, stock undo,
and the global flash hold remain unchanged.
