import json
from pathlib import Path
import tempfile
import unittest

import transcript_claude as visible_dialogue


def entry(kind, content, **extra):
    return json.dumps({'type': kind, 'message': {'content': content}, **extra})


class VisibleDialogueTest(unittest.TestCase):
    def test_keeps_prompts_and_final_answers_only(self):
        with tempfile.TemporaryDirectory() as folder:
            visible_dialogue.CONVERSATIONS = Path(folder)
            path = Path(folder) / 'a.jsonl'
            path.write_text('\n'.join([
                entry('user', 'Hello Gwyn'),
                entry('assistant', [{'type': 'thinking', 'thinking': 'private'}]),
                entry('assistant', [{'type': 'text', 'text': 'Looking around.'}]),
                entry('assistant', [{'type': 'tool_use', 'name': 'Bash', 'input': {}}]),
                entry('user', [{'type': 'tool_result', 'content': 'secret output'}]),
                entry('user', 'skill text', isMeta=True),
                entry('user', '<command-name>/status</command-name>'),
                entry('assistant', [{'type': 'text', 'text': 'Hello Noob!'}]),
                entry('user', 'Side question', isSidechain=True),
                'not json',
                entry('user', 'Second prompt'),
            ]) + '\n')
            turns = visible_dialogue.read(path)
        self.assertEqual([(t['role'], t['text']) for t in turns], [
            ('noob', 'Hello Gwyn'), ('gwyn', 'Hello Noob!'), ('noob', 'Second prompt')])

    def test_finds_transcripts_in_current_and_legacy_folders(self):
        saved = (visible_dialogue.CONVERSATIONS, visible_dialogue.LEGACY_CONVERSATIONS)
        try:
            with tempfile.TemporaryDirectory() as root:
                current, legacy = Path(root) / 'current', Path(root) / 'legacy'
                current.mkdir()
                legacy.mkdir()
                visible_dialogue.CONVERSATIONS = current
                visible_dialogue.LEGACY_CONVERSATIONS = legacy
                old_id = '70d6e7ab-9e85-4a01-b506-a21fb9c94f79'
                new_id = '11111111-2222-3333-4444-555555555555'
                (legacy / f'{old_id}.jsonl').write_text(entry('user', 'Old session') + '\n')
                self.assertEqual(visible_dialogue.find(old_id), legacy / f'{old_id}.jsonl')
                self.assertEqual(visible_dialogue.read(visible_dialogue.find(old_id))[0]['text'],
                                 'Old session')
                self.assertEqual(visible_dialogue.locate(old_id), legacy / f'{old_id}.jsonl')
                # the current folder wins when both hold the same ID
                (current / f'{old_id}.jsonl').write_text(entry('user', 'New copy') + '\n')
                self.assertEqual(visible_dialogue.find(old_id), current / f'{old_id}.jsonl')
                self.assertIsNone(visible_dialogue.find(new_id))
                self.assertIsNone(visible_dialogue.find('../../etc/passwd'))
                self.assertIsNone(visible_dialogue.find(''))
                stray = Path(root) / f'{new_id}.jsonl'
                stray.write_text(entry('user', 'x') + '\n')
                with self.assertRaises(ValueError):
                    visible_dialogue.read(stray)
        finally:
            visible_dialogue.CONVERSATIONS, visible_dialogue.LEGACY_CONVERSATIONS = saved

    def test_rejects_paths_outside_conversations(self):
        with self.assertRaises(ValueError):
            visible_dialogue.read(Path('/etc/passwd'))


if __name__ == '__main__':
    unittest.main()
