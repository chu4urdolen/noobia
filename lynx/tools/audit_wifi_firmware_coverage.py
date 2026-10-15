"""Inventory stock firmware versus the Linux payload and exact driver literals."""
import gzip,hashlib,json,re,stat,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_newc
F=P/'artifacts/busybox-wifi-ssh-twostage-v15';S=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference'
x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()));embedded={n.removeprefix('lib/firmware/'):hashlib.sha256(v['data']).hexdigest() for n,v in x.items() if n.startswith('lib/firmware/') and stat.S_ISREG(v['mode'])}
files=[]
for tree in ['vendor-unpacked','odm-unpacked']:
    for folder in ['firmware','etc/firmware']:
        root=S/tree/folder
        if not root.is_dir():continue
        for f in sorted(root.rglob('*')):
            if not stat.S_ISREG(f.lstat().st_mode):continue
            raw=f.read_bytes();rel=str(f.relative_to(root));digest=hashlib.sha256(raw).hexdigest()
            files.append({'file':str(f),'relative':rel,'bytes':len(raw),'sha256':digest,'embedded_same_path':embedded.get(rel)==digest})
literals={}
for name in ['conninfra.ko','wmt_chrdev_wifi_connac2.ko','wlan_drv_gen4m_6983.ko']:
    raw=(S/'vendor-dlkm-unpacked/lib/modules'/name).read_bytes()
    values=sorted(set(v.decode() for v in re.findall(rb'[A-Za-z0-9_./%+-]+\.(?:bin|cfg|dat|txt)',raw)))
    literals[name]=values
missing=[v for v in files if not v['embedded_same_path'] and any(v['relative'] in items or Path(v['relative']).name in items for items in literals.values())]
out=P/'docs'/('wifi-firmware-coverage-'+str(time.time_ns())+'.json');out.write_text(json.dumps({'phone_contacted':False,'embedded':embedded,'stock_files':files,'driver_filename_literals':literals,'unembedded_literal_matches':missing,'limits':'Filename literals may be formatted templates or unused code. Firmware-loader stack proves a sampled wait, not which filename was requested.'},indent=2)+'\n')
print(json.dumps({'report':str(out),'embedded_files':len(embedded),'stock_files':len(files),'stock_total_bytes':sum(v['bytes'] for v in files),'missing_literal_matches':[v['relative'] for v in missing]},indent=2))
