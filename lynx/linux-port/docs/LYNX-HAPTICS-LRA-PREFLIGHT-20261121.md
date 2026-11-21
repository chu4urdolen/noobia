# Lynx Haptics & Linear Resonant Actuator (LRA) Bring-Up Preflight (Round 7, Item D21)

## 1. Platform Identity and Haptics Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Actuator**: single linear resonant actuator (LRA) vibrator, DT node
  `vibrator0: vibrator@0` under the `&odm` block
- **Interface**: Linux vibrator class — `/sys/class/timed_output/vibrator`
  or `/sys/class/leds/vibrator` (state read-only; writing `state`,
  `delay`, or `brightness` drives the actuator and is never done here)
- **Safety Boundary**: Strictly offline by default. Live inspection is
  read-only (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated
  behind `--live --allow-live`, bounded to 8 s, zero writes to the phone
  rootfs, zero module loads, zero acoustic/vibration side effects.

> **Queue note:** the Round 7 queue names a "MediaTek MT6375 haptic wave
> generator / LRA driver" as the expected sub-PMIC driver. That name is
> **unverified on disk**: no haptic or vibrator driver source exists in the
> kernel snapshot (verified — see §2.3), so the gate does NOT assert module
> names (same precedent as D17 display, D18 touch, D19 aux cameras).
> Binding evidence comes from the Linux vibrator class interface and its
> driver link instead.

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- Board DTS: `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts` (lines 81–86, inside `&odm`, siblings `led0`–`led6`)

### 2.1 Vibrator Node (verified)

| Fact | Value |
| --- | --- |
| DT label | `vibrator0` |
| Node | `vibrator@0` |
| Parent | `&odm` |
| Compatible | `mediatek,vibrator` |
| `vib_timer` | `<25>` |
| `vib_limit` | `<9>` |
| `vib_vol` | `<9>` (source has no space after `=`) |

```dts
&odm {
    ...
    vibrator0:vibrator@0 {
        compatible = "mediatek,vibrator";
        vib_timer = <25>;
        vib_limit = <9>;
        vib_vol= <9>;
    };
    ...
};
```

### 2.2 Runtime Interface (queue invariant, standard Linux classes)

- `/sys/class/timed_output/vibrator` — legacy `timed_output` vibrator class
- `/sys/class/leds/vibrator` — led-class vibrator (brightness = on/off)

The gate treats "class present + driver bound + state 0" as the healthy
quiescent target and "bound + state ≠ 0" as the `ACTIVE_PULSE` safety
anomaly (an LRA pulse is transient; a persistent active state at inspection
time means something is driving the actuator and needs human review).

### 2.3 Driver Modules (verification status)

- **Unverified (queue guess, NOT asserted):** "MT6375 haptic wave
  generator / LRA driver" module names.
- **Verified on disk:** the string `mediatek,vibrator` appears only in five
  `.dts`/`.dtsi` files; a full grep of the kernel snapshot `drivers/` tree
  finds **zero** haptic/vibrator driver sources (no `haptic*`, no
  `vibra*` driver files, no dt-binding match). The board's runtime driver
  ships with the vendor kernel on the phone, not in this source snapshot.
  Consequently the gate binds on the runtime class interface, not on
  module names.

---

## 3. Tool Usage

```sh
# Offline fixture validation (hermetic, no network)
python3 lynx/tools/haptics/lynx_haptics_preflight.py \
  lynx/tools/haptics/fixtures/haptics-preflight-bound.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx/tools/haptics/lynx_haptics_preflight.py --live --allow-live
```

### Exit Codes

| Exit | Meaning |
| --- | --- |
| `0` | Verdict valid: `BOUND_QUIESCENT`, `UNBOUND_QUIESCENT`, `PARTIAL_ENUMERATED` |
| `1` | Verdict failed: `MALFORMED_SPEC` or `ACTIVE_PULSE`; or live SSH error |
| `2` | `--live` given without `--allow-live` (refusal) |

### Verdict Statuses

| Status | Valid | Meaning |
| --- | --- | --- |
| `BOUND_QUIESCENT` | yes | Class present, driver bound, state 0 |
| `UNBOUND_QUIESCENT` | yes | No runtime class (driver safely absent); spec verified |
| `PARTIAL_ENUMERATED` | yes | Class present, no driver bound; spec verified |
| `ACTIVE_PULSE` | **no** | Bound + non-zero state: safety anomaly, human review |
| `MALFORMED_SPEC` | **no** | Board-spec audit failure (named violations) |

### Spec Audit Coverage

- `vibrator_node_present`, node name `vibrator@0`, parent `odm`
- compatible `mediatek,vibrator`
- waveform parameters `vib_timer=25`, `vib_limit=9`, `vib_vol=9`

### Live Collector (read-only)

Bounded 8 s SSH (pinned key, known-hosts pin, `BatchMode`), script limited
to `cat`/`ls`/`find`/`readlink`/`tr`/`echo`: boot_id, vibrator class paths,
driver links, state/brightness reads, running-DT `vibrator@*` nodes with
compatible, and `/proc/modules`. It never writes any sysfs attribute.

---

## 4. Test Evidence

- `test_lynx_haptics_preflight.py`: **31 tests, all OK** (spec audit,
  evaluator verdicts incl. `ACTIVE_PULSE` anomaly, CLI exit-code contract,
  and safety checks: forbidden-token scan over the live script, command
  whitelist, AST import scan, and "never wires local_calls haptic pulse
  tools into preflight" assertions).
- CLI verified against all four fixtures: bound → `BOUND_QUIESCENT` exit 0;
  unbound → `UNBOUND_QUIESCENT` exit 0; missing-dt → `MALFORMED_SPEC`
  exit 1; active-pulse → `ACTIVE_PULSE` exit 1.
- `--live` alone → exit 2; no args → help, exit 0.
- Discovered and passed in the consolidated D20 runner
  (`run_all_lynx_tests.py`).

---

## 5. Known Limitations

- Module names for the LRA driver remain unverified (vendor driver on the
  phone; absent from the on-disk kernel snapshot) — documented, not asserted.
- `vib_timer` / `vib_limit` / `vib_vol` are board-DTS waveform parameters;
  their runtime semantics (ms vs. steps, volume scale) are not exercised —
  the gate pins the expected values so regressions are visible, without
  driving the actuator.
- `--live` requires Lynx reachable on the pinned host; offline environments
  use fixtures only.
