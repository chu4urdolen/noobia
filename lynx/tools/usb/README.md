# Lynx USB Tools

Read-only continuity and acceptance tooling for the OnePlus Nord 3 (Lynx) USB gadget interface.

## Contents
* `lynx_usb_collector.py`: Acceptance collector and evaluator for the USB ACM serial link.
* `test_lynx_usb_collector.py`: Offline unit test suite with 8 test cases.
* `fixtures/`: JSON observation fixtures for offline evaluation.

## Usage
* Run unit tests: `python3 test_lynx_usb_collector.py`
* Offline fixture evaluation: `python3 lynx_usb_collector.py --fixture fixtures/lynx-usb-connected.json --text`
* Live read-only check: `python3 lynx_usb_collector.py --live --allow-live`
