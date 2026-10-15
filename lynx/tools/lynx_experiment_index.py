"""Build a durable receipt index without querying the phone or exposing secrets."""
import datetime
import json
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def main():
    rows=[];errors=[];writes=[]
    confirmed={}
    for path in (ROOT/'logs').glob('physical-noninterference-*.json'):
        try:
            confirmation=json.loads(path.read_text())
            if confirmation.get('confirmed') and confirmation.get('source')=='Noob, explicit conversation reply':
                for receipt_path in confirmation['receipts']: confirmed[receipt_path]=str(path)
        except (OSError,ValueError,KeyError) as error:
            errors.append({'receipt':str(path),'error':str(error)})
    for path in sorted((ROOT/'logs').glob('boot-a-*.json')):
        try:
            receipt=json.loads(path.read_text())
        except (OSError,ValueError) as error:
            errors.append({'receipt':str(path),'error':str(error)});continue
        operations=receipt.get('operations',[])
        relevant=[]
        for item in operations:
            command=item.get('command',[])
            if len(command)>=6 and command[3:5]==['flash','boot_a']:
                relevant.append(item)
                writes.append({'receipt':str(path),'started_ns':item.get('started_ns',0),
                               'mode':receipt.get('mode'),'file':command[5],
                               'state':item.get('state'),'exit_code':item.get('exit_code')})
        if not relevant:continue
        started=min(item.get('started_ns',0) for item in relevant)
        row={'receipt':str(path),'started_ns':started,
             'started_utc':datetime.datetime.fromtimestamp(started/1e9,datetime.timezone.utc).isoformat(),
             'mode':receipt.get('mode'),'writes':[{'state':item.get('state'),'exit_code':item.get('exit_code'),'elapsed_seconds':item.get('elapsed_seconds')} for item in relevant],
             'reboot_accepted':any(item.get('command',[])[3:]==['reboot'] and item.get('exit_code')==0 for item in operations),
             'fastboot_return_observed':receipt.get('fastboot_return_observed'),
             'return_seconds_after_reboot':receipt.get('return_seconds_after_reboot'),
             'timing_code_hex':receipt.get('timing_nearest_code_hex'),
             'timing_residual_seconds':receipt.get('timing_residual_seconds'),
             'timing_inferred_outcome':receipt.get('timing_inferred_outcome'),
             'timing_kernel_log_mask':receipt.get('timing_kernel_log_mask'),
             'timing_kernel_log_indications':receipt.get('timing_kernel_log_indications'),
             'producer_platform_return_gate':receipt.get('producer_platform_return_gate'),
             'native_ssh_verified':receipt.get('native_ssh_verified',False),
             'physical_noninterference_confirmed':receipt.get('physical_noninterference_confirmed',False) or str(path) in confirmed,
             'physical_confirmation_receipt':confirmed.get(str(path)),
             'usb_observer_receipt':receipt.get('usb_observer_receipt')}
        rows.append(row)
    rows.sort(key=lambda row:row['started_ns']);writes.sort(key=lambda row:row['started_ns'])
    latest=writes[-1] if writes else None
    if latest and latest['state']=='returned' and latest['exit_code']==0:
        installation={'state':'last Fastboot-accepted write','image':latest['file'],'mode':latest['mode'],'receipt':latest['receipt']}
    else:
        installation={'state':'unknown or write in progress','latest_attempt':latest}
    report={'generated_ns':time.time_ns(),'phone_contacted':False,'receipts':rows,'parse_errors':errors,
            'boot_a_installation':installation,
            'limits':'Receipt-derived state, not partition readback. Timing remains conditional on physical non-interference and reset evidence. Omitted confirmation is not consent or proof.'}
    path=ROOT/'linux-port/docs/EXPERIMENT-INDEX.json'
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(path)
    print(json.dumps({'index':str(path),'indexed_receipts':len(rows),'parse_errors':len(errors),'boot_a_installation':installation},indent=2))


if __name__=='__main__':main()
