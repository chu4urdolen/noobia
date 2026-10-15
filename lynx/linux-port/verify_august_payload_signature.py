"""Verify the whole OTA payload signature after complete-download checks pass."""
import hashlib
import json
from pathlib import Path
import struct
import time
import zipfile

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from ota_payload import message, one, parse_header, repeated_messages

BASE = Path(__file__).resolve().parent
directory = BASE.parent / 'downloads'
result_path = directory / 'august-eu-payload-signature.json'
integrity_path = directory / 'august-eu-ota-integrity.json'
result = {'state': 'waiting-for-integrity-check', 'phone_contacted': False,
          'full_payload_signature_valid': False, 'key_independently_trusted': False}
result_path.write_text(json.dumps(result, indent=2) + '\n')
try:
    deadline = time.monotonic() + 5400
    while time.monotonic() < deadline:
        integrity = json.loads(integrity_path.read_text())
        if integrity['state'] == 'failed':
            raise ValueError('Full download integrity check failed')
        if integrity['state'] == 'verified':
            break
        time.sleep(5)
    else:
        raise TimeoutError('Waiting for integrity checks exceeded deadline')
    with zipfile.ZipFile(integrity['archive']) as archive:
        certificate = archive.read('META-INF/com/android/otacert')
        key = RSA.import_key(certificate)
        payload_info = archive.getinfo('payload.bin')
        with archive.open(payload_info) as payload:
            header = payload.read(24)
            manifest_size, metadata_signature_size = parse_header(header)
            manifest = payload.read(manifest_size)
            if len(manifest) != manifest_size:
                raise ValueError('Truncated manifest')
            fields = message(manifest)
            blob_bytes = one(fields, 4, 0)
            signature_bytes = one(fields, 5, 0)
            if blob_bytes is None or signature_bytes is None or not 0 < signature_bytes <= 65536:
                raise ValueError('Invalid payload signature bounds')
            if 24 + manifest_size + metadata_signature_size + blob_bytes + signature_bytes != payload_info.file_size:
                raise ValueError('Payload signature bounds do not cover file')
            metadata_signature = payload.read(metadata_signature_size)
            if len(metadata_signature) != metadata_signature_size:
                raise ValueError('Truncated metadata signature')
            digest = SHA256.new(header + manifest)
            remaining = blob_bytes
            while remaining:
                data = payload.read(min(8 * 1024 * 1024, remaining))
                if not data:
                    raise ValueError('Truncated payload data')
                digest.update(data)
                remaining -= len(data)
            signature_message = payload.read(signature_bytes)
            if len(signature_message) != signature_bytes or payload.read(1):
                raise ValueError('Wrong payload signature trailer size')
    checks = []
    for signature in repeated_messages(message(signature_message), 1):
        data = one(signature, 2, 2)
        padding = one(signature, 3, 5)
        if padding is not None:
            length = struct.unpack('<I', padding)[0]
            if length > len(data):
                raise ValueError('Invalid unpadded signature length')
            data = data[:length]
        valid = False
        try:
            pkcs1_15.new(key).verify(digest, data)
            valid = True
        except (ValueError, TypeError):
            pass
        checks.append({'signature_bytes': len(data), 'valid_against_zip_certificate': valid})
    result.update(state='verified' if any(check['valid_against_zip_certificate'] for check in checks) else 'failed',
                  full_payload_signature_valid=any(check['valid_against_zip_certificate'] for check in checks),
                  signed_payload_sha256=digest.hexdigest(), certificate_sha256=hashlib.sha256(certificate).hexdigest(),
                  public_key_der_sha256=hashlib.sha256(key.public_key().export_key(format='DER')).hexdigest(),
                  signature_checks=checks, archive=integrity['archive'],
                  source_format='AOSP Android 13 payload_signer.cc CalculateHashFromPayload',
                  limits='Full payload signature validated against its included OTA certificate; independent OEM-key trust and phone restoration remain unproven.')
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    if result['state'] != 'verified':
        raise ValueError('No valid full-payload signature')
except Exception as error:
    result.update(state='failed', error=str(error))
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    raise
