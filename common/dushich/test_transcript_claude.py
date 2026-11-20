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

    def test_rejects_paths_outside_conversations(self):
        with self.assertRaises(ValueError):
            visible_dialogue.read(Path('/etc/passwd'))


if __name__ == '__main__':
    unittest.main()
