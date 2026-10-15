"""Bounded ordinary READ32 capture. No loader, authentication, or write support."""
import hashlib
import json
from pathlib import Path
import struct
import time

ADDRESS = 0x48090000
SIZE = 0xe0000

def capture(port, directory, diagnostic, size=SIZE):
    # Smaller sizes are for offline tests only; live entry always uses SIZE.
    if size <= 0 or size > SIZE or size % 4:
        raise ValueError('Invalid bounded capture length')
    directory = Path(directory)
    started = time.monotonic()
    diagnostic.update(address=hex(ADDRESS), requested_bytes=size, events=[],
                      received_bytes=0, decoded_bytes=0, verified=False)
    def event(kind, **details):
        item = dict(kind=kind, elapsed_seconds=time.monotonic()-started, **details)
        diagnostic['events'].append(item)
        with (directory / 'transfer-events.jsonl').open('a') as stream:
            stream.write(json.dumps(item) + '\n')
    # Direct endpoint reads retain each successfully received fragment before
    # another USB operation. The SDK's aggregate read discards partial data
    # on timeout. No queued bytes are silently discarded.
    if not port.cdc.queue.empty():
        raise RuntimeError('Transport has queued bytes; fresh handshake required')
    endpoint = port.cdc.EP_IN
    carry = b''
    with (directory / 'pstore-wire.bin').open('wb', buffering=0) as wire, \
         (directory / 'pstore-memory.bin').open('wb', buffering=0) as memory, \
         (directory / 'protocol-replies.bin').open('wb', buffering=0) as replies:
        def fragment(count, body=False):
            requested = min(count, endpoint.wMaxPacketSize)
            data = bytes(endpoint.read(requested, timeout=3000))
            if body:
                wire.write(data)
                diagnostic['received_bytes'] += len(data)
            else:
                replies.write(data)
            event('receive', bytes=len(data), body=body)
            if not data or len(data) > requested:
                raise RuntimeError('Empty or oversized USB reply; received bytes preserved')
            return data
        def exact(count):
            value = b''
            while len(value) < count:
                value += fragment(count-len(value))
            return value
        try:
            for request in (b'\xd1', struct.pack('>I', ADDRESS), struct.pack('>I', size//4)):
                event('request', hex=request.hex())
                if port.usbwrite(request) is not True:
                    raise RuntimeError('USB command write failed')
                echo = exact(len(request))
                event('echo', hex=echo.hex(), matched=echo == request)
                if echo != request:
                    raise RuntimeError('Command echo mismatch')
            status = struct.unpack('>H', exact(2))[0]
            diagnostic['leading_status'] = status
            event('leading-status', value=status)
            if status > 0xff:
                raise RuntimeError('Ordinary read status outside documented accepted range')
            while diagnostic['received_bytes'] < size:
                carry += fragment(size-diagnostic['received_bytes'], body=True)
                usable = len(carry)//4*4
                if usable:
                    memory.write(b''.join(carry[n:n+4][::-1] for n in range(0, usable, 4)))
                    diagnostic['decoded_bytes'] += usable
                    carry = carry[usable:]
            status = struct.unpack('>H', exact(2))[0]
            diagnostic['trailing_status'] = status
            event('trailing-status', value=status)
            if status > 0xff:
                raise RuntimeError('Read completion status outside accepted range')
            diagnostic['verified'] = True
        finally:
            diagnostic['partial_word_hex'] = carry.hex()
            diagnostic['elapsed_seconds'] = time.monotonic()-started
            for name in ['pstore-wire.bin', 'pstore-memory.bin', 'protocol-replies.bin']:
                data = (directory / name).read_bytes()
                diagnostic[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            (directory / 'transfer-receipt.json').write_text(json.dumps(diagnostic, indent=2)+'\n')
    return (directory / 'pstore-memory.bin').read_bytes()
