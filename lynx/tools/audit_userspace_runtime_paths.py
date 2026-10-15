"""Audit runtime-directory creation and exact CLI socket-path literals offline."""
import gzip,hashlib,json,re,stat,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc
from ramdisk_codec import decompress
F=P/'artifacts/busybox-wifi-ssh-twostage-v18';e=read_newc(decompress(read_boot_v4((F/'nord3-busybox-candidate.img').read_bytes())['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()));v=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));merged={**v,**e,**x}
paths=['tmp','var','var/run','run','run/wpa_supplicant','dev/urandom','root/.ssh'];inventory={n:({'mode':oct(merged[n]['mode']),'symlink_target':merged[n]['data'].decode(errors='replace') if stat.S_ISLNK(merged[n]['mode']) else None} if n in merged else None) for n in paths}
literals=[s.decode() for s in re.findall(rb'[\x20-\x7e]{4,}',x['sbin/wpa_cli']['data']) if b'/tmp' in s or b'wpa_ctrl_' in s]
creation=[]
for name,raw in [('init',e['init']['data']),('wifi-runtime.sh',x['etc/lynx/wifi-runtime.sh']['data'])]:creation.extend(name+':'+line for line in raw.decode().splitlines() if 'mkdir' in line or 'mount -t tmpfs' in line)
out=P/'docs'/('userspace-runtime-path-audit-'+str(time.time_ns())+'.json');report={'phone_contacted':False,'paths':inventory,'wpa_cli_socket_literals':literals,'runtime_creation':creation,'limits':'Static merged archives and named init scripts. Runtime processes may create additional directories.'};out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(out),**report},indent=2))
