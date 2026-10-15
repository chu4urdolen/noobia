"""Bounded stock-DA upload-command availability probe; no exploit or data upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/sources/mtkclient-readback'
REFERENCE = ROOT / 'linux-port/artifacts/service-reference'
parser = argparse.ArgumentParser(description=__doc__)
actions = parser.add_mutually_exclusive_group()
actions.add_argument('--connect', action='store_true')
actions.add_argument('--self-test', action='store_true')
args = parser.parse_args()
manifest = json.loads((ROOT / 'tools/mtk-readonly-source-manifest.json').read_text())
for name, digest in manifest['files'].items():
    if not (name.startswith('linux-port/sources/mtkclient-readback/') or name in (
            'linux-port/artifacts/service-reference/DA_BR.bin',
            'linux-port/artifacts/service-reference/auth_sv5.auth')):
        continue  # Unrelated prior RAM-patch reports are not inputs to this probe.
    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Pinned source/resource changed: ' + name)
layout = json.loads((ROOT / 'linux-port/docs/download-agent-audit.json').read_text())
loader = (REFERENCE / 'DA_BR.bin').read_bytes()
if hashlib.sha256(loader).hexdigest() != layout['loader_sha256']:
    raise RuntimeError('Stock loader changed')
region1, region2 = layout['entries'][0]['regions'][1:3]
if (region1['file_offset'], region1['bytes'], int(region1['load_address'], 16), region1['signature_bytes']) != (188, 579552, 0x1000000, 256):
    raise RuntimeError('Stock DA1 layout changed')
if (region2['file_offset'], region2['bytes'], int(region2['load_address'], 16), region2['signature_bytes']) != (579740, 393000, 0x40000000, 256):
    raise RuntimeError('Stock DA2 layout changed')
da1 = loader[region1['file_offset']:region1['file_offset'] + region1['bytes']]
da2 = loader[region2['file_offset']:region2['file_offset'] + region2['bytes'] - region2['signature_bytes']]
sys.path.insert(0, str(SOURCE))
from mtkclient.Library.mtk_class import Mtk
from mtkclient.Library.mtk_preloader import Preloader
from mtkclient.Library.DA.mtk_daloader import DAloader
from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient.Library.DA.xmlflash.xml_lib import DAXML, DwnFile
from mtkclient.config import usb_ids

def deny(*unused, **keywords):
    raise RuntimeError('Availability probe blocks storage operations, authentication and exploits')

blocked = []
for owner, names in [(Mtk, ['bypass_security']), (Preloader, ['reset_to_brom']),
                     (DAloader, ['readflash', 'writeflash', 'formatflash', 'write_rpmb', 'auth_rpmb']),
                     (DAXML, ['readflash', 'writeflash', 'formatflash', 'patch_da',
                              'check_sla', 'handle_sla', 'handle_allinone_signature'])]:
    for name in names:
        if hasattr(owner, name):
            setattr(owner, name, deny)
            blocked.append((owner, name))
DAloader.writestate = lambda self: None

def availability(self):
    # A short literal filename; no overflow, host address or data is supplied.
    command = self.cmd.cmd_security_set_allinone_signature(filename='lynx-aio-readiness.bin')
    result = self.send_command(command)
    self.lynx_availability = {
        'command': command, 'response_class': type(result).__name__,
        'download_request_received': isinstance(result, DwnFile),
        'payload_bytes_uploaded': 0, 'session_authentication_attempted': False,
        'exploit_attempted': False, 'storage_commands_sent': False,
        'limits': 'Command availability does not prove exploitability or working crash-log readback.'}
    if isinstance(result, DwnFile):
        # Record diagnostic metadata only. Do not open its filename or call upload.
        self.lynx_availability['requested_source_file'] = result.source_file
        self.lynx_availability['requested_packet_length'] = result.packet_length
    print(json.dumps(self.lynx_availability, indent=2), flush=True)
    # Loader may now await a file transfer; end the host session without data.
    self.lynx_probe_complete = True
    return True

def stock_upload(self):
    if not self.config.stock or self.config.is_brom or self.config.generatekeys:
        return deny()
    if self.config.chipconfig.name != 'MT6983':
        return deny()
    if not self.upload_da1() or self.daconfig.da1 != da1:
        raise RuntimeError('Signed stock DA1 mismatch or upload failure')
    if not self.boot_to(int(region2['load_address'], 16), da2):
        raise RuntimeError('Unmodified stock DA2 upload failed; no fallback')
    self.daconfig.da2 = da2
    self.setup_hw_init()
    return availability(self)

DAXML.upload_da = stock_upload
original_init = Preloader.init
def checked_init(self, *positional, **keywords):
    result = original_init(self, *positional, **keywords)
    if result and (self.config.is_brom or self.config.chipconfig.name != 'MT6983'):
        raise RuntimeError('Only MT6983 preloader mode is allowed')
    return result
Preloader.init = checked_init

def fresh_connect(self, mtk, directory=None):
    if mtk.config.target_config is not None or mtk.reinited:
        raise RuntimeError('Refusing a reused loader session')
    if not mtk.preloader.init(directory=directory or '.'):
        return None
    if mtk.config.target_config is None:
        raise RuntimeError('Fresh device identification failed')
    if args.connect:
        signal.alarm(120)
        print('Fresh MT6983 handshake; two-minute active deadline started', flush=True)
    return mtk
DaHandler.connect = fresh_connect

def checked_handle(self, mtk, command, command_args):
    if command != 'printgpt' or not mtk.config.stock or mtk.config.generatekeys:
        return deny()
    if not getattr(mtk.daloader.da, 'lynx_probe_complete', False):
        raise RuntimeError('Availability probe did not complete')
    # printgpt is an upstream dispatch label only: never invoke its implementation.
    return None
DaHandler.handle_da_cmds = checked_handle
usb_ids.default_ids.clear()
usb_ids.default_ids.update({0x0e8d: {0x2000: -1, 0x2001: -1, 0x20ff: -1}, 0x22d9: {0x0006: -1}})
command = ['mtk.py', 'printgpt', '--stock', '--noreconnect', '--loader', str(REFERENCE / 'DA_BR.bin'),
           '--auth', str(REFERENCE / 'auth_sv5.auth')]

if args.self_test:
    for owner, name in blocked:
        try: getattr(owner, name)()
        except RuntimeError: pass
        else: raise AssertionError('Blocked method executed')
    calls = []
    fake = SimpleNamespace(cmd=SimpleNamespace(cmd_security_set_allinone_signature=
                           lambda **kw: ('aio-command', kw)),
                           send_command=lambda cmd: calls.append(cmd) or False)
    assert availability(fake) and fake.lynx_availability['download_request_received'] is False
    fake.send_command = lambda cmd: calls.append(cmd) or DwnFile('CHK_NO', 'test', 'lynx-aio-readiness.bin', 4096)
    assert availability(fake) and fake.lynx_availability['download_request_received'] is True
    assert len(calls) == 2 and all(cmd == ('aio-command', {'filename': 'lynx-aio-readiness.bin'}) for cmd in calls)
    assert checked_handle(None, SimpleNamespace(config=SimpleNamespace(stock=True, generatekeys=False),
                          daloader=SimpleNamespace(da=fake)), 'printgpt', None) is None
    try: checked_handle(None, None, 'write', None)
    except RuntimeError: pass
    else: raise AssertionError('Write dispatch accepted')
    print('Offline command-availability, no-data-transfer, dispatch and mutation guards passed.')
    raise SystemExit(0)
if not args.connect:
    print(json.dumps({'mode': 'offline-plan', 'command': command, 'device_contacted': False,
                      'stock_loader_uploaded_to_ram_only_when_connected': True,
                      'new_aio_payload_bytes': 0, 'flash_commands_allowed': False,
                      'authentication_bypass_allowed_by_this_tool': False}, indent=2))
    raise SystemExit(0)

session = ROOT / 'tools/mtk-sessions' / ('aio-readiness-' + str(time.time_ns()))
session.mkdir(parents=True)
(session / 'logs').mkdir()
os.chdir(session)
os.environ.update(TMPDIR=str(ROOT / 'tools/mtk-tmp'), PYTHONDONTWRITEBYTECODE='1')
receipt = {'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'loader_sha256': layout['loader_sha256'], 'state': 'started', 'device_contacted': True,
           'new_aio_payload_bytes': 0, 'stock_da_uploaded_to_ram': 'possible',
           'storage_write_commands_allowed': False, 'authentication_bypass_attempted': False}
(session / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
def expired(signum, frame):
    raise TimeoutError('Bounded availability probe timed out; no fallback')
signal.signal(signal.SIGALRM, expired)
signal.alarm(180)
class Tee:
    def __init__(self, stream, log): self.stream, self.log = stream, log
    def write(self, data): self.log.write(data); self.log.flush(); return self.stream.write(data)
    def flush(self): self.log.flush(); self.stream.flush()
    def __getattr__(self, name): return getattr(self.stream, name)
log = (session / 'probe-output.log').open('w')
sys.stdout, sys.stderr = Tee(sys.stdout, log), Tee(sys.stderr, log)
print('Stock AIO availability probe; session:', session, flush=True)
sys.argv = command
try:
    runpy.run_path(str(SOURCE / 'mtk.py'), run_name='__main__')
except BaseException as error:
    receipt.update(state='ended', exception_type=type(error).__name__, exception=str(error))
    raise
else:
    receipt.update(state='returned')
finally:
    signal.alarm(0)
    (session / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
