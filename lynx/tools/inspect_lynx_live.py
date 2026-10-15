"""Read-only inventory for storage/rootfs and power planning after SSH bring-up."""
import hashlib,json,subprocess,time,os
from pathlib import Path
from lynx_wifi_v19_contact import ssh_command,PROOF,proof_valid
R=Path(__file__).resolve().parent.parent
SCRIPT=r'''
BB=/bin/busybox
echo LYNX_READONLY_LIVE_INVENTORY
uname -a
cat /proc/uptime
echo MOUNTS
cat /proc/mounts
echo FILESYSTEMS
cat /proc/filesystems
echo PARTITIONS
cat /proc/partitions
echo UFS_PARTITION_METADATA
for b in /sys/class/block/sd*; do
 [ -d "$b" ] || continue
 echo "BLOCK ${b##*/}"
 for attr in uevent size start ro; do
  [ -r "$b/$attr" ] || continue
  echo "ATTR $attr"
  $BB timeout 2 cat "$b/$attr"
 done
done
echo POWER_SUPPLIES
for p in /sys/class/power_supply/*; do
 [ -d "$p" ] || continue
 echo "SUPPLY ${p##*/}"
 for attr in type status present online capacity voltage_now current_now temp charge_counter charge_full charge_full_design health usb_type; do
  [ -r "$p/$attr" ] || continue
  printf '%s=' "$attr"
  $BB timeout 2 cat "$p/$attr"
 done
done
echo WATCHDOGS
for p in /sys/class/watchdog/*; do
 [ -d "$p" ] || continue
 echo "WATCHDOG ${p##*/}"
 for attr in identity state status bootstatus timeout nowayout; do
  [ -r "$p/$attr" ] || continue
  printf '%s=' "$attr"
  $BB timeout 2 cat "$p/$attr"
 done
done
echo THERMAL
for p in /sys/class/thermal/thermal_zone*; do
 [ -r "$p/type" ] || continue
 printf '%s ' "${p##*/}"
 $BB timeout 2 cat "$p/type"
 $BB timeout 2 cat "$p/temp"
done
echo MODULES
cat /proc/modules
echo CPU_FREQUENCY_POLICIES
for p in /sys/devices/system/cpu/cpufreq/policy*; do
 [ -d "$p" ] || continue
 echo "POLICY ${p##*/}"
 for attr in affected_cpus scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_max_freq; do
  [ -r "$p/$attr" ] || continue
  printf '%s=' "$attr"
  $BB timeout 2 cat "$p/$attr"
 done
done
echo COOLING_DEVICES
for p in /sys/class/thermal/cooling_device*; do
 [ -d "$p" ] || continue
 echo "COOLING ${p##*/}"
 cat "$p/type" "$p/cur_state" "$p/max_state"
done
echo CPU_LOAD
cat /proc/loadavg
$BB top -b -n 2 -d 1
echo UPTIME_AT_END
cat /proc/uptime
echo LYNX_INVENTORY_DONE
'''
def main():
 os.umask(0o077);ip='192.168.100.9';out=R/'logs'/('live-inventory-'+str(time.time_ns()));out.mkdir(mode=0o700)
 p=subprocess.run(ssh_command(ip,PROOF),capture_output=True,timeout=15);(out/'identity.stdout').write_bytes(p.stdout);(out/'identity.stderr').write_bytes(p.stderr)
 if not proof_valid(p.stdout.decode(errors='replace'),p.returncode):raise RuntimeError('Identity failed; inventory not executed')
 (out/'remote-source.sh').write_text(SCRIPT);started=time.time_ns();timedout=False
 try:
  p=subprocess.run(ssh_command(ip,SCRIPT),capture_output=True,timeout=45);stdout,stderr,rc=p.stdout,p.stderr,p.returncode
 except subprocess.TimeoutExpired as ex:stdout,stderr,rc=ex.stdout or b'',ex.stderr or b'',None;timedout=True
 (out/'inventory.stdout').write_bytes(stdout);(out/'inventory.stderr').write_bytes(stderr)
 report={'phone_ip':ip,'identity_verified':True,'started_ns':started,'finished_ns':time.time_ns(),'exit_code':rc,'timed_out':timedout,'completed':b'LYNX_INVENTORY_DONE' in stdout,'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'partition_writes':False,'sysfs_writes':False,'mounts_changed':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json')
if __name__=='__main__':main()
