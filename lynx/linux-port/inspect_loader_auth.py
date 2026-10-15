"""Match public-key identifiers offline; never emit private key material."""
import hashlib
import json
from pathlib import Path
import sys

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'sources/mtkclient-readback'))
from mtkclient.Library.Auth.sla_keys import SlaKey, da_sla_keys
from Cryptodome.Util.number import long_to_bytes

audit = json.loads((base / 'docs/download-agent-audit.json').read_text())
loader = (base / 'artifacts/service-reference/DA_BR.bin').read_bytes()
if hashlib.sha256(loader).hexdigest() != audit['loader_sha256']:
    raise ValueError('Loader changed since inspection')
region = audit['entries'][0]['regions'][2]
da2 = loader[region['file_offset']:region['file_offset'] + region['bytes']]
matches = []
count = 0
for key in da_sla_keys:
    if not isinstance(key, SlaKey):
        continue
    count += 1
    modulus = long_to_bytes(key.n)
    if modulus in da2:
        matches.append({'public_modulus_sha256': hashlib.sha256(modulus).hexdigest(),
                        'modulus_bits': key.n.bit_length(), 'byte_offset_in_da2': da2.find(modulus)})
report = {'loader_sha256': audit['loader_sha256'], 'public_keys_checked': count,
          'public_key_matches': matches, 'phone_authentication_attempted': False,
          'restoration_verified': False, 'private_key_material_emitted': False,
          'conclusion': 'No supplied MTKClient DA authentication key matches the stock loader.' if not matches
                        else 'A public-key identifier matches; device session acceptance remains untested.'}
(base / 'docs/loader-auth-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
