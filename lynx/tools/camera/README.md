# Lynx Camera Boot & Capture Tools (H2 / S1)

This directory contains the camera-at-boot OpenRC persistence service and bounded single-frame capture tool for Lynx:
- `lynx_camera_capture.py`: Standalone single-frame capture tool; validates image data in memory, strictly bounded (timeout <= 5.0s), zero persistent disk writes unless `--output` is explicitly passed.
- `lynx-camera-boot.initd`: Staged OpenRC init script for camera hardware initialization and CAMSV-0 route configuration.
- `test_lynx_camera_capture.py`: Offline unit tests covering dry-run, disable switches, missing device errors, and JSON output contracts.

Install packet: `lynx/linux-port/docs/LYNX-INSTALL-PACKET-H2-CAMERA-BOOT-20261121.md`.
