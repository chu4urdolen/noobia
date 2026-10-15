"""Start collector AFTER approval, then the fixed guarded trial without another gap."""
import json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent
def main():
    out=R/'logs'/('wifi-v18-run-'+str(time.time_ns()));out.mkdir(mode=0o700)
    receipt=out/'result.json';report={'state':'starting','phone_commands':'fixed guarded boot_a-only V14 trial','started_ns':time.time_ns(),'collector_receipt':None}
    def save():receipt.write_text(json.dumps(report,indent=2)+'\n')
    save()
    with (out/'collector.log').open('w') as output:
        collector=subprocess.Popen(['python3',str(R/'tools/lynx_wifi_v18_contact.py'),'--listen','--seconds','660'],stdout=output,stderr=subprocess.STDOUT)
        report['collector_pid']=collector.pid;save()
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if collector.poll() is not None:raise RuntimeError('Collector stopped: '+(out/'collector.log').read_text())
                lines=(out/'collector.log').read_text().splitlines()
                paths=[Path(s.removeprefix('LISTENER READY: ')) for s in lines if s.startswith('LISTENER READY: ')]
                if len(paths)==1:
                    path=paths[0].resolve()
                    if not path.is_relative_to((R/'logs').resolve()):raise ValueError('Unexpected collector path')
                    current=json.loads(path.read_text())
                    if current.get('state')=='listening':break
                time.sleep(.1)
            else:raise RuntimeError('Collector readiness deadline; no trial launched')
            report.update(state='trial-active',collector_receipt=str(path),trial_started_ns=time.time_ns());save()
            print('SYNCHRONIZED COLLECTOR READY:',path,flush=True)
            p=subprocess.run(['python3',str(R/'tools/lynx_boot_a_wifi_v18_trial.py'),'--flash-linux','--reboot','--network-receipt',str(path)])
            report.update(state='trial-returned',trial_exit_code=p.returncode,trial_finished_ns=time.time_ns());save()
            current=json.loads(path.read_text())
            if current.get('native_ssh_verified') and current.get('fallback_cancel_ack_exit_code')==0:
                try:collector.wait(timeout=90)
                except subprocess.TimeoutExpired:report['diagnostic_collection_deadline']=True
            if p.returncode:raise RuntimeError('Trial returned failure; inspect its durable receipt before retrying')
        except BaseException as error:
            report.update(state='launcher-error',error=repr(error));save();raise
        finally:
            if collector.poll() is None:
                collector.terminate()
                try:collector.wait(timeout=5)
                except subprocess.TimeoutExpired:collector.kill();collector.wait()
            report.update(collector_exit_code=collector.returncode,finished_ns=time.time_ns());save()
    print('RUN RECEIPT:',receipt,flush=True)
if __name__=='__main__':main()
