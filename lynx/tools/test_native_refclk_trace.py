"""Load exact UFS dependency closure and register selected probes in isolated QEMU."""
import gzip,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,module_metadata,elf64,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
TARGETS=['ufs_mtk_probe','ufs_mtk_init','ufs_mtk_setup_clocks','ufs_mtk_mphy_power_on','ufs_mtk_setup_ref_clk','ufs_mtk_hce_enable_notify']
def main():
    image=(P/'artifacts/busybox-ufs-registration-only-v1/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=='034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56','Reference changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    merged={**vendor,**entries};byname={}
    for path,item in merged.items():
        if path.startswith('lib/modules/') and path.endswith('.ko'):
            meta=module_metadata(item['data'])['values'];byname[meta['name'][0].replace('-','_')]=(path,item,meta)
    order=[];visiting=set()
    def visit(name):
        if name in order:return
        require(name not in visiting,'Dependency cycle');visiting.add(name)
        path,item,meta=byname[name]
        for text in meta.get('depends',[]):
            for dep in text.split(','):
                if dep:visit(dep.replace('-','_'))
        visiting.remove(name);order.append(name)
    visit('ufs_mediatek_mod')
    raw=byname['ufs_mediatek_mod'][1]['data'];sections=elf64(raw)['sections'];names=sections['.strtab'];functions=set()
    for offset in range(0,len(sections['.symtab']),24):
        index,info,_,section,value,size=struct.unpack_from('<IBBHQQ',sections['.symtab'],offset)
        name=names[index:names.index(b'\0',index)].decode()
        if section and info&15==2:functions.add(name)
    require(set(TARGETS)<=functions,'Selected exact stock symbol missing: '+str(sorted(set(TARGETS)-functions))+'; available UFS candidates: '+str(sorted(n for n in functions if n.startswith('ufs_mtk_') or n.startswith('ufshcd_pltfrm'))))
    init=b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
'''
    rows=[]
    for name in order:
        path,item,meta=byname[name];entries[path]=item
        init+=f'$BB insmod /{path}\nprintf "UFS_VM_LOAD_{name}=%s\\n" "$?"\n'.encode()
        rows.append(dict(name=name,path=path,sha256=hashlib.sha256(item['data']).hexdigest()))
    setup=(P/'ufs-refclk-persistent-trace-setup.sh').read_bytes()
    init+=b'log() { printf "%s\\n" "$*"; }\n'+setup+b'\nlynx_ufs_persistent_trace_setup\nprintf "UFS_VM_TRACE_SETUP=%s\\n" "$?"\n'
    for index,name in enumerate(['refclk-enter', 'before-firmware', 'after-firmware', 'before-request-store', 'after-request-store', 'before-ack-read', 'after-ack-read', 'refclk-return', 'crypto-enter'],1):
        token=entries['etc/lynx/session-token']['data'].decode().strip()
        init+=f"printf 'UFS_VM_ENABLED_{name}=%s\\n' \"$($BB cat /run/lynx/trace/events/lynx_ufs/lx{token}_{index}/enable)\"\n".encode()
    init+=b'''[ -d /sys/bus/platform/drivers/ufshcd-mtk ] && echo UFS_VM_DRIVER_REGISTERED
echo UFS_VM_EVENTS_BEGIN
$BB cat /run/lynx/trace/kprobe_events
$BB cat /run/lynx/trace/error_log
$BB grep 'ufs_mtk_probe' /proc/kallsyms
echo UFS_VM_EVENTS_END
$BB poweroff -f
'''
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-refclk-trace-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root'
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 tp_printk']
    env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    try:result=subprocess.run(command,env=env,capture_output=True,timeout=60);raw=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:raw=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(raw)
    checks={name:('UFS_VM_LOAD_'+name+'=0').encode() in raw for name in order}
    checks.update({name:('UFS_VM_ENABLED_'+name+'=1').encode() in raw for name in ['refclk-enter', 'before-firmware', 'after-firmware', 'before-request-store', 'after-request-store', 'before-ack-read', 'after-ack-read', 'refclk-return', 'crypto-enter']})
    checks['setup_returned']=b'UFS_VM_TRACE_SETUP=0' in raw
    checks.update(driver_registered=b'UFS_VM_DRIVER_REGISTERED' in raw,poweroff=b'reboot: Power down' in raw,no_exception=not any(x in raw for x in [b'Kernel panic',b'Internal error:',b'CFI failure']))
    report=dict(passed=code==0 and all(checks.values()),checks=checks,modules=rows,targets=['refclk-enter', 'before-firmware', 'after-firmware', 'before-request-store', 'after-request-store', 'before-ack-read', 'after-ack-read', 'refclk-return', 'crypto-enter'],setup_source_sha256=hashlib.sha256(setup).hexdigest(),phone_contacted=False,kernel_sha256=hashlib.sha256(boot['kernel']).hexdigest(),limits='Exact stock UFS dependency/module registration and selected kprobe definitions on QEMU without MediaTek DT matching. Does not prove physical probe entry/return or persistent phone logs.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out/'result.json'),**report),indent=2));require(report['passed'],'Native UFS trace registration failed')
if __name__=='__main__':main()
