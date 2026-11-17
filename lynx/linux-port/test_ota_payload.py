"""Check rejection boundaries before using reconstructed firmware images."""
import hashlib
import lzma
import unittest

from ota_payload import message, reconstruct


class PayloadTests(unittest.TestCase):
    def partition(self, operation):
        data = b'x' * 4096
        return {'size': len(data), 'hash': hashlib.sha256(data).digest(),
                'old_partition_info_present': False, 'operations': [operation]}

    def operation(self, kind=0, blob=b'x' * 4096):
        return {1: [(0, kind)], 2: [(0, 0)], 3: [(0, len(blob))],
                6: [(2, b'\x08\x00\x10\x01')], 8: [(2, hashlib.sha256(blob).digest())]}

    def test_valid_replacement_and_xz(self):
        for kind, blob in ((0, b'x' * 4096), (8, lzma.compress(b'x' * 4096))):
            operation = self.operation(kind, blob)
            self.assertEqual(reconstruct(self.partition(operation), 4096, lambda off, size: blob), b'x' * 4096)

    def test_corrupt_operation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'data hash mismatch'):
            reconstruct(self.partition(self.operation()), 4096, lambda off, size: b'y' * size)

    def test_source_operation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported operation'):
            reconstruct(self.partition(self.operation(4)), 4096, lambda off, size: bytes(size))

    def test_out_of_bounds_extent_is_rejected(self):
        operation = self.operation()
        operation[6] = [(2, b'\x08\x01\x10\x01')]
        with self.assertRaisesRegex(ValueError, 'outside image'):
            reconstruct(self.partition(operation), 4096, lambda off, size: b'x' * size)

    def test_duplicate_extent_is_rejected(self):
        operation = self.operation()
        partition = self.partition(operation)
        partition['operations'].append(operation)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            reconstruct(partition, 4096, lambda off, size: b'x' * size)

    def test_truncated_protobuf_is_rejected(self):
        for data in (b'\x80', b'\x0a\x10short', b'\x09tiny'):
            with self.assertRaises(ValueError):
                message(data)


if __name__ == '__main__':
    unittest.main()
