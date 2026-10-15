"""Verify OTA metadata against the certificate contained in its ZIP."""
import hashlib
import json
from pathlib import Path
import struct

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from ota_payload import message, one, repeated_messages

BASE = Path(__file__).resolve().parent
directory = BASE / 'artifacts/stock-cph2493-August-eu-ota'
certificate = (directory / 'otacert.pem').read_bytes()
key = RSA.import_key(certificate)
metadata = (directory / 'payload-metadata.bin').read_bytes()
signatures = message((directory / 'payload-metadata-signatures.bin').read_bytes())
checks = []
for signature in repeated_messages(signatures, 1):
    data = one(signature, 2, 2)
    unpadded = one(signature, 3, 5)
    if unpadded is not None:
        data = data[:struct.unpack('<I', unpadded)[0]]
    valid = False
    try:
        pkcs1_15.new(key).verify(SHA256.new(metadata), data)
        valid = True
    except (ValueError, TypeError):
        pass
    damaged = False
    try:
        pkcs1_15.new(key).verify(SHA256.new(bytes([metadata[0] ^ 1]) + metadata[1:]), data)
    except (ValueError, TypeError):
        damaged = True
    checks.append({'signature_bytes': len(data), 'valid_against_embedded_certificate': valid,
                   'damaged_metadata_rejected': damaged})
report = {'metadata_sha256': hashlib.sha256(metadata).hexdigest(),
          'certificate_sha256': hashlib.sha256(certificate).hexdigest(),
          'public_key_der_sha256': hashlib.sha256(key.public_key().export_key(format='DER')).hexdigest(),
          'rsa_bits': key.size_in_bits(), 'signature_checks': checks,
          'metadata_signature_valid': any(item['valid_against_embedded_certificate'] for item in checks),
          'key_independently_trusted': False, 'phone_contacted': False,
          'limits': 'Signature proves consistency with the ZIP certificate; independent publisher-key trust is not established.'}
(directory / 'metadata-signature-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if not report['metadata_signature_valid']:
    raise SystemExit(1)
