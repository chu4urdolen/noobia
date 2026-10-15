"""Inspect archive parent paths and symlinks; never print credentials or regular-file contents."""
import hashlib,json,sys,time
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_newc,read_boot_v4
from ramdisk_codec import decompress
stock=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
boot=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v9/nord3-busybox-candidate.img').read_bytes())
first=read_newc(decompress(boot['ramdisk']))
extra=read_newc(decompress((P/'artifacts/busybox-wifi-ssh-twostage-v9/supplement.cpio.gz').read_bytes()))
base={**stock,**first}
parents=set()
for name in extra:
    parents.update(str(p) for p in PurePosixPath(name).parents if str(p)!='.')
rows=[]
for name in sorted(parents):
    if name in base:
        item=base[name];row={'path':name,'mode':oct(item['mode'])}
        if item['mode']&0o170000==0o120000:
            row['symlink_target']=item['data'].decode();row['target_literal_entry_exists']=item['data'].decode().lstrip('/') in base
        rows.append(row)
report={'phone_contacted':False,'regular_file_contents_printed':False,'parents_present_in_stock_root':rows,'limits':'Literal archive metadata; does not prove final kernel mounts or fully resolve symlink chains.'}
out=P/'docs'/('payload-stock-root-parent-audit-'+str(time.time_ns())+'.json')
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'receipt':str(out),**report},indent=2))
