#!/usr/bin/env python3
"""Offline integrity and replay checks for the prepared Lynx BLE envelope."""

import unittest

from lynx_ble_auth import Authenticator, FragmentAssembler, envelope, fragments


KEY = bytes(range(32))
CHALLENGE = bytes(range(32, 64))


class AuthTests(unittest.TestCase):
    def test_valid_request_and_replay(self):
        auth = Authenticator(KEY, CHALLENGE)
        frame = envelope(KEY, CHALLENGE, 1, b"NRP/1 42 CALL HAPTIC_SET 80 1\n")
        self.assertEqual(auth.accept(frame), b"NRP/1 42 CALL HAPTIC_SET 80 1\n")
        with self.assertRaisesRegex(ValueError, "replayed"):
            auth.accept(frame)
        self.assertEqual(auth.accept(envelope(KEY, CHALLENGE, 2, b"NRP/1 43 STATUS\n")),
                         b"NRP/1 43 STATUS\n")

    def test_tamper_and_wrong_challenge(self):
        auth = Authenticator(KEY, CHALLENGE)
        frame = envelope(KEY, CHALLENGE, 1, b"NRP/1 7 CALL HAPTIC_SET 1 0\n")
        with self.assertRaisesRegex(ValueError, "authentication failed"):
            auth.accept(frame.replace(b"SET 1 0", b"SET 1 1"))
        with self.assertRaisesRegex(ValueError, "authentication failed"):
            auth.accept(envelope(KEY, bytes(32), 1, b"NRP/1 7 PING\n"))
        self.assertEqual(auth.highest_sequence, 0)

    def test_frame_bounds_and_syntax(self):
        auth = Authenticator(KEY, CHALLENGE)
        for frame in (b"NRP/1 1 CALL HAPTIC_SET 1 0\n",
                      b"AUTH/1 1 00 NRP/1 1 PING\n", b"x" * 513):
            with self.subTest(frame=frame[:20]), self.assertRaises(ValueError):
                auth.accept(frame)
        with self.assertRaises(ValueError):
            envelope(KEY, CHALLENGE, 1, b"NRP/1 1 LOAD " + b"aa" * 300 + b"\n")
        with self.assertRaises(ValueError):
            envelope(KEY, CHALLENGE, 1, b"NRP/1 1 PING\nNRP/1 2 PING\n")

    def test_bounded_fragments_reassemble_only_for_same_device(self):
        frame = envelope(KEY, CHALLENGE, 1, b"NRP/1 8 LOAD 00\n")
        chunks = list(fragments(frame))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(2 <= len(chunk) <= 20 for chunk in chunks))
        assembler = FragmentAssembler()
        for chunk in chunks[:-1]:
            self.assertIsNone(assembler.add("nexus", chunk))
        with self.assertRaises(ValueError):
            assembler.add("other", chunks[-1])
        self.assertEqual(assembler.add("nexus", chunks[-1]), frame)
        with self.assertRaises(ValueError):
            assembler.add("nexus", chunks[-1])


if __name__ == "__main__":
    unittest.main()
