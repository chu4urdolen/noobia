# Nexus Detect Test Fixtures

Test fixture images for unit testing the `nexus_detect` ObjectDetector service offline without network access.

| Fixture File | Size | Expected Top Class | Provenance & Source | License / Usage |
|---|---|---|---|---|
| `cat.jpg` | 17 KB | `cat` | ImageNet sample dataset (`n02123045_tabby.JPEG`), resized to thumbnail for compact repository storage | Research / Educational / Public Domain sample |
| `dog.jpg` | 106 KB | `dog` | ImageNet sample dataset (`n02106662_German_shepherd.JPEG`) | Research / Educational / Public Domain sample |
| `person.jpg` | 17 KB | `person` | Ultralytics sample test asset (`zidane.jpg`), resized to thumbnail | AGPL-3.0 (Ultralytics repository sample asset) |

All images are used strictly for offline verification in `test_detect_service.py` to confirm the model detects genuine classes without fabrication.
