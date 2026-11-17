#!/usr/bin/env python3
"""Render a wrapper's manifest as its human and agent-facing --help text."""
import json
from pathlib import Path
import sys


def render(script):
    script = Path(script)
    metadata = json.loads(script.with_suffix('.json').read_text())
    properties = metadata['parameters'].get('properties', {})
    lines = [script.name, metadata['description'], '', 'Arguments:']
    if not properties:
        lines.append('  None. Input an empty JSON object: {}')
    for name, schema in properties.items():
        kinds = schema.get('type', 'value')
        if isinstance(kinds, list):
            kinds = ' or '.join(kinds)
        lines.append('  ' + name + ' (' + kinds + ', required): ' + schema.get('description', name.replace('_', ' ')))
        if 'enum' in schema:
            lines.append('    Allowed values: ' + ', '.join(str(x) for x in schema['enum']))
        for label in ('minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems'):
            if label in schema:
                lines.append('    ' + label + ': ' + str(schema[label]))
        if schema.get('items'):
            lines.append('    Item schema: ' + json.dumps(schema['items']))
    lines += ['', 'Execution timeout: ' + str(metadata.get('timeout', 60)) + ' seconds.']
    if metadata.get('protocol') == 'command-stdin':
        lines += ['Agent input: JSON object with command; the runner sends raw command text to stdin.',
                  'CLI: ' + script.name + " -c 'uname -a'",
                  "Or: printf '%s' 'uname -a' | " + script.name,
                  'Output: combined stdout/stderr and the real shell exit status.']
    else:
        lines += ['Input: one JSON object on stdin. No positional arguments.',
                  'Example: printf \'%s\' \'' + json.dumps(metadata.get('example', {})) + "' | " + script.name,
                  'Output: command stdout/stderr; a nonzero exit status indicates failure.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(render(sys.argv[1]), end='')
