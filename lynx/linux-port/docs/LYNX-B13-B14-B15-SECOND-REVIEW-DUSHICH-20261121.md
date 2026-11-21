# Second review — B13 (2185a79), B14 (2adb7aa), B15 (49cd03e) — Solo Dushich, 2026-11-21

Addendum to `LYNX-B9V2-B10-B11-SECOND-REVIEW-DUSHICH-20261121.md` (D12,
Gwyn queue #147). Banshee's full round-5 set B10–B15 has now landed; this
closes the second-review mandate. Verdicts: **B13 ACCEPT — B14 ACCEPT —
B15 ACCEPT.**

## B13 `2185a79` — ACCEPT
Type-C analog accessory detection trace + decoder (`lynx_headset_collector.py`).
- Switch-bit constants match the stable Linux input ABI exactly:
  `SW_HEADPHONE_INSERT 0x02`, `SW_MICROPHONE_INSERT 0x04`,
  `SW_LINEOUT_INSERT 0x06`, `SW_JACK_PHYSICAL_INSERT 0x07` — the decoder is
  only meaningful if these match what the phone's input subsystem reports via
  `EVIOCGSW`, and they do ✓
- `decode_accessory_type()` is a pure function with explicit illegal-combo
  rules (physical-off with active pins, headphone+lineout together → INVALID) —
  good failure honesty ✓
- 3 new fixtures (lineout, Type-C MUX 4-pole, invalid combo); headset suite
  **11/11 OK** (my run) ✓
- Boundary preserved: switch sense never validates routed ALSA audio ✓

## B14 `2adb7aa` — ACCEPT
Offline NCI frame parser + tag-trial receipt decoder (`lynx_nfc_parser`
→ `lynx_nfc/lynx_nci_parser.py`).
- Pure decoder: **no subprocess, no SSH, no file writes** (grep-verified) —
  zero RF actuation possible ✓
- Decodes the exact frame classes the SN110 tag trial needs (CORE_RESET/INIT,
  RF_DISCOVER, RF_INTF_ACTIVATED with ATQA/UID/SAK, RF_DEACTIVATE, Data) and a
  multi-frame state-transition receipt decoder ✓
- 4 fixtures incl. corrupted-frame negative case; NFC suite **OK**
  (18 new parser tests) ✓

## B15 `49cd03e` — ACCEPT
Catalog proposal for `lynx_usb_serial_status`, staged **outside** local_calls.
- Boundary is *enforced by test*, not just claimed:
  `test_local_calls_boundary_enforced` asserts schema/wrapper are absent from
  `local_calls/` until Aria approves ✓ (0 local_calls files in the commit — verified)
- Follows the accepted B6 proposal pattern (schema, host wrapper,
  manifest + coverage entries, design doc) ✓
- USB suite **39/39 OK** (my run; was 34 pre-B15) ✓
- Not installed; deployment remains Aria's lane ✓

## Round-5 second-review status (D12): COMPLETE
B9v2 ✓ · B10 ✓ · B11 ✓ · B12 ✓ · B13 ✓ · B14 ✓ · B15 ✓ — all ACCEPT, all
offline/read-only, all suites green as of 2026-11-21. Nothing in the round is
installed on Lynx; live trials (GNSS fix, NFC tag, USB serial, camera) remain
Aria's attended lane.
