# Lynx USB Tools

Validation, framing transport, and cold-boot persistence tooling for the MediaTek MTU3 USB gadget interface on the OnePlus Nord 3 5G CPH2493 (MT6983 / 22823 "Vitamin").

## Contents

* `lynx_usb_collector.py`: Acceptance collector and evaluator for the USB ACM serial link.
* `lynx_usb_nrp_transport.py`: Authenticated framing parser and framing protocol for NRP/1 over `/dev/ttyGS0`.
* `lynx_usb_boot_persistence.py`: Offline validator for OpenRC boot persistence service configuration and ordering.
* `lynx-usb-gadget.initd`: Reference OpenRC init script template for MTU3 ACM gadget persistence.
* `test_lynx_usb_collector.py`: Unit tests for USB acceptance collector (8 tests).
* `test_lynx_usb_nrp_transport.py`: Unit tests for NRP/1 USB framing transport (9 tests).
* `test_lynx_usb_boot_persistence.py`: Unit tests for boot persistence validator and OpenRC script (13 tests).
* `fixtures/`: Deterministic JSON observation fixtures for offline evaluation.

## Usage

```bash
# Run full USB unit test suite (30 tests)
python3 -m unittest discover -s . -p 'test_*.py'

# Evaluate USB boot persistence fixture
python3 lynx_usb_boot_persistence.py fixtures/boot-persistence-valid-enabled.json --init-script lynx-usb-gadget.initd

# Offline acceptance fixture evaluation
python3 lynx_usb_collector.py --fixture fixtures/lynx-usb-connected.json --text

# Live read-only check (requires explicit safety flag)
python3 lynx_usb_collector.py --live --allow-live
```
