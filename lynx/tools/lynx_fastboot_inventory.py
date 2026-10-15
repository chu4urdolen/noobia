"""Preserve Fastboot getvar all after Lynx's fixed identity/slot checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from lynx_pllk_log import ROOT, FASTBOOT, SERIAL, EXPECTED_FASTBOOT

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect',action='store_true')
    args=parser.parse_args()
    command=[str(FASTBOOT),'-s',SERIAL,'getvar','all']
    if not args.connect:
        print(json.dumps(dict(command=command,phone_contacted=False,writes_allowed=False),indent=2))
        return
    if hashlib.sha256(FASTBOOT.read_bytes()).hexdigest()!=EXPECTED_FASTBOOT:
        raise RuntimeError('Pinned Fastboot executable changed')
    output=ROOT/'logs'/('fastboot-inventory-'+str(time.time_ns()))
    report=dict(command=command,writes_allowed=False,state='preflight',
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limits='Variables may omit dump settings and do not prove Linux startup or a read-only dump path.')
    receipt=output.with_suffix('.json')
    receipt.write_text(json.dumps(report,indent=2)+'\n')
    try:
        preflight=subprocess.run(['python3',str(ROOT/'tools/lynx_fastboot_preflight.py'),'--connect'],
                                 capture_output=True,timeout=120)
        output.with_suffix('.preflight.stdout.txt').write_bytes(preflight.stdout)
        output.with_suffix('.preflight.stderr.txt').write_bytes(preflight.stderr)
        if preflight.returncode:
            raise RuntimeError('Lynx identity/slot preflight failed; getvar all not issued')
        report['preflight']=json.loads(preflight.stdout)
        report['state']='query-issued'
        receipt.write_text(json.dumps(report,indent=2)+'\n')
        try:
            process=subprocess.run(command,capture_output=True,timeout=20)
            stdout,stderr=process.stdout,process.stderr
            report.update(state='returned',exit_code=process.returncode)
        except subprocess.TimeoutExpired as error:
            stdout,stderr=error.stdout or b'',error.stderr or b''
            report.update(state='timeout',exit_code=None)
        for label,data in [('stdout',stdout),('stderr',stderr)]:
            path=output.with_suffix('.'+label+'.txt');path.write_bytes(data)
            report[label]=dict(file=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    except BaseException as error:
        report.update(state='stopped',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        receipt.write_text(json.dumps(report,indent=2)+'\n')
    print('Inventory preserved:',receipt)
    if report.get('exit_code')!=0:raise SystemExit(1)

if __name__=='__main__':main()
