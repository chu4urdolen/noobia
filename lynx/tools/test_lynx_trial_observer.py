"""Check that initial Fastboot presence cannot be mistaken for a return."""
import json
from pathlib import Path
import time
from lynx_trial_observer import USBObserver

ROOT = Path(__file__).resolve().parent.parent
output = ROOT / 'tools/test-artifacts' / ('trial-observer-' + str(time.time_ns()))
output.mkdir()
old = [dict(identifier='0e8d:201c', bus='1', device='23', sysfs='fixture')]
new = [dict(identifier='0e8d:201c', bus='1', device='24', sysfs='fixture')]
results = []
for name, sequence, expected in [('continuous-presence', [old, old], False),
                                  ('initially-absent', [[], old], False),
                                  ('real-departure-return', [old, [], new], True)]:
    receipt = output / (name + '.json')
    observer = USBObserver(receipt)
    for state in sequence:
        observer.record(state)
        observer.save()
    assert observer.returned.is_set() == expected
    saved = json.loads(receipt.read_text())
    assert saved['fastboot_return_observed'] == expected
    assert saved['phone_commands_sent'] is False
    assert all(event['wall_time_ns'] and event['elapsed_seconds'] >= 0 for event in saved['events'])
    results.append(dict(case=name, return_observed=expected))
(output / 'result.json').write_text(json.dumps(dict(passed=True, cases=results, phone_contacted=False), indent=2) + '\n')
print('Three observer fixtures passed:', output / 'result.json')
