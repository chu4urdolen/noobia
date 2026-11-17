"""Retain corrected Wi-Fi payload; add direct result timing before native fallback."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v10';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v11'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='bd0f541c93507b296865699e7c972c9468600bdc516e2bfed234dbb12497606f','Reference changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']));init=entries['init']['data']
    anchor=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n";require(init.count(anchor)==1,'Entry boundary changed')
    startup=b'''
IFS=' ' read -r nt_initial_uptime nt_initial_unused < /proc/uptime || stop
nt_initial_seconds=MARKER{nt_initial_uptime%%.*}
case "$nt_initial_seconds" in ''|*[!0-9]*) stop ;; esac
printf '%s\\n' "$nt_initial_seconds" > /run/lynx/network-timing-start || stop
'''.replace(b'MARKER',b'$')
    init=init.replace(anchor,startup+anchor);put(entries,'init',init)
    native=entries['bin/boot-proof-reboot']['data'];require(native[:4]==b'\x7fELF','Native helper changed')
    put(entries,'bin/boot-proof-reboot-native',native)
    runtime=(P/'lynx-network-failure-timing.sh').read_bytes();put(entries,'bin/boot-proof-reboot',runtime)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+raw[coverage:]
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',init),('timing-runtime-source',runtime),('supplement.cpio.gz',(F/'supplement.cpio.gz').read_bytes()),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        path=OUT/name;path.write_bytes(data);path.chmod(0o600)
    labels=['Wi-Fi worker returned0 but pinned host did not confirm','base driver worker131','storage driver worker132','device scan worker133','factory calibration worker134','radio module worker135','device scan worker136','chip ioctl worker137','calibration submission worker138','station power worker139','WLAN interface worker140','interface up worker141','WPA startup worker142','WPA association worker143','DHCP worker144','address worker145','Dropbear startup worker146','other Wi-Fi worker status','Wi-Fi worker result unavailable/deadline','other bootstrap failure','bootstrap base151','bootstrap storage152','bootstrap partition153','bootstrap payload154','bootstrap result unavailable/deadline']
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,failure_timing=True,timing_runtime_sha256=sha(runtime),native_reboot_helper_sha256=sha(native),result_codes={str(i):v for i,v in enumerate(labels)},target_delays_seconds={str(i):480+5*i for i in range(25)},timing_match_tolerance_seconds=2,observation_seconds=720,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd)),indent=2))
if __name__=='__main__':main()
