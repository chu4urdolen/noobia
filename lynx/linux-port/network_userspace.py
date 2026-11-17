"""Add verified native ARM64 networking tools to a Linux initramfs dictionary."""
import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
from image_formats import require,elf64
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent/'tools/alpine-aarch64/root'
def put(entries,name,data,mode=0o100755):
 for parent in reversed(PurePosixPath(name).parents):
  text=str(parent)
  if text!='.' and text not in entries: entries[text]=dict(mode=0o40755,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=b'')
 entries[name]=dict(mode=mode,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=data)
def add_network_userspace(entries,vm_client=False):
 receipt=json.loads((ROOT.parent/'package-extraction.json').read_text())
 require(receipt['repository_signatures_verified_by_apk'],'Signed package verification missing')
 for record in receipt['packages']:
  p=ROOT.parent/'packages'/record['name']; require(hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256'],'Signed package changed')
 added=[]
 for folder in ['lib','usr/lib']:
  for p in sorted((ROOT/folder).glob('*')):
   if p.is_dir() or '.so' not in p.name: continue
   name=str(p.relative_to(ROOT)); mode=p.lstat().st_mode
   if stat.S_ISLNK(mode): data=os.readlink(p).encode();mode=0o120777
   else:
    data=p.read_bytes(); require(elf64(data)['machine']==183,'Shared library is not ARM64'); mode=0o100755
   put(entries,name,data,mode); added.append(name)
 names=['usr/sbin/dropbear','usr/bin/dropbearkey','sbin/wpa_supplicant','sbin/wpa_cli','usr/bin/nc']
 names+=['usr/bin/dbclient','sbin/ip','usr/sbin/dnsmasq'] if vm_client else []
 iw=next(ROOT.rglob('iw')); names.append(str(iw.relative_to(ROOT)))
 for name in names:
  data=(ROOT/name).read_bytes();require(elf64(data)['machine']==183,'Network executable is not ARM64');put(entries,name,data);added.append(name)
 put(entries,'etc/passwd',b'root:x:0:0:Lynx:/root:/bin/sh\n',0o100644)
 put(entries,'etc/shadow',b'root::0:0:99999:7:::\n',0o100600)
 put(entries,'etc/group',b'root:x:0:\ntty:x:5:\n',0o100644)
 put(entries,'etc/shells',b'/bin/sh\n',0o100644)
 put(entries,'root',b'',0o40700);put(entries,'root/.ssh',b'',0o40700)
 return added
