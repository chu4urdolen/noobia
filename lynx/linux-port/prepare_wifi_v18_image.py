"""Capture WPA status/scan/rfkill together and prioritize association result slots."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v17';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v18'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def target(n):return 525 if n==9 else 160+5*(n-50) if n>=50 else 210+5*(n-40) if n>=40 else 260+5*(n-25) if n>=25 else 335+5*n
def main():
    require(not OUT.exists(),'Preserve earlier artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab','Parent differs');b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()));diag=(P/'wpa-diagnostics.sh').read_bytes();put(x,'etc/lynx/wpa-diagnostics.sh',diag,0o100644);put(x,'etc/lynx/wpa-target-ssid',b'Noobia\n',0o100644)
    wifi=x['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    [ "$connected" = 1 ] || return 143\n';require(wifi.count(anchor)==1,'Association boundary differs');wifi=wifi.replace(anchor,b'''    if [ "$connected" != 1 ]; then
        . /etc/lynx/wpa-diagnostics.sh || return 143
        lynx_wpa_snapshot || return 143
        [ "$nt_wpa" = 51 ] || return 143
    fi
''');require(wifi.count(b'/sbin/wpa_supplicant -B -D')==1,'Supplicant boundary differs');wifi=wifi.replace(b'/sbin/wpa_supplicant -B -D',b'/sbin/wpa_supplicant -B -d -D');put(x,'etc/lynx/wifi-runtime.sh',wifi,0o100644);payload=gzip.compress(decompress(pack(x)),mtime=0)
    timing=e['bin/boot-proof-reboot']['data'];anchor=b'                            elif [ "$nt_worker" = 135 ]; then\n';require(timing.count(anchor)==1,'Worker mapping differs');timing=timing.replace(anchor,b'''                            elif [ "$nt_worker" = 143 ]; then
                                nt_code=59
                                if IFS= read -r nt_wpa < /run/lynx/wpa-failure-code; then
                                    case "$nt_wpa" in 50|51|52|53|54|55|56|57|58|59) nt_code=$nt_wpa ;; esac
                                fi
'''+anchor)
    anchor=b'    nt_target=$((80+5*nt_code))\n    [ "$nt_code" != 9 ] || nt_target=525\n';require(timing.count(anchor)==1,'Timing boundary differs');timing=timing.replace(anchor,b'''    case "$nt_code" in
        9) nt_target=525 ;;
        50|51|52|53|54|55|56|57|58|59) nt_target=$((160+5*(nt_code-50))) ;;
        40|41|42|43|44|45|46|47|48|49) nt_target=$((210+5*(nt_code-40))) ;;
        25|26|27|28|29|30|31|32|33|34|35|36|37|38|39) nt_target=$((260+5*(nt_code-25))) ;;
        *) nt_target=$((335+5*nt_code)) ;;
    esac
''');put(e,'bin/boot-proof-reboot',timing);put(e,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(e,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644);token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644);rd=pack(e);h=bytearray(raw[:1584]);struct.pack_into('<I',h,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(h).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;prev=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap');image[offset:offset+max(len(payload),len(prev))]=payload.ljust(max(len(payload),len(prev)),b'\0');image=bytes(image);OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',e['init']['data']),('timing-runtime-source',timing),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('wpa-diagnostics.sh',diag)]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    labels=['supplicant control/status unavailable','late completed association snapshot','last key/4-way handshake error','last association/authentication rejection','WLAN rfkill block observed','target absent from successful cached scan','target seen but not connected','authentication/association/handshake in progress','supplicant interface inactive/disabled','unclassified or incomplete WPA diagnostic']
    m=json.loads((F/'build-validation.json').read_text());m['result_codes'].update({str(n):label for n,label in enumerate(labels,50)});m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(x),timing_runtime_sha256=sha(timing),wpa_diagnostics_sha256=sha(diag),target_delays_seconds={str(n):target(n) for n in range(60)},diagnostic_version='v18 prioritized WPA status/scan/rfkill diagnostic',parent_sha256=sha(raw),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd),'supplement_bytes':len(payload)},indent=2))
if __name__=='__main__':main()
