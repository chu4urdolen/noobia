"""Add guarded stock radio clock suppliers and bounded station-failure diagnostics."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v11';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v12'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='4aad96c499317fa7f6d46371657a8e8bb93043b99de6627f801c5508f40a1033','Reference changed')
    audit=json.loads((P/'docs/stock-radio-clock-audit.json').read_text());require(audit['passed'] and len(audit['runtime_property_checks'])==18,'Clock audit incomplete')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']));extra=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
    guard=(P/'radio-clock-guard.sh').read_bytes();put(extra,'etc/lynx/radio-clock-guard.sh',guard,0o100644)
    properties=''.join(row['node']+' '+row['property']+' '+row['sha256']+'\n' for row in audit['runtime_property_checks']).encode();put(extra,'etc/lynx/radio-clock-properties',properties,0o100644)
    wifi=extra['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    lynx_stage WIFI_DRIVERS\n';require(wifi.count(anchor)==1,'Radio boundary changed')
    clock=b'''    . /etc/lynx/radio-clock-guard.sh || return 135
    lynx_stage WIFI_CLOCK_BUFFER_PROVIDER
    lynx_radio_clock_load
    radio_clock_status=$?
    printf '%s\\n' "$radio_clock_status" > /run/lynx/radio-clock-result
    [ "$radio_clock_status" = 0 ] || return 135
'''
    wifi=wifi.replace(anchor,clock+anchor)
    anchor=b'    /bin/lynx-wifi-control --station || return 139\n';require(wifi.count(anchor)==1,'Station boundary changed')
    station=b'''    station_token=$($BB cat /etc/lynx/session-token) || return 139
    printf '<6>LYNX_STATION_ATTEMPT_BEGIN %s\\n' "$station_token" > /dev/kmsg || true
    /bin/lynx-wifi-control --station
    station_status=$?
    printf '%s\\n' "$station_status" > /run/lynx/station-result
    if [ "$station_status" != 0 ]; then
        $BB dmesg | $BB tail -c 1048576 > /run/lynx/station-dmesg
        return 139
    fi
'''
    wifi=wifi.replace(anchor,station);put(extra,'etc/lynx/wifi-runtime.sh',wifi,0o100644)
    payload=gzip.compress(decompress(pack(extra)),mtime=0)
    parser=(P/'station-failure-parser.sh').read_bytes();timing=entries['bin/boot-proof-reboot']['data'];anchor=b'lynx_network_timing_clock() {';require(timing.count(anchor)==1,'Timing function boundary changed');timing=timing.replace(anchor,parser+anchor)
    anchor=b'                            nt_code=$((nt_worker-130)) ;;\n';require(timing.count(anchor)==1,'Worker mapping changed')
    timing=timing.replace(anchor,b'''                            nt_code=$((nt_worker-130))
                            if [ "$nt_worker" = 139 ]; then
                                lynx_station_failure_code
                                nt_code=$nt_station_code
                            elif [ "$nt_worker" = 135 ]; then
                                if IFS= read -r nt_radio_clock < /run/lynx/radio-clock-result; then
                                    case "$nt_radio_clock" in 36|37|38|39) nt_code=$nt_radio_clock ;; esac
                                fi
                            fi ;;
''');put(entries,'bin/boot-proof-reboot',timing)
    put(entries,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(entries,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;oldpayload=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap')
    image[offset:offset+max(len(payload),len(oldpayload))]=payload.ljust(max(len(payload),len(oldpayload)),b'\0');image=bytes(image)
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',entries['init']['data']),('timing-runtime-source',timing),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('radio-clock-guard.sh',guard),('station-failure-parser.sh',parser),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        p=OUT/name;p.write_bytes(data);p.chmod(0o600)
    codes=json.loads((F/'build-validation.json').read_text())['result_codes']
    labels=['station device open failed','station device type check failed','station argument unrecognized','last station diagnostic: power-on failed','last station diagnostic: mode callback absent','last station diagnostic: network interface timeout','last station diagnostic: mode setting failed','last station diagnostic: driver resetting','last station diagnostic: invalid write count','station marker present; no recognized failure string','station detail unavailable or marker absent','radio clock target/property/module guard refused','radio clock MFD load or binding failed','radio clock buffer load or binding failed','radio clock RC binding failed']
    codes.update({str(i):label for i,label in enumerate(labels,25)})
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(extra),timing_runtime_sha256=sha(timing),radio_clock_guard_sha256=sha(guard),station_parser_sha256=sha(parser),result_codes=codes,target_delays_seconds={str(i):480+5*i for i in range(40)},observation_seconds=780,stock_radio_clock_suppliers=True,station_snapshot_bound_bytes=1048576,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),supplement_bytes=len(payload)),indent=2))
if __name__=='__main__':main()
