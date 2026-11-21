# Nexus Detect Test Fixtures

Test fixture images for unit testing the `nexus_detect` ObjectDetector service offline without network access.

| Fixture File | Size | Expected Top Class | Provenance & Source | License / Usage |
|---|---|---|---|---|
| `cat.jpg` | 17 KB | `cat` | ImageNet sample dataset (`n02123045_tabby.JPEG`), resized to thumbnail for compact repository storage | **Not public domain.** Copyright stays with the original photographer; ImageNet does not own or license its images. Internal test use only |
| `dog.jpg` | 106 KB | `dog` | ImageNet sample dataset (`n02106662_German_shepherd.JPEG`) | **Not public domain.** Copyright stays with the original photographer; ImageNet does not own or license its images. Internal test use only |
| `person.jpg` | 17 KB | `person` | Ultralytics sample test asset (`zidane.jpg`), resized to thumbnail | **Not covered by AGPL-3.0.** Ultralytics' license covers their code, not this press photo of a real person, whose copyright holder is unknown. Internal test use only |

All images are used strictly for offline verification in `test_detect_service.py` to confirm the model detects genuine classes without fabrication.

**To do (Gwyn review, 2026-11-21):** replace all three fixtures with images
whose licence is explicitly CC0 or public domain, such as Wikimedia Commons
files marked PD or CC0. Record each file's page URL. Avoid photos of
identifiable real people. Until then, these files stay test-only and must
not be published or redistributed.
