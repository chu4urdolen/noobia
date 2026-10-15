"""Recognize already-command-ready preloader using only GET_HW_CODE."""
import json
from pathlib import Path
import time

def identify_ready(port, directory):
    report={'command_hex':'fd', 'read_only_identification':True,
            'matched':False, 'reply_hex':'', 'events':[]}
    started=time.monotonic()
    directory=Path(directory)
    raw=bytearray()
    try:
        if not port.cdc.queue.empty():
            raise RuntimeError('Queued transport bytes; refusing command-ready query')
        sent=port.cdc.EP_OUT.write(b'\xfd',timeout=500)
        report['events'].append(dict(operation='write',sent_bytes=sent))
        if sent!=1: raise RuntimeError('Hardware-code command was not sent completely')
        while len(raw)<5:
            value=bytes(port.cdc.EP_IN.read(5-len(raw),timeout=1000))
            raw.extend(value)
            (directory/'command-ready-reply.bin').write_bytes(raw)
            report['events'].append(dict(operation='read',bytes=len(value),hex=value.hex(),
                                         elapsed_seconds=time.monotonic()-started))
            if not value or len(raw)>5: raise RuntimeError('Incomplete or oversized hardware-code reply')
        # Exact regular-mode response already observed from this Lynx:
        # GET_HW_CODE echo, hardware code 0x0907 and initial HW version 0.
        if raw!=b'\xfd\x09\x07\x00\x00':
            raise RuntimeError('Not the previously observed MT6983 command-ready response')
        report['matched']=True
        return True
    except BaseException as error:
        report.update(error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report.update(reply_hex=raw.hex(),elapsed_seconds=time.monotonic()-started)
        (directory/'command-ready-receipt.json').write_text(json.dumps(report,indent=2)+'\n')

def self_test(directory):
    from queue import Queue
    from types import SimpleNamespace
    directory=Path(directory)
    directory.mkdir(parents=True)
    for index, (reply,good) in enumerate([(b'\xfd\x09\x07\x00\x00',True),
                                         (b'\xfd\x09\x06\x00\x00',False),
                                         (b'\x5f',False),(b'\xfd',False),(b'',False)]):
        path=directory/str(index); path.mkdir()
        calls=[]
        data=bytearray(reply)
        def write(value,timeout): calls.append(value); return len(value)
        def read(count,timeout):
            value=data[:min(count,2)]; del data[:len(value)]; return value
        port=SimpleNamespace(cdc=SimpleNamespace(queue=Queue(),EP_IN=SimpleNamespace(read=read),
                                               EP_OUT=SimpleNamespace(write=write)))
        try: result=identify_ready(port,path)
        except RuntimeError: assert not good
        else: assert good and result
        assert calls==[b'\xfd']
        saved=json.loads((path/'command-ready-receipt.json').read_text())
        assert saved['matched']==good and saved['reply_hex']==reply.hex()
    (directory/'test-results.json').write_text(json.dumps(dict(cases=5,passed=True,phone_contacted=False),indent=2)+'\n')
