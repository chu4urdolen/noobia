# Lynx Headset Collector & Validator

This directory provides a passive, strictly bounded event collector and receipt validator for headset switch status on Lynx (OnePlus Nord 3 5G CPH2493 / MT6983 / project 22823 "Vitamin").

## Diagnostic Separation

A core requirement of this tool is enforcing the architectural boundary:
> **Jack Switch Detection $\neq$ Routed Audio Validation.**

An `EV_SW` event (`SW_HEADPHONE_INSERT`, `SW_MICROPHONE_INSERT`) confirms electrical/impedance sense by the PMIC or jack sensor. It does **not** prove ALSA PCM stream routing, DSP pipeline enablement, amplifier unmute, or acoustic transmission.

## Files

- `lynx_headset_collector.py`: Passive switch bit reader (`EVIOCGSW_8` ioctl `0x8008451B`), bounded non-blocking `select()` event listener, and offline receipt validator.
- `test_lynx_headset_collector.py`: Unit test suite covering unplugged, headset inserted, headphones only, malformed, and boundary enforcement.
- `fixtures/`: Test fixture receipts demonstrating pass, unplugged, and failure states.
