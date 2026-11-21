# Lynx Audio AFE PCM & DSP Core Preflight Gate (Round 7, Item D23)

## 1. Platform Identity and Audio Core Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **AFE PCM controller**: `afe: mt6983-afe-pcm@1e100000`
  (`compatible = "mediatek,mt6983-sound"`, MMIO `0x1e100000` size `0x2000`,
  IRQ `GIC_SPI 448`)
- **DSP offload**: `snd_scp_ultra`
  (`compatible = "mediatek,snd_scp_ultra"`, memif ids `0x7` DL / `0xf` UL)
- **Sound machine**: `sound` (`mediatek,mt6983-mt6338-sound`,
  `mediatek,platform = <&afe>`, headset codec `&mt6338_accdet`)
- **Interface**: ALSA proc interface — `/proc/asound/{cards,pcm}`
  (opening a PCM stream or writing audio data never happens here)
- **Safety Boundary**: Strictly offline by default. Live inspection is
  read-only (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated
  behind `--live --allow-live`, bounded to 8 s, zero writes to the phone
  rootfs, zero module loads, zero acoustic emission, zero stream capture
  or playback.

> **Queue note:** the Round 7 queue says the gate should "assert PCM DAI
> links, buffer allocations, and sample rates". Those are runtime/audio-core
> concepts built by the vendor sound machine driver, **not board-DTS facts**
> (the kernel snapshot has no `drivers/sound` — the vendor driver ships
> with the phone kernel). This gate asserts the verified DTS facts (AFE
> controller, SCP offload, sound machine, clocks, power domain) and the
> runtime ALSA interface presence, and does NOT assert sample-rate or
> buffer facts (D17–D22 precedent for unverified claims).

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/mt6983.dts`
  (AFE node at lines 13828–13980, `snd_scp_ultra` at lines 13984–13988,
  `sound` machine node nearby — all top-level, parent `/`)

### 2.1 AFE PCM Controller (verified)

| Fact | Value |
| --- | --- |
| Node / label | `mt6983-afe-pcm@1e100000` / `afe` |
| Compatible | `mediatek,mt6983-sound` |
| Reg | `<0 0x1e100000 0 0x2000>` |
| Interrupt | `<GIC_SPI 448 IRQ_TYPE_LEVEL_HIGH 0>` |
| Clock references | `&topckgen_clk`, `&apmixedsys_clk`, `&infracfg_ao_clk` |
| Power domain | `<&scpsys MT6983_POWER_DOMAIN_AUDIO>` |
| Clocks | `afe_clk` family (AFE/DAC/ADC/TDM/APLL tuners…) + `topckgen` audio muxes |

```dts
afe: mt6983-afe-pcm@1e100000 {
    compatible = "mediatek,mt6983-sound";
    reg = <0 0x1e100000 0 0x2000>;
    interrupts = <GIC_SPI 448 IRQ_TYPE_LEVEL_HIGH 0>;
    topckgen = <&topckgen_clk>;
    apmixedsys = <&apmixedsys_clk>;
    infracfg = <&infracfg_ao_clk>;
    power-domains = <&scpsys MT6983_POWER_DOMAIN_AUDIO>;
    clocks = <&afe_clk CLK_AFE_AFE>, ...;
};
```

### 2.2 SCP DSP Offload Node (verified)

| Fact | Value |
| --- | --- |
| Node / label | `snd_scp_ultra` |
| Compatible | `mediatek,snd_scp_ultra` |
| `scp_ultra_dl_memif_id` | `<0x7>` |
| `scp_ultra_ul_memif_id` | `<0xf>` |

### 2.3 Sound Machine & Neighbors (verified)

| Node | Compatible | Note |
| --- | --- | --- |
| `sound` | `mediatek,mt6983-mt6338-sound` | `mediatek,platform = <&afe>`, headset codec `&mt6338_accdet` |
| `audio_sram@1e102000` | `mediatek,audio_sram` | 0x18000 @ 0x1e102000, `prefer_mode 0`, `block_size 0x1000` |
| `audio_extend` | `oplus,asoc-audio` | vendor extend (OPLUS_ARCH_EXTENDS) |

### 2.4 Driver Modules (verification status)

- **Unverified (queue scope, NOT asserted):** PCM DAI link topology,
  buffer allocations, sample-rate tables — vendor machine driver territory,
  absent from this kernel snapshot.
- **Verified on disk:** the three top-level nodes above (`afe`,
  `snd_scp_ultra`, `sound`) with the compatibles quoted verbatim.

---

## 3. Tool Usage

```sh
# Offline fixture validation (hermetic, no network)
python3 lynx/tools/audio_afe/lynx_audio_afe_preflight.py \
  lynx/tools/audio_afe/fixtures/audio-afe-sound-ready.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx/tools/audio_afe/lynx_audio_afe_preflight.py --live --allow-live
```

### Exit Codes

| Exit | Meaning |
| --- | --- |
| `0` | Verdict valid: `SOUND_READY`, `UNBOUND_QUIESCENT`, `PARTIAL_ENUMERATED` |
| `1` | Verdict failed: `MALFORMED_SPEC` or `STREAM_ACTIVE`; or live SSH error |
| `2` | `--live` given without `--allow-live` (refusal) |

### Verdict Statuses

| Status | Valid | Meaning |
| --- | --- | --- |
| `SOUND_READY` | yes | ALSA cards + PCM devices enumerated, quiescent |
| `UNBOUND_QUIESCENT` | yes | No runtime ALSA interface (driver safely absent); spec verified |
| `PARTIAL_ENUMERATED` | yes | `/proc/asound` present, no PCM devices; spec verified |
| `STREAM_ACTIVE` | **no** | An active audio stream reported at inspection time: anomaly, human review |
| `MALFORMED_SPEC` | **no** | Board-spec audit failure (named violations) |

### Spec Audit Coverage

- AFE: node present / `mt6983-afe-pcm@1e100000` / `mediatek,mt6983-sound` /
  reg base `0x1e100000` / IRQ 448 / `MT6983_POWER_DOMAIN_AUDIO` / clock
  sources `topckgen`, `apmixedsys`, `infracfg_ao_clk`
- SCP: node present / `mediatek,snd_scp_ultra` / memif `0x7` DL / `0xf` UL
- Sound: node present / `mediatek,mt6983-mt6338-sound` / platform `afe`

### Live Collector (read-only)

Bounded 8 s SSH (pinned key, known-hosts pin, `BatchMode`), script limited
to `cat`/`ls`/`find`/`readlink`/`tr`/`echo`: boot_id, `/proc/asound`
listing, `cards` and `pcm` file reads (plain file reads — **no stream is
opened**), running-DT `mt6983-afe-pcm@*`, `snd_scp_ultra`, and `sound`
nodes with compatibles, and `/proc/modules`. It never writes any attribute
and never touches `/dev/snd`.

---

## 4. Test Evidence

- `test_lynx_audio_afe_preflight.py`: **35 tests, all OK** (constants,
  spec audit incl. per-violation rejection, evaluator verdicts incl.
  `STREAM_ACTIVE` anomaly, CLI exit-code contract, and safety checks:
  forbidden-token scan over the live script, command whitelist,
  "no stream, no writes" assertions, AST import scan, and
  "never wires into local_calls" assertions).
- CLI verified against all five fixtures: sound-ready → `SOUND_READY`
  exit 0; unbound → `UNBOUND_QUIESCENT` exit 0; partial →
  `PARTIAL_ENUMERATED` exit 0; stream-active → `STREAM_ACTIVE` exit 1;
  missing-dt → `MALFORMED_SPEC` exit 1.
- `--live` alone → exit 2; no args → help, exit 0.
- Discovered and passed in the consolidated D20 runner
  (`run_all_lynx_tests.py`).

---

## 5. Known Limitations

- DAI link / buffer / sample-rate topology remains vendor-driver territory
  (unverified on disk; documented, not asserted).
- The live collector cannot determine stream activity read-only;
  `stream_active` is fixture-reported (a live run always treats audio as
  quiescent-by-observation).
- `--live` requires Lynx reachable on the pinned host; offline
  environments use fixtures only.
