"""Offline transport tests: no USB or phone access."""
from pathlib import Path
from queue import Queue
import struct
import hashlib
import json
import time
from types import SimpleNamespace
from lynx_pstore_stream import ADDRESS, SIZE, capture

def run():
    size = 4096
    raw = bytes(range(256))*16
    decoded = b''.join(raw[n:n+4][::-1] for n in range(0,size,4))
    test_root=Path(__file__).parent/'test-artifacts'/('pstore-offline-tests-'+str(time.time_ns()))
    test_root.mkdir(parents=True)
    results=[]
    class Endpoint:
        wMaxPacketSize = 512
        def __init__(self, first=0, last=0, cut=None, bad_echo=0, oversize=False):
            self.remaining = bytearray(b'\xd1'+struct.pack('>II',ADDRESS,size//4)+
                                       struct.pack('>H',first)+raw+struct.pack('>H',last))
            if bad_echo: self.remaining[{1:0,2:1,3:5}[bad_echo]] ^= 1
            self.oversize=oversize
            self.cut = cut
            self.done = 0
            self.fragments = iter([1,2,1,3,1,1,1,2,3,7,511])
        def read(self, count, timeout):
            assert timeout == 3000
            if self.oversize: return b'X'*(count+1)
            if self.cut is not None and self.done >= self.cut:
                raise OSError('Simulated disconnect')
            n = min(count,next(self.fragments,512),len(self.remaining))
            if self.cut is not None: n = min(n,self.cut-self.done)
            value=self.remaining[:n]; del self.remaining[:n]; self.done+=n
            return value
    cases = 0
    for options, success in [({},True),({'first':1,'last':255},True),
                              ({'first':256},False),({'last':256},False),
                              ({'cut':14},False),({'cut':1014},False),
                              ({'bad_echo':1},False),({'bad_echo':2},False),
                              ({'bad_echo':3},False),({'oversize':True},False),
                              ({'cut':size+11},False)]:
        endpoint=Endpoint(**options)
        calls=[]
        def write(data): calls.append(data); return True
        port=SimpleNamespace(cdc=SimpleNamespace(queue=Queue(),EP_IN=endpoint),usbwrite=write)
        folder=test_root/str(cases)
        folder.mkdir()
        if True:
            details={}
            try: result=capture(port,folder,details,size=size)
            except (RuntimeError,OSError): assert not success
            else:
                assert success and result==decoded and details['verified']
            path=Path(folder)
            body=(path/'pstore-wire.bin').read_bytes()
            assert body == raw[:len(body)]
            mem=(path/'pstore-memory.bin').read_bytes()
            assert mem == decoded[:len(mem)]
            assert details['received_bytes']==len(body)
            assert details['decoded_bytes']==len(mem)
            assert details['partial_word_hex']==body[len(mem):].hex()
            assert (path/'transfer-receipt.json').exists()
            assert (path/'transfer-events.jsonl').exists()
            if options.get('first',0)>255: assert len(body)==0
            if options.get('last',0)>255: assert len(body)==size and not details['verified']
            if options.get('bad_echo'): assert len(calls)==options['bad_echo']
            elif options.get('oversize'): assert len(calls)==1
            else: assert calls==[b'\xd1',struct.pack('>I',ADDRESS),struct.pack('>I',size//4)]
            results.append(dict(options=options, expected_success=success, passed=True,
                                received_bytes=len(body), decoded_bytes=len(mem)))
        cases+=1
    size=SIZE
    raw=bytes(range(256))*(size//256)
    decoded=b''.join(raw[n:n+4][::-1] for n in range(0,size,4))
    endpoint=Endpoint()
    full=test_root/'full-region'; full.mkdir()
    port=SimpleNamespace(cdc=SimpleNamespace(queue=Queue(),EP_IN=endpoint),usbwrite=lambda data: True)
    details={}
    assert capture(port,full,details)==decoded and details['verified']
    results.append(dict(full_region_bytes=SIZE, passed=True))
    receipt=dict(phone_contacted=False, results=results,
                 test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 capture_source_sha256=hashlib.sha256((Path(__file__).parent/'lynx_pstore_stream.py').read_bytes()).hexdigest())
    (test_root/'test-results.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(f'{len(results)} offline capture cases passed; preserved evidence: {test_root}')

if __name__=='__main__': run()
