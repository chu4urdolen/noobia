# Lynx Fingerprint Tools

Read-only hardware inventory and secure boundary tooling for the OnePlus Nord 3 (Lynx) optical under-display fingerprint sensor.

## Contents
* `lynx_fingerprint_inventory.py`: Read-only inventory evaluating hardware, kernel driver, TEE boundary, and userspace layers.
* `test_lynx_fingerprint_inventory.py`: Offline unit test suite with 7 test cases.
* `fixtures/`: JSON observation fixtures for offline evaluation.

## Usage
* Run unit tests: `python3 test_lynx_fingerprint_inventory.py`
* Offline fixture evaluation: `python3 lynx_fingerprint_inventory.py --fixture fixtures/lynx-fingerprint-v53.json --text`
* Live read-only check: `python3 lynx_fingerprint_inventory.py --live --allow-live --text`
