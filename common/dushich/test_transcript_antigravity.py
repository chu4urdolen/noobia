"""Check that the Antigravity reader excludes intermediate working steps."""

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import transcript_antigravity as dialogue


def varint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def field(number, data):
    return varint(number << 3 | 2) + varint(len(data)) + data


class VisibleDialogueTests(unittest.TestCase):
    def test_only_user_prompt_and_final_answer_are_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'conversation.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE steps(idx integer, step_type integer, step_payload blob)')
            db.execute('INSERT INTO steps VALUES(0, 14, ?)',
                       (field(19, field(2, b'Please read this file')),))
            db.execute('INSERT INTO steps VALUES(1, 15, ?)',
                       (field(20, field(3, b'Private working step')),))
            db.execute('INSERT INTO steps VALUES(2, 15, ?)',
                       (field(20, field(1, b'The file is ready')),))
            db.commit()
            db.close()
            with patch.object(dialogue, 'CONVERSATIONS', root):
                self.assertEqual(dialogue.read(path), [
                    {'index': 0, 'role': 'noob', 'text': 'Please read this file'},
                    {'index': 2, 'role': 'banshee', 'text': 'The file is ready'},
                ])


if __name__ == '__main__':
    unittest.main()
