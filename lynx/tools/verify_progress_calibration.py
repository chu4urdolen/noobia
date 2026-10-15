"""Bind known-field0 timing to matching read-only software-reset evidence."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SHA='465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--trial',type=Path,required=True);parser.add_argument('--reset',type=Path,required=True);args=parser.parse_args()
    trial=json.loads(args.trial.read_text());reset=json.loads(args.reset.read_text())
    assert trial.get('fastboot_return_observed') and trial.get('baseline_range_plausible')
    assert trial['images'][0]['sha256']==SHA and all(op.get('exit_code')==0 for op in trial['operations'])
    raw=Path(reset['raw_file']).read_bytes();assert reset['exit_code']==0 and hashlib.sha256(raw).hexdigest()==reset['raw_sha256']
    cleaned=Path(reset['raw_file'].replace('.raw.txt','.clean.txt')).read_text()
    assert 'rst from: lk' in cleaned and re.search(r'NONRST_REG2:\s+0x28002003',cleaned) and re.search(r'wdt_status:\s+0x2',cleaned)
    baseline=trial['timing_baseline_candidate_seconds'];assert 10<=baseline<=40
    out=ROOT/'linux-port/docs/progress-debug-calibration.json';assert not out.exists(),'Preserve previous calibration'
    report={'passed':True,'baseline_seconds':baseline,'calibration_image_sha256':SHA,'trial_receipt':str(args.trial),'reset_receipt':str(args.reset),'limits':'Known-field0 timing with matching reset evidence; conditional on the user leaving handset untouched. No storage or Wi-Fi proof.'}
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'calibration':str(out),'baseline_seconds':baseline},indent=2))
if __name__=='__main__':main()
