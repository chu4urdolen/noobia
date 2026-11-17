"""Bounded stock-loader GPT probe for Lynx; no flash command is exposed."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import runpy
import signal
import sys
import time

root = Path('/noobia/lynx')
source = root / 'linux-port/sources/mtkclient-readback'
reference = root / 'linux-port/artifacts/service-reference'
manifest_path = root / 'tools/mtk-readonly-source-manifest.json'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--connect', action='store_true', help='Attempt the prepared stock-loader GPT probe')
parser.add_argument('--self-test', action='store_true', help='Exercise mutation guards without contacting hardware')
parser.add_argument('--ram-probe', action='store_true', help='Use the reviewed exact RAM patch for a bounded GPT read')
parser.add_argument('--stock-table', action='store_true', help='Request only the stock loader partition-table metadata without attempting session authentication')
args = parser.parse_args()
if args.stock_table and args.ram_probe:
    parser.error('Select exactly one probe method')
if args.ram_probe and args.connect and (root / 'linux-port/docs/RAM-READBACK-RESULT-20261010.md').exists():
    raise SystemExit('The reviewed RAM hash probe was rejected; repeating it is disabled')

expected = json.loads(manifest_path.read_text())
for name, digest in expected['files'].items():
    path = root / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('Diagnostic source or resource changed: ' + name)

sys.path.insert(0, str(source))
from mtkclient.Library.mtk_class import Mtk
from mtkclient.Library.mtk_preloader import Preloader
from mtkclient.Library.DA.mtk_daloader import DAloader
from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient.Library.DA.xmlflash.xml_lib import DAXML
from mtkclient.Library.DA.xmlflash.xml_lib import UpFile
from mtkclient.config import usb_ids


def deny(*unused_args, **unused_kwargs):
    raise RuntimeError('Read-only probe blocked a write, security bypass or fallback')


blocked = []
blocked_callables = []
for owner, names in ((Mtk, ('bypass_security',)),
                     (Preloader, ('reset_to_brom',)),
                     (DAloader, ('writeflash', 'formatflash', 'write_rpmb', 'auth_rpmb')),
                     (DAXML, ('writeflash', 'formatflash', 'patch_da'))):
    for name in names:
        if hasattr(owner, name):
            setattr(owner, name, deny)
            blocked.append(owner.__name__ + '.' + name)
            blocked_callables.append(getattr(owner, name))

def checked_sla(self, *positional, **keywords):
    data = self.get_sys_property(key='DA.SLA', length=0x200000)
    if not isinstance(data, bytes):
        raise RuntimeError('No valid loader authentication-state response')
    match = re.search(rb'<item\b[^>]*>([^<]+)</item>', data)
    if match is None:
        raise RuntimeError('Malformed loader authentication-state response')
    if match.group(1).strip() != b'DISABLED':
        raise RuntimeError('Loader requests session authentication; stop instead of trying fallback keys')
    return False


DAXML.check_sla = checked_sla

if args.ram_probe:
    ram_audit = json.loads((root / 'linux-port/docs/ram-readback-audit.json').read_text())
    patch_audit = json.loads((root / 'linux-port/docs/ram-payload-preparation.json').read_text())
    layout = json.loads((root / 'linux-port/docs/download-agent-audit.json').read_text())
    patched = (reference / 'da2-upstream-patch-OFFLINE-ONLY.bin').read_bytes()
    loader = (reference / 'DA_BR.bin').read_bytes()
    if (hashlib.sha256(patched).hexdigest() != patch_audit['patched_da2_sha256']
            or not ram_audit['potential_ram_route']
            or len(ram_audit['da2_hash_links_in_da1']) != 1):
        raise SystemExit('Reviewed RAM payload requirements not satisfied')
    link = ram_audit['da2_hash_links_in_da1'][0]
    if link['algorithm'] != 'sha256' or link['payload'] != 'without_signature':
        raise SystemExit('Unexpected loader hash contract')
    da1_region, da2_region = layout['entries'][0]['regions'][1:3]
    hash_offset = link['offset_in_da1']
    if not 0 <= hash_offset <= da1_region['bytes'] - da1_region['signature_bytes'] - 32:
        raise SystemExit('Hash replacement is outside reviewed DA1 RAM payload')
    if len(patched) != da2_region['bytes']:
        raise SystemExit('Patched DA2 size changed')
    ram_da2 = patched[:-da2_region['signature_bytes']]
    ram_hash = hashlib.sha256(ram_da2).digest()

    def ram_upload(self):
        if not self.config.stock or self.config.is_brom or self.config.generatekeys:
            return deny()
        if self.config.chipconfig.name != 'MT6983':
            return deny()
        original_da1 = loader[da1_region['file_offset']:da1_region['file_offset'] + da1_region['bytes']]
        if not self.upload_da1():
            raise RuntimeError('Signed DA1 upload failed; no fallback')
        if self.daconfig.da1 != original_da1:
            # Upstream da1 may be passed without its signature; accept only that exact form.
            if self.daconfig.da1 != original_da1[:-da1_region['signature_bytes']]:
                raise RuntimeError('Loaded DA1 differs from reviewed source')
        hash_address = int(da1_region['load_address'], 16) + hash_offset
        da2_address = int(da2_region['load_address'], 16)
        print('Bounded RAM probe: updating DA1 hash at', hex(hash_address), flush=True)
        if not self.boot_to(hash_address, ram_hash):
            raise RuntimeError('DA1 RAM hash redirection failed; no fallback')
        if not self.boot_to(da2_address, ram_da2):
            raise RuntimeError('Reviewed DA2 RAM upload failed; no fallback')
        self.daconfig.da2 = ram_da2
        self.setup_hw_init()
        self.change_usb_speed()
        if self.check_sla() is not False:
            raise RuntimeError('RAM probe did not establish an unauthenticated read session')
        self.reinit(True)
        # No extension payload, key derivation, persistent patch or flash command.
        return True

    DAXML.upload_da = ram_upload

if args.stock_table:
    layout = json.loads((root / 'linux-port/docs/download-agent-audit.json').read_text())
    loader = (reference / 'DA_BR.bin').read_bytes()
    da1_region, da2_region = layout['entries'][0]['regions'][1:3]
    stock_da1 = loader[da1_region['file_offset']:da1_region['file_offset'] + da1_region['bytes']]
    stock_da2 = loader[da2_region['file_offset']:da2_region['file_offset'] + da2_region['bytes'] - da2_region['signature_bytes']]

    def stock_table_request(self):
        reply = self.send_command(self.cmd.cmd_read_partition_table(), noack=True)
        print('Partition-table command acknowledgement:', repr(reply), flush=True)
        if reply is not True:
            raise RuntimeError('Partition-table command was not acknowledged: ' + repr(reply))
        command, transfer = self.get_command_result()
        if not isinstance(transfer, UpFile):
            raise RuntimeError('Expected partition-table upload, received: ' + repr((command, transfer)))
        data = self.download(transfer)
        end, result = self.get_command_result()
        self.ack()
        if end != 'CMD:END' or result != 'OK':
            raise RuntimeError('Partition-table transfer did not complete: ' + repr((end, result)))
        next_command, state = self.get_command_result()
        if next_command != 'CMD:START' or state != 'START':
            raise RuntimeError('Partition-table transfer did not return to ready state')
        if not data or b'<partition_table' not in data or b'<pt>' not in data:
            raise RuntimeError('Partition-table transfer did not contain recognized metadata')
        return data.decode('utf-8')

    def stock_table_upload(self):
        if not self.config.stock or self.config.is_brom or self.config.generatekeys:
            return deny()
        if self.config.chipconfig.name != 'MT6983':
            return deny()
        if not self.upload_da1() or self.daconfig.da1 != stock_da1:
            raise RuntimeError('Signed stock DA1 did not match; no fallback')
        if not self.boot_to(int(da2_region['load_address'], 16), stock_da2):
            raise RuntimeError('Unmodified stock DA2 upload failed; no fallback')
        self.daconfig.da2 = stock_da2
        self.setup_hw_init()
        print('Requesting stock partition-table metadata; no authentication attempt', flush=True)
        data = stock_table_request(self)
        Path('stock-partition-table.xml').write_text(data)
        print('Stock partition table saved:', Path.cwd() / 'stock-partition-table.xml', flush=True)
        self.stock_table_complete = True
        return True

    DAXML.upload_da = stock_table_upload
    # The direct metadata probe does not initialize a general storage session.
    DAloader.writestate = lambda self: None

original_init = Preloader.init


def checked_init(self, *positional, **keywords):
    result = original_init(self, *positional, **keywords)
    if result:
        if self.config.is_brom or self.config.chipconfig.name != 'MT6983':
            raise RuntimeError('Expected MT6983 preloader mode; refusing any other loader route')
    return result


Preloader.init = checked_init


def fresh_connect(self, mtk, directory=None):
    # Upstream connect skips initialization if it sees an existing USB interface
    # without a saved .state. These probes always need a fresh handshake.
    if mtk.config.target_config is not None or mtk.reinited:
        raise RuntimeError('Refusing to reuse a prior loader session')
    if not mtk.preloader.init(directory=directory or '.'):
        return None
    if mtk.config.target_config is None:
        raise RuntimeError('Fresh handshake did not identify the device')
    if args.connect:
        signal.alarm(180)
        print('Fresh handshake complete; three-minute active-probe deadline started', flush=True)
    return mtk


DaHandler.connect = fresh_connect
original_handle = DaHandler.handle_da_cmds


def checked_handle(self, mtk, command, command_args):
    if command != 'printgpt' or not mtk.config.stock or mtk.config.generatekeys:
        return deny()
    if args.stock_table:
        if not getattr(mtk.daloader.da, 'stock_table_complete', False):
            raise RuntimeError('Stock metadata read was not completed')
        return None
    return original_handle(self, mtk, command, command_args)


DaHandler.handle_da_cmds = checked_handle
# Exclude USB Wi-Fi adapters, Fastboot, BROM and unrelated serial devices.
usb_ids.default_ids.clear()
usb_ids.default_ids.update({0x0E8D: {0x2000: -1, 0x2001: -1, 0x20FF: -1},
                           0x22D9: {0x0006: -1}})
command = ['mtk.py', 'printgpt', '--stock', '--noreconnect',
           '--loader', str(reference / 'DA_BR.bin'), '--auth', str(reference / 'auth_sv5.auth')]
if args.self_test:
    for method in blocked_callables:
        try:
            method()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Mutation guard did not reject')
    from types import SimpleNamespace
    calls = []
    fake_mtk = SimpleNamespace(config=SimpleNamespace(target_config=None), reinited=False)
    def fake_init(**kw):
        calls.append(kw)
        fake_mtk.config.target_config = {'sbc': True}
        return True
    fake_mtk.preloader = SimpleNamespace(init=fake_init)
    assert fresh_connect(None, fake_mtk, 'test-session') is fake_mtk
    assert calls == [{'directory': 'test-session'}]
    try:
        fresh_connect(None, fake_mtk)
    except RuntimeError:
        pass
    else:
        raise AssertionError('A prior loader session was reused')
    print('Offline fresh-connection checks passed')
    try:
        checked_handle(None, SimpleNamespace(config=SimpleNamespace(stock=True, generatekeys=False)), 'w', None)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Write command was not rejected')
    assert checked_sla(SimpleNamespace(get_sys_property=lambda **kw: b'<item key="DA.SLA">DISABLED</item>')) is False
    for response in (None, b'', b'<item key="DA.SLA">ENABLED</item>'):
        try:
            checked_sla(SimpleNamespace(get_sys_property=lambda **kw: response))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Invalid or enabled authentication state was accepted')
    if args.ram_probe:
        calls = []
        original_da1 = loader[da1_region['file_offset']:da1_region['file_offset'] + da1_region['bytes']]
        fake = SimpleNamespace(config=SimpleNamespace(stock=True, is_brom=False, generatekeys=False,
                                                      chipconfig=SimpleNamespace(name='MT6983')),
                               daconfig=SimpleNamespace(da1=original_da1),
                               upload_da1=lambda: True,
                               boot_to=lambda address, data: calls.append((address, data)) or True,
                               setup_hw_init=lambda: None, change_usb_speed=lambda: None,
                               check_sla=lambda: False, reinit=lambda display: None)
        assert ram_upload(fake) is True
        assert calls == [(int(da1_region['load_address'], 16) + hash_offset, ram_hash),
                         (int(da2_region['load_address'], 16), ram_da2)]
        fake.config.is_brom = True
        try:
            ram_upload(fake)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unexpected boot mode accepted')
        print('Offline RAM address, payload and mode checks passed')
    if args.stock_table:
        calls = []
        fake = SimpleNamespace(config=SimpleNamespace(stock=True, is_brom=False, generatekeys=False,
                                                      chipconfig=SimpleNamespace(name='MT6983')),
                               daconfig=SimpleNamespace(da1=stock_da1), upload_da1=lambda: True,
                               boot_to=lambda address, data: calls.append((address, data)) or True,
                               setup_hw_init=lambda: None,
                               cmd=SimpleNamespace(cmd_read_partition_table=lambda: 'metadata-read'),
                               send_command=lambda *a, **kw: 'ERR!DENIED',
                               get_command_result=lambda: (_ for _ in ()).throw(AssertionError('Read after rejected command')))
        try:
            stock_table_upload(fake)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Failed metadata response was accepted')
        assert calls == [(int(da2_region['load_address'], 16), stock_da2)]
        fake.send_command = lambda *a, **kw: False
        try:
            stock_table_request(fake)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Missing command acknowledgement was accepted')
        payload = b'<partition_table version="1.0"><pt><name>boot_a</name><start>0x0</start><size>0x4000000</size></pt></partition_table>'
        results = iter([('CMD:UPLOAD-FILE', UpFile('CHK_NO', 'table', 'MEM://0:4096', 4096)),
                        ('CMD:END', 'OK'), ('CMD:START', 'START')])
        fake.send_command = lambda *a, **kw: True
        fake.get_command_result = lambda: next(results)
        fake.download = lambda transfer: payload
        fake.ack = lambda: None
        assert stock_table_request(fake) == payload.decode()
        print('Offline stock payload and rejected metadata-response checks passed')
    print('Offline mutation guards passed:', ', '.join(blocked))
    raise SystemExit(0)
if not args.connect:
    print(json.dumps({'command': command, 'blocked_methods': blocked, 'ram_probe': args.ram_probe, 'stock_table': args.stock_table,
                      'phone_contacted': False, 'flash_operations': 0}, indent=2))
    raise SystemExit(0)

session = root / 'tools/mtk-sessions' / str(time.time_ns())
session.mkdir(parents=True)
(session / 'logs').mkdir()
os.chdir(session)  # Never reuse a previous device's .state or log files.
os.environ['TMPDIR'] = str(root / 'tools/mtk-tmp')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.argv = command
print('Stock-loader GPT probe; session:', session, flush=True)
def expired(signum, frame):
    print('Probe deadline expired; ending without fallback or storage writes', flush=True)
    raise SystemExit(124)

signal.signal(signal.SIGALRM, expired)
signal.alarm(600)
class Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, data):
        self.log.write(data)
        self.log.flush()
        return self.stream.write(data)

    def flush(self):
        self.log.flush()
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)

log = (session / 'probe-output.log').open('w')
sys.stdout, sys.stderr = Tee(sys.stdout, log), Tee(sys.stderr, log)
runpy.run_path(str(source / 'mtk.py'), run_name='__main__')
