"""Bounded native ACM console capture and read-only shell check for Lynx."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time

ROOT=Path(__file__).resolve().parent.parent
COMMAND=b"printf '\\nLYNX_CHECK_BEGIN\\n'; uname -m; printf 'LYNX_PID1_COMM='; cat /proc/1/comm; id; printf '\\nLYNX_CHECK_END\\n'\n"

def identified_ports():
    result=[]
    for tty in Path('/sys/class/tty').glob('ttyACM*'):
        device=(tty/'device').resolve()
        for parent in [device,*device.parents]:
            try:
                if ((parent/'idVendor').read_text().strip(),(parent/'idProduct').read_text().strip(),
                    (parent/'serial').read_text().strip())==('1d6b','0104','lynx-busybox'):
                    result.append('/dev/'+tty.name)
                    break
            except OSError:continue
    return result

def complete(data):
    return bool(re.search(rb'(?:^|\n)LYNX_CHECK_END\r?\n',data))

def self_test():
    echo=COMMAND+b'\r\n'
    assert not complete(echo)
    reply=b'\r\nLYNX_CHECK_BEGIN\r\naarch64\r\nLYNX_PID1_COMM=init\r\nuid=0(root)\r\n\r\nLYNX_CHECK_END\r\n'
    for width in [1,2,7,512]:
        received=bytearray(echo)
        for index in range(0,len(reply),width):
            received.extend(reply[index:index+width])
            if index+width<len(reply):assert not complete(received)
        assert complete(received)
    print('Console completion parsing passed fragmented replies and command-echo rejection; no device contacted.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--connect',action='store_true')
    actions.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:self_test();return
    if not args.connect:
        print(json.dumps(dict(phone_contacted=False,required_usb='1d6b:0104',required_serial='lynx-busybox',
                             deadline_seconds=120,partition_writes=False,commands=COMMAND.decode()),indent=2));return
    import serial
    output=ROOT/'logs'/('busybox-console-'+str(time.time_ns()))
    report=dict(state='waiting',partition_writes=False,command_sent=False,process_id=os.getpid(),
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    receipt=output.with_suffix('.json')
    def save():
        report['heartbeat_ns']=time.time_ns()
        receipt.write_text(json.dumps(report,indent=2)+'\n')
        (ROOT/'logs/busybox-console-active.json').write_text(json.dumps(dict(receipt=str(receipt),**report),indent=2)+'\n')
    def expired(*unused):raise TimeoutError('Console deadline expired')
    signal.signal(signal.SIGALRM,expired);signal.alarm(125)
    started=time.monotonic();data=bytearray();port=None
    save();print('Native BusyBox console recorder waiting; receipt:',receipt,flush=True)
    try:
        with output.with_suffix('.raw.bin').open('wb',buffering=0) as raw:
            while time.monotonic()-started<120:
                if time.time_ns()-report['heartbeat_ns']>1_000_000_000:save()
                if port is None:
                    ports=identified_ports()
                    if len(ports)>1:raise RuntimeError('Multiple matching native consoles; refusing ambiguity')
                    if not ports:time.sleep(0.25);continue
                    port=serial.Serial(ports[0],115200,timeout=0.25,write_timeout=2)
                    report.update(state='connected',port=ports[0]);save()
                    print('Matched native ACM console; capturing raw output.',flush=True)
                chunk=port.read(4096)
                if not chunk:continue
                raw.write(chunk);data.extend(chunk)
                if len(data)>32*1024*1024:raise RuntimeError('Console capture size bound reached')
                if not report['command_sent'] and b'LYNX_NATIVE_BUSYBOX_SHELL' in data:
                    report.update(state='native-banner-seen',command_sent=True,command=COMMAND.decode());save()
                    if port.write(COMMAND)!=len(COMMAND):raise RuntimeError('Partial smoke-check command write')
                if report['command_sent'] and complete(data):
                    report.update(state='shell-check-complete',
                                  aarch64_observed=bool(re.search(rb'(?:^|\n)aarch64\r?\n',data)),
                                  root_observed=b'uid=0(' in data or b'uid=0 ' in data,
                                  pid1_comm=re.findall(rb'LYNX_PID1_COMM=([^\r\n]+)',data)[-1].decode(errors='replace'))
                    break
            else:report['state']='deadline'
    except BaseException as error:
        report.update(state='stopped',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        signal.alarm(0)
        if port is not None:port.close()
        report.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),elapsed_seconds=time.monotonic()-started)
        save()
    print('Console result:',report['state'],'receipt:',receipt,flush=True)
    if report['state']!='shell-check-complete' or not report.get('aarch64_observed') or not report.get('root_observed'):
        raise SystemExit(1)

if __name__=='__main__':main()
