"""Check the exact Git-visible Lynx files without printing credential values."""
import hashlib,json,re,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;repo=R.parent
def main():
 p=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard','--','lynx'],cwd=repo,capture_output=True,check=True)
 names=sorted(set(n.decode() for n in p.stdout.split(b'\0') if n));issues=[];needles=[]
 for secret in (R/'secrets').glob('*'):
  if not secret.is_file():continue
  raw=secret.read_bytes()
  if len(raw)>=16:needles.append(raw)
  if b'PRIVATE KEY' in raw:
   needles.extend(line for line in raw.splitlines() if len(line)>40 and not line.startswith(b'-----'))
  if 'wpa_supplicant' in secret.name:
   for value in re.findall(rb'^\s*psk=(.+)$',raw,re.M):
    value=value.strip().strip(b'"')
    if len(value)>=12:needles.append(value)
 records=[]
 forbidden={'secrets','checkpoints','artifacts','downloads','logs','migration','sources','test-artifacts','__pycache__'}
 for name in names:
  f=repo/name
  if f.is_symlink():issues.append({'file':name,'reason':'symlink requires explicit review'});continue
  data=f.read_bytes();records.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
  if forbidden.intersection(f.relative_to(R).parts):issues.append({'file':name,'reason':'private or downloaded path'})
  if len(data)>2*1024*1024 or b'\0' in data:issues.append({'file':name,'reason':'oversized or binary data'})
  try:data.decode('utf-8')
  except UnicodeDecodeError:issues.append({'file':name,'reason':'non-UTF8 data'})
  if any(needle in data for needle in needles):issues.append({'file':name,'reason':'matches local secret material'})
 out=R/'logs'/('publication-audit-'+str(time.time_ns())+'.json');report={'passed':not issues,'files':len(names),'bytes':sum(r['bytes'] for r in records),'issues':issues,'inventory':records,'checks':'Exact local secret values and private-key body lines; path allowlist and text/size checks. No secret values emitted.'};out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o600)
 print(json.dumps({k:report[k] for k in ['passed','files','bytes','issues']},indent=2));print(out)
 if issues:raise SystemExit(1)
if __name__=='__main__':main()
