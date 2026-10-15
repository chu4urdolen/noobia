"""Start a verified ready collector immediately before the scoped Wi-Fi trial."""
import json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;T=ROOT/'tools'
def main():
    out=ROOT/'logs'/('wifi-v5-run-'+str(time.time_ns()));out.mkdir(mode=0o700)
    report={'started_ns':time.time_ns(),'started_monotonic':time.monotonic(),'state':'preparing','collector_ready':False,'trial_issued':False}
    path=out/'result.json'
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(path)
    save()
    validated=subprocess.run(['python3',str(T/'validate_wifi_v5_image.py')],capture_output=True,text=True,timeout=30)
    (out/'validation.raw').write_text(validated.stdout+validated.stderr)
    if validated.returncode:raise RuntimeError('Offline candidate validation failed; no phone contacted')
    prior=set((ROOT/'logs').glob('wifi-v5-contact-*/result.json'));trials=set((ROOT/'logs').glob('boot-a-wifi-v5-trial-*.json'))
    collector=None
    try:
        with (out/'collector.raw').open('wb') as capture:
            collector=subprocess.Popen(['python3',str(T/'lynx_wifi_v5_contact.py'),'--listen','--seconds','900'],stdout=capture,stderr=subprocess.STDOUT)
            report['collector_pid']=collector.pid;save();deadline=time.monotonic()+15;receipt=None
            while time.monotonic()<deadline:
                if collector.poll() is not None:raise RuntimeError('Collector exited before ready; no phone contacted')
                fresh=set((ROOT/'logs').glob('wifi-v5-contact-*/result.json'))-prior
                if len(fresh)>1:raise RuntimeError('Ambiguous new collector receipts; no phone contacted')
                if fresh:
                    candidate=next(iter(fresh));status=json.loads(candidate.read_text())
                    if status.get('state')=='listening' and time.time_ns()-status.get('heartbeat_ns',0)<2_000_000_000:receipt=candidate;break
                time.sleep(.1)
            if receipt is None:raise RuntimeError('Collector readiness deadline; no phone contacted')
            report.update(collector_ready=True,collector_receipt=str(receipt),state='collector-ready');save();print('NETWORK COLLECTOR READY:',receipt,flush=True)
            report.update(trial_issued=True,trial_started_ns=time.time_ns(),trial_started_monotonic=time.monotonic(),state='trial-running');save()
            trial=subprocess.run(['python3',str(T/'lynx_boot_a_wifi_v5_trial.py'),'--flash-linux','--reboot','--network-receipt',str(receipt)],stdout=None,stderr=None)
            report['trial_exit_code']=trial.returncode;report['trial_finished_ns']=time.time_ns();report['trial_elapsed_seconds']=time.monotonic()-report['trial_started_monotonic']
            new_trials=set((ROOT/'logs').glob('boot-a-wifi-v5-trial-*.json'))-trials
            report['trial_receipts']=[str(p) for p in sorted(new_trials)]
            if len(new_trials)==1:
                result=json.loads(next(iter(new_trials)).read_text());report.update(native_ssh_verified=result.get('native_ssh_verified',False),fastboot_return_observed=result.get('fastboot_return_observed'),stock_undo_pending=result.get('stock_undo_pending'))
            report['state']='trial-finished';save()
            if report.get('native_ssh_verified'):
                try:collector.wait(timeout=120)
                except subprocess.TimeoutExpired:report['diagnostic_collection_wait_expired']=True;save()
            print('RUN RECEIPT:',path,flush=True)
    finally:
        if collector is not None and collector.poll() is None:
            collector.terminate()
            try:collector.wait(timeout=5)
            except subprocess.TimeoutExpired:collector.kill();collector.wait()
        report.update(finished_ns=time.time_ns(),elapsed_seconds=time.monotonic()-report['started_monotonic']);save()
if __name__=='__main__':main()
