"""Record Noob's explicit answer for the two trials named in the pending question."""
import json,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
RECEIPTS=['boot-a-core-probe-trial-1791907590015628810.json','boot-a-match-profile-trial-1791909079698893610.json']


def main():
    paths=[ROOT/'logs'/name for name in RECEIPTS]
    for path in paths:
        receipt=json.loads(path.read_text());assert receipt.get('fastboot_return_observed'),'Trial did not record a return'
    report={'recorded_ns':time.time_ns(),'source':'Noob, explicit conversation reply',
            'confirmed':True,'receipts':[str(path) for path in paths],
            'statement':'Yes she did. I do not touch anything, just press proceed; I am working on another computer.',
            'question':'Did Lynx return to Fastboot on her own during the last two trials, with no button presses or USB cable changes?',
            'phone_contacted':False,'limits':'User confirmation of physical non-interference. Does not authenticate internal trace contents or prove storage or networking works.'}
    path=ROOT/'logs'/('physical-noninterference-'+str(report['recorded_ns'])+'.json')
    path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
