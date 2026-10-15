"""Extract matching OTA Wi-Fi reference partitions locally; never access a phone."""
import base64, hashlib, inspect, json, struct, sys, time, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PROJECT=ROOT/'linux-port'
sys.path.insert(0,str(PROJECT))
import ota_payload
from ota_payload import parse_header,parse_manifest
# Preserve the reviewed parser; change only the selected partition size limit.
source=inspect.getsource(ota_payload.reconstruct)
assert source.count('size <= 67108864')==1
source=source.replace('size <= 67108864','size <= 2147483648')
namespace=dict(vars(ota_payload)); exec(source,namespace)
reconstruct=namespace['reconstruct']
stock=PROJECT/'artifacts/stock-cph2493-August-eu-ota'
out=stock/'wifi-reference'
out.mkdir(exist_ok=True)
(out/'reconstruction-source.py').write_text(source)
receipt=out/('extraction-'+str(time.time_ns())+'.json')
report={'phone_contacted':False,'partition_writes_allowed':False,'operations':[],'state':'started'}
def save(): receipt.write_text(json.dumps(report,indent=2)+'\n')
save()
try:
 integrity=json.loads((ROOT/'downloads/august-eu-ota-integrity.json').read_text())
 signature=json.loads((ROOT/'downloads/august-eu-payload-signature.json').read_text())
 assert integrity['state']=='verified' and signature['full_payload_signature_valid']
 archive=Path(integrity['archive']); assert archive.stat().st_size==integrity['archive_bytes']
 with zipfile.ZipFile(archive) as z, archive.open('rb') as f:
  info=z.getinfo('payload.bin'); assert info.compress_type==0
  f.seek(info.header_offset); header=f.read(30); assert header[:4]==b'PK\x03\x04'
  a,b=struct.unpack_from('<HH',header,26); offset=info.header_offset+30+a+b
  f.seek(offset); manifest_size,sig_size=parse_header(f.read(24)); f.seek(offset)
  metadata=f.read(24+manifest_size)
  props=dict(line.split('=',1) for line in (stock/'payload_properties.txt').read_text().splitlines())
  assert hashlib.sha256(metadata).digest()==base64.b64decode(props['METADATA_HASH'])
  block,parts=parse_manifest(metadata[24:]); base=offset+24+manifest_size+sig_size
  def fetch(start,length):
   assert start>=0 and base+start+length<=offset+info.file_size
   f.seek(base+start); data=f.read(length); assert len(data)==length
   return data
  for name in ['vendor_dlkm','odm_dlkm','vendor','odm']:
   p=parts[name]; target=out/(name+'.img')
   record={'partition':name,'bytes':p['size'],'sha256':p['hash'].hex(),'state':'started','started_ns':time.time_ns()}
   report['operations'].append(record); save()
   if target.exists():
    assert target.stat().st_size==p['size'] and hashlib.sha256(target.read_bytes()).digest()==p['hash']
    record['state']='existing-verified'
   else:
    data=reconstruct(p,block,fetch); partial=out/(name+'.partial'); assert not partial.exists()
    partial.write_bytes(data); partial.rename(target); del data
    record['state']='extracted-verified'
   record['completed_ns']=time.time_ns(); save(); print(name,record['state'],record['bytes'],flush=True)
 report['state']='complete'; save(); print('Receipt:',receipt,flush=True)
except Exception as e:
 report['state']='failed'; report['error']=repr(e); save(); raise
