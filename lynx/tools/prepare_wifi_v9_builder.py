"""Preserve the unflashed v8 archive; retain gzip for userspace supplementary payload."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
s=(P/'prepare_wifi_v8_image.py').read_text().replace('import hashlib,json,secrets,struct','import gzip,hashlib,json,secrets,struct').replace('busybox-wifi-ssh-twostage-v8','busybox-wifi-ssh-twostage-v9').replace('    payload=pack(extra)','    payload=gzip.compress(decompress(pack(extra)),mtime=0)')
out=P/'prepare_wifi_v9_image.py';assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
