"""Build a private boot_a-only native Wi-Fi candidate offline; never flash."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require,static_aarch64
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import add_network_userspace,put
BASE=Path(__file__).resolve().parent;ROOT=BASE.parent;STOCK=BASE/'artifacts/stock-cph2493-August-eu-ota'
OUT=BASE/'artifacts/busybox-wifi-ssh-twostage-v2'

def main():
 require(not OUT.exists(),'Preserve previous Wi-Fi image')
 base_path=BASE/'artifacts/busybox-usb-module-checkpoints/suppliers/nord3-busybox-candidate.img'
 data=base_path.read_bytes();require(hashlib.sha256(data).hexdigest()=='0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece','Reference changed')
 boot=read_boot_v4(data);entries=read_newc(decompress(boot['ramdisk']))
 original=dict(entries)
 marker=b'\nlynx_load_checkpoint_modules /etc/lynx-checkpoint-modules.load || stop\n'
 require(entries['init']['data'].count(marker)==1,'Reset/module prelude changed')
 init=entries['init']['data'].split(marker)[0].replace(b'export PATH=/bin:/sbin',b'export PATH=/bin:/sbin:/usr/bin:/usr/sbin')
 init+=b'''\n# Manual nodes: exact stock kernel has no devtmpfs.
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
$BB mknod -m 666 /dev/random c 1 8
$BB mknod -m 666 /dev/urandom c 1 9
$BB mount -t tmpfs -o size=32m tmpfs /run || stop
$BB mkdir -p /run/lynx /run/wpa_supplicant /run/tmp /sys/fs/pstore
$BB chmod 700 /run/lynx /run/wpa_supplicant
: > /run/lynx/boot.log
$BB chmod 600 /run/lynx/boot.log
log() {
    IFS=' ' read -r log_uptime log_unused < /proc/uptime
    printf 'LYNX_WIFI uptime=%s %s\\n' "$log_uptime" "$*" >> /run/lynx/boot.log
    printf '<6>LYNX_WIFI uptime=%s %s\\n' "$log_uptime" "$*" > /dev/kmsg
    if [ -c /dev/pmsg0 ]; then printf 'LYNX_WIFI uptime=%s %s\\n' "$log_uptime" "$*" > /dev/pmsg0; fi
    return 0
}
$BB hostname lynx
$BB mdev -s
$BB mkdir -p /dev/pts
$BB mount -t devpts -o newinstance,ptmxmode=0666,mode=0620,gid=5 devpts /dev/pts || log 'DEVPTS_MOUNT_FAILED'
[ -e /dev/ptmx ] || $BB ln -s pts/ptmx /dev/ptmx
$BB mount -t pstore pstore /sys/fs/pstore || log 'PSTORE_MOUNT_UNAVAILABLE'
log "PSTORE_BACKEND_CHECK; records=$($BB ls /sys/fs/pstore 2>/dev/null)"
export TMPDIR=/run/tmp
'''
 init+=(BASE/'lynx-calibration-readonly.sh').read_bytes()+(BASE/'lynx-wifi-runtime.sh').read_bytes()
 init+=b"\nlog 'WIFI_NATIVE_INIT_START'\nlynx_wifi_supervise\nlog 'WIFI_SUPERVISOR_FINISHED; PID1_REMAINS_ALIVE'\nstop\n"
 put(entries,'init',init)
 base_names=entries['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines();require(len(base_names)==33 and 'mtu3.ko' not in base_names,'Base module boundary changed')
 audit=json.loads((BASE/'docs/wifi-boot-module-audit.json').read_text());records={r['name']:r for r in audit['modules']}
 from image_formats import module_metadata
 files={r['name']:Path(r['file']) for r in audit['modules']}
 def direct(name):return records[name]['modinfo_depends']
 storage=[];seen=set(base_names)|{'mtk_wdt.ko','reboot-mode.ko','syscon-reboot-mode.ko'}
 def storage_visit(name):
  if name in seen:return
  for child in dict.fromkeys([*records[name]['dependencies'],*direct(name)]):storage_visit(child)
  seen.add(name);storage.append(name)
 for name in ['phy-mtk-ufs.ko','ufs-mediatek-mod.ko']:storage_visit(name)
 radio=[name for name in audit['module_order'] if name not in seen]
 for name in [*storage,*radio]:
  raw=files[name].read_bytes();require(hashlib.sha256(raw).hexdigest()==records[name]['sha256'],'Stock module changed');put(entries,'lib/modules/'+name,raw,0o100644)
 for stage,names in [('base',base_names),('storage',storage),('radio',radio)]:put(entries,'etc/lynx/wifi-'+stage+'-modules.load',('\n'.join(names)+'\n').encode(),0o100644)
 added_network=add_network_userspace(entries)
 helper=(BASE/'artifacts/wifi-native-helpers/lynx-wifi-control.elf').read_bytes();static_aarch64(helper);put(entries,'bin/lynx-wifi-control',helper)
 put(entries,'bin/lynx-dhcp',(BASE/'lynx-dhcp.sh').read_bytes())
 firmware=STOCK/'wifi-reference/vendor-unpacked/firmware';firmware_records=[]
 for f in sorted(firmware.iterdir()):
  if not f.is_file() or not (f.name.startswith(('soc7_0','WIFI_RAM_CODE_soc7_0')) or f.name=='conninfra.cfg'):continue
  raw=f.read_bytes();put(entries,'lib/firmware/'+f.name,raw,0o100644);firmware_records.append({'name':f.name,'source':str(f),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 require(any(r['name']=='WIFI_RAM_CODE_soc7_0_1_1.bin' for r in firmware_records),'Matching Wi-Fi firmware absent')
 put(entries,'vendor/firmware',b'../lib/firmware',0o120777)
 for name in ['wifi.cfg','wifisar.cfg']:
  raw=(STOCK/'wifi-reference/odm-unpacked/etc/wifi'/name).read_bytes();put(entries,'odm/etc/wifi/'+name,raw,0o100644);put(entries,'lib/firmware/'+name,raw,0o100644)
 private=ROOT/'secrets'
 put(entries,'etc/lynx/wpa_supplicant.conf',(private/'noobia-wpa_supplicant.conf').read_bytes(),0o100600)
 put(entries,'etc/dropbear/lynx_ed25519_host_key',(private/'lynx_ssh_host_ed25519').read_bytes(),0o100600)
 put(entries,'root/.ssh/authorized_keys',(private/'nexus_lynx_ed25519.pub').read_bytes(),0o100600)
 token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644);put(entries,'etc/lynx/host-ip',b'192.168.100.106\n',0o100644)
 put(entries,'etc/lynx/wifi-runtime.sh',(BASE/'lynx-wifi-runtime.sh').read_bytes(),0o100644)
 put(entries,'etc/lynx/calibration-readonly.sh',(BASE/'lynx-calibration-readonly.sh').read_bytes(),0o100644)
 # Base and storage drivers are already loaded by the first-stage bootstrap.
 put(entries,'etc/lynx/wifi-base-modules.load',b'',0o100644)
 put(entries,'etc/lynx/wifi-storage-modules.load',b'',0o100644)
 vendor=read_newc(decompress((STOCK/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
 combined={**vendor,**original}
 supplement={name:entry for name,entry in entries.items() if name!='init' and (name not in combined or entry!=combined[name])}
 require(not any(name in supplement for name in ['bin/busybox','bin/sh','bin/boot-proof-reboot','init']),'Supplement would overwrite a running bootstrap executable')
 payload_archive=decompress(pack(supplement));supplement_gzip=gzip.compress(payload_archive,compresslevel=9,mtime=0)
 supplement_sha=hashlib.sha256(supplement_gzip).hexdigest()
 first={name:dict(item) for name,item in original.items()}
 for name,raw in [('bootstrap-base-modules.load',('\n'.join(base_names)+'\n').encode()),('bootstrap-storage-modules.load',('\n'.join(storage)+'\n').encode()),('payload-bytes',(str(len(supplement_gzip))+'\n').encode()),('payload-sha256',(supplement_sha+'\n').encode())]:put(first,'etc/lynx/'+name,raw,0o100644)
 setup=init.split((BASE/'lynx-calibration-readonly.sh').read_bytes())[0].replace(b'size=32m',b'size=128m')
 setup=setup.replace(b'# Manual nodes:',b'umask 077\n# Manual nodes:')
 init=setup+(BASE/'lynx-boot-payload-readonly.sh').read_bytes()+(BASE/'lynx-wifi-bootstrap-runtime.sh').read_bytes()
 init+=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\nlynx_wifi_bootstrap || stop\n. /etc/lynx/calibration-readonly.sh || stop\n. /etc/lynx/wifi-runtime.sh || stop\nlynx_wifi_supervise\nlog 'WIFI_SUPERVISOR_FINISHED; PID1_REMAINS_ALIVE'\nstop\n"
 put(first,'init',init)
 ramdisk=pack(first);header=bytearray(data[:1584]);struct.pack_into('<I',header,12,len(ramdisk));align=lambda n:(n+4095)//4096*4096
 boot_payload=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
 magic,_,_,coverage,offset,metadata_size=struct.unpack('!4sIIQQQ28x',data[-64:]);require(magic==b'AVBf' and len(boot_payload)<=coverage<=offset,'Bootstrap exceeds preserved metadata boundary')
 image=bytearray(boot_payload.ljust(coverage,b'\0')+data[coverage:]);supplement_offset=24*1024*1024
 require(supplement_offset>=offset+metadata_size and supplement_offset+len(supplement_gzip)<len(image)-64,'Supplement overlaps metadata or footer')
 require(not any(data[supplement_offset:supplement_offset+len(supplement_gzip)]),'Supplement would replace non-padding stock bytes')
 image[supplement_offset:supplement_offset+len(supplement_gzip)]=supplement_gzip
 image=bytes(image)
 require(len(image)==67108864 and read_boot_v4(image)['kernel']==boot['kernel'],'Kernel or geometry changed')
 require(image[offset:offset+metadata_size]==data[offset:offset+metadata_size] and image[-64:]==data[-64:],'OEM metadata bytes changed')
 require(read_newc(decompress(read_boot_v4(image)['ramdisk']))==first,'Bootstrap archive differs')
 require(read_newc(gzip.decompress(bytes(image[supplement_offset:supplement_offset+len(supplement_gzip)])))==supplement,'Supplement archive differs')
 OUT.mkdir(mode=0o700);candidate=OUT/'nord3-busybox-candidate.img';candidate.write_bytes(image);candidate.chmod(0o600)
 (OUT/'supplement.cpio.gz').write_bytes(supplement_gzip);(OUT/'supplement.cpio.gz').chmod(0o600)
 (OUT/'init-source').write_bytes(init);(OUT/'initramfs.cpio.lz4').write_bytes(ramdisk);(OUT/'initramfs.cpio.lz4').chmod(0o600)
 report={'candidate':str(candidate),'candidate_sha256':hashlib.sha256(image).hexdigest(),'kernel_sha256':hashlib.sha256(boot['kernel']).hexdigest(),'init_sha256':hashlib.sha256(init).hexdigest(),'ramdisk_bytes':len(ramdisk),'two_stage':True,'supplement_offset':supplement_offset,'supplement_bytes':len(supplement_gzip),'supplement_sha256':supplement_sha,'supplement_entry_names':list(supplement),'base_modules':base_names,'storage_modules':storage,'radio_modules':radio,'firmware':firmware_records,'network_entries':added_network,'native_helper_sha256':hashlib.sha256(helper).hexdigest(),'session_token':token,'collector_ip':'192.168.100.106','ssh_host_alias':'lynx','password_authentication_disabled':True,'factory_calibration_policy':'Only existing unique nvdata GPT label, block read-only + ext4 ro,noload; copy to RAM; no synthesis or partition write.','fallback_deadline_seconds':240,'phone_contacted':False,'hardware_wifi_verified':False,'flash_eligible':False,'limits':['Not independently validated or flashed.','Warm-reboot pstore backend persistence unverified on hardware.','Module symbol dependencies do not guarantee all platform suppliers are initialized.']}
 (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'image':str(candidate),'sha256':report['candidate_sha256'],'ramdisk_bytes':len(ramdisk),'two_stage':True,'supplement_offset':supplement_offset,'supplement_bytes':len(supplement_gzip),'supplement_sha256':supplement_sha,'supplement_entry_names':list(supplement),'module_count':3+len(base_names)+len(storage)+len(radio)},indent=2))
if __name__=='__main__':main()
