.PHONY: build validate validate-arm64 check build-august check-august emulate-august check-august-lz4 emulate-august-lz4

# All compilation/packaging happens on Nexus. These targets never access Lynx.
build:
	python3 build_busybox_image.py

validate-arm64:
	python3 build_busybox_image.py --validate-on-argus

validate:
	python3 validate_image.py

check: validate
	python3 -m unittest -v test_image_formats

# Preserve July artifacts; the August candidate has its own directory.
build-august:
	python3 build_busybox_image.py --stock-dir artifacts/stock-cph2493-August-eu-ota --stock-manifest artifacts/stock-cph2493-August-eu-ota/package-inspection.json --vendor-audit docs/august-vendor-ramdisk-audit.json --output artifacts/busybox-August

check-august:
	python3 validate_image.py --directory artifacts/busybox-August --stock-boot artifacts/stock-cph2493-August-eu-ota/boot.img
	python3 -m unittest -v test_ota_payload

emulate-august:
	python3 emulate_first_boot.py --candidate-dir artifacts/busybox-August --output-dir artifacts/emulated-boot-August

# Corrected packaging: preserve the original failed trial as a separate artifact.
check-august-lz4:
	python3 validate_image.py --directory artifacts/busybox-August-lz4-avb --stock-boot artifacts/stock-cph2493-August-eu-ota/boot.img
	python3 test_avb_boot_model.py

emulate-august-lz4:
	python3 emulate_first_boot.py --candidate-dir artifacts/busybox-August-lz4-avb --output-dir artifacts/emulated-stock-vendor-lz4 --prepend-vendor-ramdisk artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00 --timeout 30
