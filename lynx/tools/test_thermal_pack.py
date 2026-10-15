"""Validate prepared module archive and actual ARM shell refusal paths offline."""
import gzip,hashlib,io,json,os,subprocess,sys,tarfile,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require,module_metadata
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 candidates=sorted((P/'artifacts').glob('thermal-ssh-pack-*/result.json'));F=candidates[-1].parent;m=json.loads((F/'manifest.json').read_text());report=json.loads((F/'result.json').read_text());raw=(F/'thermal-ssh-pack.tar.gz').read_bytes();require(sha(raw)==report['archive_sha256'],'Archive differs');require(not m['live_trial_eligible'] or m.get('trial_scope')==['soc-temperature'],'Pack trial scope differs')
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
  members=t.getmembers();require(all(x.isfile() and not x.name.startswith('/') and '..' not in Path(x.name).parts for x in members),'Unsafe archive path/type');files={x.name:t.extractfile(x).read() for x in members};require(len(files)==len(members),'Duplicate archive entry')
 for line in files['SHA256SUMS'].decode().splitlines():
  digest,name=line.split('  ',1);require(sha(files[name])==digest,'Checksum mismatch: '+name)
 require(files['thermal-step.sh']==(P/'thermal-step.sh').read_bytes(),'Runtime source differs');require(('REVIEW-HOLD' in files)==(not m['live_trial_eligible']),'Hold policy differs')
 for name,row in m['modules'].items():
  data=files['modules/'+row['file']];require(sha(data)==row['sha256'],'Module changed');require(module_metadata(data)['values']['vermagic']==[m['kernel_release']+' SMP preempt mod_unload modversions aarch64'],'Module kernel differs')
 for group,row in m['groups'].items():
  order=row['full_dependency_order'];seen=set()
  for n in order:
   require(set(m['modules'][n]['depends'])<=seen,'Dependency not ordered');seen.add(n)
  require(not row['automatic_loading'],'Automatic loading enabled')
  require(('plans/'+group+'.list' in files)==(not row['review_only']),'Review-only stage exposed')
 syntax=subprocess.run(['sh','-n',str(P/'thermal-step.sh')],capture_output=True);require(syntax.returncode==0,'Shell syntax failed')
 out=P/'artifacts'/('emulated-thermal-pack-guards-'+str(time.time_ns()));out.mkdir(mode=0o700)
 b=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img').read_bytes());e=read_newc(decompress(b['ramdisk']))
 for name,data in files.items():put(e,'fixture/'+name,data,0o100700 if name.endswith('.sh') else 0o100600)
 init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
$BB mkdir -p /run/lynx
$BB cat /proc/modules > /fixture/modules.before
check() {
 name=$1; expected=$2; shift 2
 "$@" > /fixture/check.out 2>&1
 rc=$?
 if [ "$rc" != 0 ] && $BB grep -Fq "$expected" /fixture/check.out; then echo "THERMAL_GUARD_$name=PASS"; else echo "THERMAL_GUARD_$name=FAIL"; $BB cat /fixture/check.out; fi
}
unset SSH_CONNECTION
printf 'fixture hold\\n' > /fixture/REVIEW-HOLD
check HOLD 'preparation-only' $BB sh /fixture/thermal-step.sh --load soc-temperature
check REVIEW_ONLY 'review-only or unknown' $BB sh /fixture/thermal-step.sh --load battery
$BB rm /fixture/REVIEW-HOLD
check NO_SSH 'live SSH session' $BB sh /fixture/thermal-step.sh --load soc-temperature
export SSH_CONNECTION='192.0.2.1 10000 192.0.2.2 22'
printf '%s\\n' mismatch > /run/lynx/host-confirmed
check TOKEN 'boot confirmation mismatch' $BB sh /fixture/thermal-step.sh --load soc-temperature
$BB cp /etc/lynx/session-token /run/lynx/host-confirmed
$BB cp /fixture/manifest.json /fixture/manifest.saved
printf x >> /fixture/manifest.json
check HASH 'pack hash mismatch' $BB sh /fixture/thermal-step.sh --load soc-temperature
$BB cp /fixture/manifest.saved /fixture/manifest.json
# Repair only fixture checksums to reach actual mismatching QEMU DT guard.
(cd /fixture && $BB grep -v '  REVIEW-HOLD$' SHA256SUMS > HASH.NEW && $BB mv HASH.NEW SHA256SUMS)
check DT 'device tree differs' $BB sh /fixture/thermal-step.sh --load soc-temperature
$BB cat /proc/modules > /fixture/modules.after
if $BB cmp -s /fixture/modules.before /fixture/modules.after; then echo THERMAL_NO_MODULE_INSERTION=PASS; fi
$BB poweroff -f
'''
 put(e,'init',init);(out/'init-source').write_bytes(init);(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e))
 q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
 cmd=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
 timedout=False
 try:p=subprocess.run(cmd,env=env,capture_output=True,timeout=50);console=p.stdout+p.stderr;rc=p.returncode
 except subprocess.TimeoutExpired as ex:console=(ex.stdout or b'')+(ex.stderr or b'');rc=None;timedout=True
 (out/'console.log').write_bytes(console);checks={name:('THERMAL_GUARD_'+name+'=PASS').encode() in console for name in ['HOLD','REVIEW_ONLY','NO_SSH','TOKEN','HASH','DT']};checks.update(no_module_insertion=b'THERMAL_NO_MODULE_INSERTION=PASS' in console,clean_poweroff=b'reboot: Power down' in console);result={'passed':rc==0 and not timedout and all(checks.values()),'checks':checks,'archive_sha256':sha(raw),'runtime_sha256':sha(files['thermal-step.sh']),'phone_contacted':False,'physical_probe_tested':False,'exit_code':rc,'timed_out':timedout};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'result.json');print(json.dumps(result,indent=2));require(result['passed'],'Thermal pack checks failed')
if __name__=='__main__':main()
