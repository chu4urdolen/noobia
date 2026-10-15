"""Negative tests for the checks protecting the offline boot artifacts."""
import gzip
from pathlib import Path
import struct
import unittest
from image_formats import read_boot_v4, read_newc, static_aarch64

BASE = Path(__file__).resolve().parent


class ArtifactGuards(unittest.TestCase):
    def test_wrong_architecture_is_rejected(self):
        binary = bytearray((BASE / 'artifacts/busybox-aarch64-static').read_bytes())
        struct.pack_into('<H', binary, 18, 62)
        with self.assertRaisesRegex(ValueError, 'not AArch64'):
            static_aarch64(binary)

    def test_truncated_boot_payload_is_rejected(self):
        image = (BASE / 'artifacts/busybox-offline/nord3-busybox-candidate.img').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Truncated boot'):
            read_boot_v4(image[:-4096])

    def test_archive_traversal_is_rejected(self):
        data = bytearray(gzip.decompress((BASE / 'artifacts/busybox-offline/initramfs.cpio.gz').read_bytes()))
        data[110:113] = b'../'
        with self.assertRaisesRegex(ValueError, 'Unsafe newc path'):
            read_newc(data)

    def test_missing_archive_trailer_is_rejected(self):
        data = gzip.decompress((BASE / 'artifacts/busybox-offline/initramfs.cpio.gz').read_bytes())
        end = data.index(b'TRAILER!!!')
        with self.assertRaises(ValueError):
            read_newc(data[:end])


if __name__ == '__main__':
    unittest.main()
