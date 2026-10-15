"""Fixed full pstore-region read through the ordinary preloader interface."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
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
WORDS = 0xe0000 // 4

from lynx_pstore_stream import capture, SIZE

def read_header(port, diagnostic=None):
    return capture(port, Path.cwd(), diagnostic if diagnostic is not None else {}, size=WORDS*4)

def self_test():
    from test_lynx_pstore_stream import run
    run()

def main():
    global WORDS
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--connect', action='store_true')
    actions.add_argument('--self-test', action='store_true')
    parser.add_argument('--check-command-ready', action='store_true',
                        help='Use one ordinary GET_HW_CODE query for an already connected preloader')
    parser.add_argument('--header-only', action='store_true',
                        help='Request exactly 64 bytes at the same fixed pstore address to check length rejection')
    args = parser.parse_args()
    if args.header_only: WORDS = 16
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
    session = ROOT / 'tools/mtk-sessions' / ('pstore-full-' + str(time.time_ns()))
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
        raise RuntimeError('Pstore collector blocks uploads, writes, authentication and fallback')
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
    config = MtkConfig(loglevel=logging.DEBUG)
    config.skipwdt = True
    config.readsocid = True
    config.stock = True
    config.generatekeys = False
    config.hwparam_path = str(session)
    report = {'state': 'waiting', 'address': hex(ADDRESS), 'requested_bytes': WORDS * 4,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'stream_source_sha256': hashlib.sha256((ROOT / 'tools/lynx_pstore_stream.py').read_bytes()).hexdigest(),
              'ready_source_sha256': hashlib.sha256((ROOT / 'tools/lynx_preloader_ready.py').read_bytes()).hexdigest(),
              'handshake_strategy': 'ordinary-hardware-code-query' if args.check_command_ready else 'startup-handshake',
              'loader_uploaded': False, 'writes_allowed': False,
              'authentication_attempted': False, 'bypass_attempted': False,
              'limits': 'Successful transport does not establish record age or prove this region contains the failed native boot.'}
    receipt = session / 'receipt.json'
    def save(): receipt.write_text(json.dumps(report, indent=2) + '\n')
    def expired(signum, frame): raise TimeoutError('Bounded diagnostic deadline expired')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    save()
    print('Full pstore collector waiting for preloader; session:', session, flush=True)
    mtk = None
    log = (session / 'probe-output.log').open('w')
    try:
        with redirect_stdout(log), redirect_stderr(log):
            mtk = Mtk(config=config, loglevel=logging.DEBUG)
            # The library creates its console handler at import time, before
            # redirect_stdout. Move that handler into the persistent log too.
            for handler in logging.getLogger().handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    handler.setStream(log)
            if args.check_command_ready:
                from lynx_preloader_ready import identify_ready
                class IdentificationStopped(BaseException): pass
                def ready_query(*unused, **keywords):
                    try:
                        return identify_ready(mtk.port, session)
                    except Exception as error:
                        # The SDK otherwise catches RuntimeError and retries.
                        raise IdentificationStopped(str(error)) from error
                mtk.port.run_handshake = ready_query
            mtk.preloader.display = False
            if not mtk.preloader.init(display=False, directory=str(session)):
                raise RuntimeError('No completed preloader handshake')
        signal.alarm(120)
        if config.is_brom or config.hwcode != 0x907 or config.chipconfig.name != 'MT6983':
            raise RuntimeError('Expected MT6983 regular/preloader mode')
        if config.socid != known_socid:
            raise RuntimeError('Chip identity differs from the previously identified Lynx')
        if config.target_config is None or config.target_config.get('memread') is not False:
            raise RuntimeError('Memory-read authorization is required or unknown; no fallback')
        report.update(state='identified', regular_mt6983_and_chip_identity_match=True, target_config=dict(config.target_config))
        save()
        print(f'Lynx identified; requesting {WORDS*4} bytes at the fixed pstore address.', flush=True)
        report['read_protocol'] = {}
        data = read_header(mtk.port, report['read_protocol'])
        path = session / 'pstore-memory.bin'
        path.write_bytes(data)
        report.update(state='pstore-read-complete', file=str(path), bytes=len(data),
                      sha256=hashlib.sha256(data).hexdigest())
        print(f'Complete requested {WORDS*4}-byte region preserved. Receipt:', receipt, flush=True)
    except BaseException as error:
        report.update(state='stopped', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        signal.alarm(0)
        save()
        if mtk is not None: mtk.port.close()
        log.close()

if __name__ == '__main__': main()
