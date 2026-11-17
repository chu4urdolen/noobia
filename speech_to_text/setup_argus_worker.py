#!/usr/bin/env python3
"""Run on Nexus when Argus is online to install/register its optional STT slot."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def ssh(host, command, code=None):
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=2', host, command], input=code, text=True,
        capture_output=True, check=True).stdout


def main():
    # Do not create or enable a Syra slot until Argus is reachable and ready.
    ssh('argus', 'true')
    public = ssh('rose', 'python3 -', '''
from pathlib import Path
import subprocess
p=Path.home()/'.config/noobia-speech'
p.mkdir(parents=True,exist_ok=True,mode=0o700)
key=p/'argus_ed25519'
if not key.exists():
 subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','rose-argus-transcription','-f',str(key)],check=True)
print(key.with_suffix('.pub').read_text().strip())
''').strip()
    if not public.startswith('ssh-ed25519 '):
        raise ValueError('Unexpected worker public key')
    ssh('argus', 'mkdir -p /noobia/speech_to_text')
    subprocess.run(['scp', '-q', str(ROOT/'decode_engine.py'), str(ROOT/'nexus_worker.py'),
        str(ROOT/'worker_bridge.py'), 'argus:/noobia/speech_to_text/'], check=True)
    install = '''
from pathlib import Path
import json,subprocess
root=Path('/noobia/speech_to_text')
venv=root/'.venv'
if not (venv/'bin/python').exists():
 subprocess.run(['python3','-m','venv','--system-site-packages',str(venv)],check=True)
subprocess.run([str(venv/'bin/python'),'-m','pip','install','--disable-pip-version-check','faster-whisper==1.2.1'],check=True)
auth=Path.home()/'.ssh/authorized_keys'
auth.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
old=auth.read_text() if auth.exists() else ''
key=PUBLIC
if not any(key.split()[1] in line for line in old.splitlines()):
 with auth.open('a') as f:
  if old and not old.endswith('\\n'): f.write('\\n')
  f.write('restrict,command="/usr/bin/python3 /noobia/speech_to_text/worker_bridge.py" '+key+'\\n')
auth.chmod(0o600)
unit=Path.home()/'.config/systemd/user/noobia-transcription-worker.service'
unit.parent.mkdir(parents=True,exist_ok=True)
unit.write_text(UNIT)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','noobia-transcription-worker.service'],check=True)
subprocess.run([str(venv/'bin/python'),'-c','from decode_engine import Decoder; Decoder().prepare()'],cwd=root,check=True)
'''
    unit = (ROOT/'noobia-transcription-worker.service').read_text().replace('Nexus warm', 'Argus warm')
    ssh('argus', 'python3 -', 'PUBLIC='+repr(public)+'\nUNIT='+repr(unit)+'\n'+install)
    host_key = ssh('argus', 'cat /etc/ssh/ssh_host_ed25519_key.pub').split()
    if len(host_key) < 2 or host_key[0] != 'ssh-ed25519':
        raise ValueError('Unexpected Argus host key')
    # Read the verified alias's actual user/address; do not guess credentials.
    config = subprocess.check_output(['ssh', '-G', 'argus'], text=True)
    resolved = dict(line.split(' ', 1) for line in config.splitlines() if ' ' in line)
    address, user = resolved['hostname'], resolved['user']
    ssh('rose', 'python3 -', 'HOST='+repr(address)+'\nUSER='+repr(user)+'\nHOST_KEY='+repr(' '.join(host_key[:2]))+'\n'+'''
from pathlib import Path
import json,subprocess
p=Path.home()/'.config/noobia-speech'
known=p/'argus_known_hosts'
known.write_text(HOST+' '+HOST_KEY+'\\n'); known.chmod(0o600)
config=p/'argus.json'
config.write_text(json.dumps({'name':'Argus','target':USER+'@'+HOST,'identity':str(p/'argus_ed25519'),'known_hosts':str(known)},indent=2)+'\\n')
config.chmod(0o600)
subprocess.run(['systemctl','--user','restart','noobia-speech.service'],check=True)
''')
    print('Argus worker installed and third slot enabled on Syra')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print('Argus setup failed; third slot was not registered. Command exit: '+str(error.returncode), file=sys.stderr)
        sys.exit(1)
