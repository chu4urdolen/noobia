"""Bootstrap official Alpine apk verifier locally; no host installation or phone I/O."""
import gzip,hashlib,io,json,tarfile,urllib.request
from pathlib import Path
ROOT=Path('/noobia/lynx/tools/alpine-bootstrap'); ROOT.mkdir(exist_ok=True)
base='https://dl-cdn.alpinelinux.org/alpine/v3.22/main/x86_64/'
records=[]
def fetch(name):
 data=urllib.request.urlopen(base+name,timeout=60).read(); (ROOT/name).write_bytes(data)
 records.append({'url':base+name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}); return data
index=fetch('APKINDEX.tar.gz')
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(index)),mode='r:',ignore_zeros=True) as t:
 content=t.extractfile('APKINDEX').read().decode()
packages={}
for stanza in content.split('\n\n'):
 fields=dict(line.split(':',1) for line in stanza.splitlines() if ':' in line)
 if 'P' in fields: packages[fields['P']]=fields
for name in ['apk-tools-static','alpine-keys']:
 filename=name+'-'+packages[name]['V']+'.apk'; data=fetch(filename)
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(data)),mode='r:',ignore_zeros=True) as t:
  for m in t.getmembers():
   path=m.name.lstrip('./')
   if (path=='sbin/apk.static' or path.startswith('etc/apk/keys/')) and m.isfile():
    target=ROOT/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(t.extractfile(m).read()); target.chmod(0o755 if path=='sbin/apk.static' else 0o644)
(ROOT/'bootstrap-provenance.json').write_text(json.dumps({'records':records,'trust':'Initial verifier and trust keys bootstrapped over HTTPS from official Alpine CDN. Subsequent APK fetches must verify repository signatures with these keys.','phone_contacted':False},indent=2)+'\n')
(ROOT/'repositories').write_text('https://dl-cdn.alpinelinux.org/alpine/v3.22/main\nhttps://dl-cdn.alpinelinux.org/alpine/v3.22/community\n')
print(ROOT/'sbin/apk.static')
