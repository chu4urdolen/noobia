"""Compare public RSA moduli with the saved stock loader; no imports or USB."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
source = BASE / 'sources/mtkclient-readback/mtkclient/Library/Auth/sla_keys.py'
layout = json.loads((BASE / 'docs/download-agent-audit.json').read_text())
loader = (BASE / 'artifacts/service-reference/DA_BR.bin').read_bytes()
assert hashlib.sha256(loader).hexdigest() == layout['loader_sha256']
region = layout['entries'][0]['regions'][2]
da2 = loader[region['file_offset']:region['file_offset'] + region['bytes']]
tree = ast.parse(source.read_text())
assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'da_sla_keys' for target in node.targets))
records = []
for item in assignment.value.elts:
    if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.func.id != 'SlaKey':
        continue
    # Never evaluate or output private key fields. Upstream matches only public n.
    keywords = {word.arg: word.value for word in item.keywords}
    modulus = ast.literal_eval(keywords['n'])
    encoded = modulus.to_bytes((modulus.bit_length() + 7) // 8, 'big')
    records.append({'vendor': ast.literal_eval(keywords['vendor']),
                    'name': ast.literal_eval(keywords['name']), 'modulus_bits': modulus.bit_length(),
                    'public_modulus_sha256': hashlib.sha256(encoded).hexdigest(),
                    'stock_da2_big_endian_offset': da2.find(encoded),
                    'stock_da2_little_endian_offset': da2.find(encoded[::-1])})
matches = [record for record in records if record['stock_da2_big_endian_offset'] >= 0]
report = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'loader_sha256': layout['loader_sha256'], 'stock_da2_sha256': hashlib.sha256(da2).hexdigest(),
          'public_key_count': len(records), 'upstream_selection_matches': matches,
          'public_key_comparisons': records, 'device_contacted': False,
          'authentication_attempted': False,
          'limits': ['A modulus match alone would not establish authentication success or safe protocol side effects.',
                     'Absence of a match does not establish that all RAM bypass methods are impossible.']}
(BASE / 'docs/loader-auth-public-key-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ['public_key_count', 'upstream_selection_matches',
                                             'device_contacted', 'authentication_attempted']}, indent=2))
