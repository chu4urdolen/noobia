"""Fixed 64-byte pstore-header read through the ordinary preloader interface."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import signal
import struct
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/sources/mtkclient-readback'
ADDRESS = 0x48090000
WORDS = 16

def read_header(port):
    """Strict protocol status checks; exactly one fixed-region, 16-word request."""
    for data in (b'\xd1', struct.pack('>I', ADDRESS), struct.pack('>I', WORDS)):
        if port.echo(data) is not True:
            raise RuntimeError('Ordinary memory-read command acknowledgement failed')
    if port.rword() != 0:
        raise RuntimeError('Ordinary memory read denied; no fallback')
    values = port.rdword(WORDS)
    if not isinstance(values, (list, tuple)) or len(values) != WORDS:
        raise RuntimeError('Incomplete diagnostic header response')
    if port.rword() != 0:
        raise RuntimeError('Ordinary memory-read completion status failed')
    if not all(isinstance(value, int) and 0 <= value <= 0xffffffff for value in values):
        raise RuntimeError('Invalid diagnostic words')
    return struct.pack('<' + 'I' * WORDS, *values)

def self_test():
    class Port:
        def __init__(self, fail_echo=0, first_status=0, last_status=0, short=False):
            self.calls = []; self.fail_echo = fail_echo
            self.statuses = iter([first_status, last_status]); self.short = short
            self.data_reads = 0
        def echo(self, data):
            self.calls.append(data)
            return len(self.calls) != self.fail_echo
        def rword(self): return next(self.statuses)
        def rdword(self, count):
            assert count == WORDS
            self.data_reads += 1
            return list(range(WORDS - (1 if self.short else 0)))
    good = Port()
    assert read_header(good) == struct.pack('<16I', *range(16))
    assert good.calls == [b'\xd1', struct.pack('>I', ADDRESS), struct.pack('>I', WORDS)]
    for bad in [Port(fail_echo=1), Port(fail_echo=2), Port(fail_echo=3),
                Port(first_status=1), Port(last_status=1), Port(short=True)]:
        try: read_header(bad)
        except RuntimeError: pass
        else: raise AssertionError('Invalid response accepted')
    print('Fixed-address request, word encoding and six abort cases passed; no USB contacted.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--connect', action='store_true')
    actions.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.connect:
        print(json.dumps({'address': hex(ADDRESS), 'bytes': WORDS * 4,
                          'phone_contacted': False, 'loader_upload': False,
                          'memory_or_storage_writes': False,
                          'authentication_or_bypass': False}, indent=2)); return
    manifest = json.loads((ROOT / 'tools/mtk-readonly-source-manifest.json').read_text())
    for name, digest in manifest['files'].items():
        if name.startswith('linux-port/sources/mtkclient-readback/'):
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Pinned diagnostic source changed: ' + name)
    known_log = (ROOT / 'tools/mtk-sessions/aio-readiness-1791650798290665979/probe-output.log').read_text()
    matches = re.findall(r'SOC_ID:\s*([0-9A-Fa-f]{64})', known_log)
    if len(set(matches)) != 1:
        raise RuntimeError('No unambiguous previously identified Lynx chip identifier')
    known_socid = bytes.fromhex(matches[0])
    session = ROOT / 'tools/mtk-sessions' / ('pstore-header-' + str(time.time_ns()))
    session.mkdir(parents=True)
    (session / 'logs').mkdir()
    os.chdir(session)
    os.environ.update(TMPDIR=str(ROOT / 'tools/mtk-tmp'), PYTHONDONTWRITEBYTECODE='1')
    sys.path.insert(0, str(SOURCE))
    from mtkclient.Library.mtk_class import Mtk
    from mtkclient.Library.mtk_preloader import Preloader
    from mtkclient.Library.DA.mtk_daloader import DAloader
    from mtkclient.config.mtk_config import MtkConfig
    from mtkclient.config import usb_ids
    def deny(*unused, **keywords):
        raise RuntimeError('Header-only probe blocks uploads, writes, authentication and fallback')
    for owner, names in [(Mtk, ['bypass_security']),
                         (Preloader, ['read', 'read32', 'read32_direct', 'read16', 'read_a2',
                                      'write', 'write16', 'write32', 'writemem', 'send_da', 'jump_da',
                                      'send_auth', 'send_root_cert', 'handle_sla', 'reset_to_brom',
                                      'setreg_disablewatchdogtimer']),
                         (DAloader, ['upload_da', 'readflash', 'writeflash', 'formatflash',
                                     'write_rpmb', 'auth_rpmb'])]:
        for name in names:
            if hasattr(owner, name): setattr(owner, name, deny)
    usb_ids.default_ids.clear()
    usb_ids.default_ids.update({0x0e8d: {0x2000: -1, 0x2001: -1, 0x20ff: -1}, 0x22d9: {0x0006: -1}})
    config = MtkConfig(loglevel=logging.WARNING)
    config.skipwdt = True
    config.readsocid = True
    config.stock = True
    config.generatekeys = False
    config.hwparam_path = str(session)
    report = {'state': 'waiting', 'address': hex(ADDRESS), 'requested_bytes': WORDS * 4,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'loader_uploaded': False, 'writes_allowed': False,
              'authentication_attempted': False, 'bypass_attempted': False,
              'limits': 'Header access does not prove complete crash-log retrieval or establish record age.'}
    receipt = session / 'receipt.json'
    def save(): receipt.write_text(json.dumps(report, indent=2) + '\n')
    def expired(signum, frame): raise TimeoutError('Bounded diagnostic deadline expired')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    save()
    print('Header-only probe waiting for preloader; session:', session, flush=True)
    mtk = None
    try:
        mtk = Mtk(config=config, loglevel=logging.WARNING)
        mtk.preloader.display = False
        if not mtk.preloader.init(display=False, directory=str(session)):
            raise RuntimeError('No completed preloader handshake')
        signal.alarm(30)
        if config.is_brom or config.hwcode != 0x907 or config.chipconfig.name != 'MT6983':
            raise RuntimeError('Expected MT6983 regular/preloader mode')
        if config.socid != known_socid:
            raise RuntimeError('Chip identity differs from the previously identified Lynx')
        if config.target_config is None or config.target_config.get('memread') is not False:
            raise RuntimeError('Memory-read authorization is required or unknown; no fallback')
        report.update(state='identified', regular_mt6983_and_chip_identity_match=True)
        save()
        print('Lynx identified; requesting only the fixed 64-byte diagnostic header.', flush=True)
        data = read_header(mtk.port)
        path = session / 'pstore-header.raw.bin'
        path.write_bytes(data)
        report.update(state='header-read-complete', file=str(path), bytes=len(data),
                      sha256=hashlib.sha256(data).hexdigest())
        print('64-byte diagnostic header preserved. Receipt:', receipt, flush=True)
    except BaseException as error:
        report.update(state='stopped', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        signal.alarm(0)
        save()
        if mtk is not None: mtk.port.close()

if __name__ == '__main__': main()
