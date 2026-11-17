"""Read fixed charger device-tree properties on verified V46 Lynx."""

import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
PROPS = ('chg_tmr', 'chg_tmr_en', 'te_en', 'wdt', 'cv', 'ichg', 'ieoc',
         'vbus_ov', 'mivr', 'aicr', 'vrec', 'boot_mode')


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-charger-dt-{time.time_ns()}'
    out.mkdir(mode=0o700)
    remote = '''import json
from pathlib import Path
boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
root=Path('/sys/firmware/devicetree/base/i2c@11e01000/mt6375@34/chg')
props={}
for name in PROPS:
    path=root/name
    if not path.is_file():
        props[name]={'present':False}
        continue
    data=path.read_bytes()
    if len(data)>32: raise ValueError('Property too large')
    props[name]={'present':True,'bytes_hex':data.hex(),
                 'uint_be':int.from_bytes(data,'big') if len(data)==4 else None,
                 'boolean_node':len(data)==0}
print(json.dumps({'boot_id':boot_id,'properties':props}))
'''.replace('PROPS', repr(PROPS))
    argv = ssh_command(IP, 'python3 -')
    argv[-2:-2] = ['-p', '2222']
    run = subprocess.run(argv, input=remote.encode(), capture_output=True, timeout=20)
    (out / 'stdout').write_bytes(run.stdout)
    (out / 'stderr').write_bytes(run.stderr)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'phone_ip': IP,
              'phone_writes': False, 'exit_code': run.returncode}
    try:
        data = json.loads(run.stdout)
        if run.returncode or data.get('boot_id') != BOOT_ID or set(data.get('properties', {})) != set(PROPS):
            raise ValueError('Charger DT read incomplete or wrong boot')
        report.update(state='v46-charger-dt-readonly-captured',
                      properties=data['properties'])
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'properties': report.get('properties')}))
    if report['state'] != 'v46-charger-dt-readonly-captured':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
