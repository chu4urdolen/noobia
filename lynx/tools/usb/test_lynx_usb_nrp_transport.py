#!/usr/bin/env python3
"""Offline unit tests for USB CDC ACM NRP/1 transport prototype."""

import os
import unittest

from lynx_usb_nrp_transport import (
    MAX_FRAME,
    MAX_BUFFER,
    AuthenticationError,
    Authenticator,
    DisconnectError,
    FrameTooLongError,
    MalformedFrameError,
    SimulatedSerialChannel,
    StreamingFrameParser,
    compute_mac,
    create_authenticated_frame,
)

SAMPLE_KEY = b"\x01" * 32
SAMPLE_CHALLENGE = b"\x02" * 32


class TestUSBNRPTransport(unittest.TestCase):
    def test_valid_frame_roundtrip(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)
        cmd = "NRP/1 1 STATUS"
        frame = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 1, cmd)

        self.assertTrue(frame.startswith(b"AUTH/1 1 "))
        self.assertTrue(frame.endswith(b" NRP/1 1 STATUS\n"))

        unpacked = auth.verify_and_unpack(frame)
        self.assertEqual(unpacked, b"NRP/1 1 STATUS\n")
        self.assertEqual(auth.highest_sequence, 1)

    def test_sequence_monotonicity_and_replay_rejection(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)
        f1 = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 5, "NRP/1 1 STATUS")
        f2_replay = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 5, "NRP/1 2 INFO")
        f3_older = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 4, "NRP/1 3 CAPS")
        f4_newer = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 6, "NRP/1 4 PING")

        self.assertEqual(auth.verify_and_unpack(f1), b"NRP/1 1 STATUS\n")

        with self.assertRaises(AuthenticationError) as ctx:
            auth.verify_and_unpack(f2_replay)
        self.assertIn("Replay detected", str(ctx.exception))

        with self.assertRaises(AuthenticationError) as ctx:
            auth.verify_and_unpack(f3_older)
        self.assertIn("Replay detected", str(ctx.exception))

        self.assertEqual(auth.verify_and_unpack(f4_newer), b"NRP/1 4 PING\n")
        self.assertEqual(auth.highest_sequence, 6)

    def test_malformed_frames_rejected(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)

        bad_frames = [
            b"INVALID_PREFIX 1 abc NRP/1 1 STATUS\n",
            b"AUTH/1\n",
            b"AUTH/1 1 short_sig NRP/1 1 STATUS\n",
            b"AUTH/1 -1 0000000000000000000000000000000000000000000000000000000000000000 NRP/1 1 STATUS\n",
            b"AUTH/1 1 0000000000000000000000000000000000000000000000000000000000000000 NOT_NRP\n",
            b"AUTH/1 1 0000000000000000000000000000000000000000000000000000000000000000 NRP/1 1 STATUS",  # missing newline
        ]
        for f in bad_frames:
            with self.subTest(frame=f):
                with self.assertRaises(MalformedFrameError):
                    auth.verify_and_unpack(f)

    def test_corrupted_signature_rejected(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)
        f = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 1, "NRP/1 1 STATUS")
        # Flip one character in the hex HMAC
        corrupted = f[:15] + (b"0" if f[15:16] != b"0" else b"1") + f[16:]
        with self.assertRaises(AuthenticationError) as ctx:
            auth.verify_and_unpack(corrupted)
        self.assertIn("HMAC verification failed", str(ctx.exception))

    def test_length_limits(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)
        # Attempt to create frame exceeding MAX_FRAME (512)
        huge_payload = "NRP/1 1 CALL HUGE_" + ("X" * 600)
        with self.assertRaises(FrameTooLongError):
            create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 1, huge_payload)

        # Attempt to feed oversized raw line to verify_and_unpack
        oversized = b"AUTH/1 1 " + (b"0" * 64) + b" NRP/1 1 CALL " + (b"A" * 600) + b"\n"
        with self.assertRaises(FrameTooLongError):
            auth.verify_and_unpack(oversized)

    def test_streaming_fragmentation_and_assembly(self):
        parser = StreamingFrameParser(max_frame=MAX_FRAME)
        f1 = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 1, "NRP/1 1 STATUS")
        f2 = create_authenticated_frame(SAMPLE_KEY, SAMPLE_CHALLENGE, 2, "NRP/1 2 INFO")

        stream = f1 + f2
        # Feed in irregular tiny chunks (e.g. 7 bytes at a time)
        extracted = []
        for i in range(0, len(stream), 7):
            chunk = stream[i : i + 7]
            for frame in parser.feed(chunk):
                extracted.append(frame)

        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0], f1)
        self.assertEqual(extracted[1], f2)

    def test_streaming_buffer_overflow_protection(self):
        parser = StreamingFrameParser(max_frame=100, max_buffer=200)
        # Feed 250 bytes without any newline (generator must be consumed)
        with self.assertRaises(FrameTooLongError) as ctx:
            list(parser.feed(b"A" * 250))
        self.assertIn("overflow", str(ctx.exception))
        self.assertEqual(len(parser.buffer), 0)

    def test_unauthenticated_diagnostic_ping(self):
        auth = Authenticator(SAMPLE_KEY, challenge=SAMPLE_CHALLENGE)
        diag = b"DIAG/1 42 PING\n"
        res = auth.verify_and_unpack(diag)
        self.assertEqual(res, diag)

    def test_simulated_channel_disconnect(self):
        channel = SimulatedSerialChannel()
        channel.write_a(b"test data")
        self.assertEqual(channel.read_b(), b"test data")

        channel.disconnect()
        with self.assertRaises(DisconnectError):
            channel.write_a(b"more data")
        with self.assertRaises(DisconnectError):
            channel.read_b()


if __name__ == "__main__":
    unittest.main()
