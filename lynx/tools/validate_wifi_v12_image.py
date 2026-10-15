"""Validate V12's guarded provider and bounded diagnostic changes independently."""
import argparse,gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_station_failure_timing import decode_progress_timing
SHA='1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 argparse.ArgumentParser().parse_args()
 for script in ['validate_wifi_v11_image.py','audit_stock_radio_clock.py']:
  p=subprocess.run(['python3',str(R/'tools'/script)],capture_output=True,text=True,timeout=60);require(p.returncode==0,'Parent/audit failed: '+p.stdout+p.stderr)
 F=P/'artifacts/busybox-wifi-ssh-twostage-v12';V=P/'artifacts/busybox-wifi-ssh-twostage-v11';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes()
 require(sha(raw)==SHA and len(raw)==67108864,'Pinned image differs')
 require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Artifact permissions differ')
 b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']))
 require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header/cmdline changed')
 require(set(e)==set(p),'First-stage entries changed')
 for name in p:
  if name not in ['bin/boot-proof-reboot','etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[name]==p[name],'Unrelated first-stage change: '+name)
 parser=(P/'station-failure-parser.sh').read_bytes();guard=(P/'radio-clock-guard.sh').read_bytes();timing=e['bin/boot-proof-reboot']['data']
 anchor=b'lynx_network_timing_clock() {';expected=p['bin/boot-proof-reboot']['data'].replace(anchor,parser+anchor)
 anchor=b'                            nt_code=$((nt_worker-130)) ;;\n'
 detail=b'''                            nt_code=$((nt_worker-130))
                            if [ "$nt_worker" = 139 ]; then
                                lynx_station_failure_code
                                nt_code=$nt_station_code
                            elif [ "$nt_worker" = 135 ]; then
                                if IFS= read -r nt_radio_clock < /run/lynx/radio-clock-result; then
                                    case "$nt_radio_clock" in 36|37|38|39) nt_code=$nt_radio_clock ;; esac
                                fi
                            fi ;;
'''
 require(expected.count(anchor)==1,'Worker mapping boundary changed');expected=expected.replace(anchor,detail)
 require(timing==expected==(F/'timing-runtime-source').read_bytes(),'Unexpected timing executable')
 payload=(F/'supplement.cpio.gz').read_bytes();oldpayload=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(oldpayload))
 require(set(x)-set(y)=={'etc/lynx/radio-clock-guard.sh','etc/lynx/radio-clock-properties'} and not set(y)-set(x),'Supplementary files differ')
 for name in y:
  if name!='etc/lynx/wifi-runtime.sh':require(x[name]==y[name],'Unrelated firmware/module/key/config changed: '+name)
 audit=json.loads((P/'docs/stock-radio-clock-audit.json').read_text())
 props=''.join(r['node']+' '+r['property']+' '+r['sha256']+'\n' for r in audit['runtime_property_checks']).encode()
 require(x['etc/lynx/radio-clock-properties']['data']==props and x['etc/lynx/radio-clock-guard.sh']['data']==guard,'Guard/map differs')
 wifi=y['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    lynx_stage WIFI_DRIVERS\n'
 clock=b'''    . /etc/lynx/radio-clock-guard.sh || return 135
    lynx_stage WIFI_CLOCK_BUFFER_PROVIDER
    lynx_radio_clock_load
    radio_clock_status=$?
    printf '%s\\n' "$radio_clock_status" > /run/lynx/radio-clock-result
    [ "$radio_clock_status" = 0 ] || return 135
'''
 require(wifi.count(anchor)==1,'Radio boundary changed');wifi=wifi.replace(anchor,clock+anchor)
 anchor=b'    /bin/lynx-wifi-control --station || return 139\n'
 capture=b'''    station_token=$($BB cat /etc/lynx/session-token) || return 139
    printf '<6>LYNX_STATION_ATTEMPT_BEGIN %s\\n' "$station_token" > /dev/kmsg || true
    /bin/lynx-wifi-control --station
    station_status=$?
    printf '%s\\n' "$station_status" > /run/lynx/station-result
    if [ "$station_status" != 0 ]; then
        $BB dmesg | $BB tail -c 1048576 > /run/lynx/station-dmesg
        return 139
    fi
'''
 require(wifi.count(anchor)==1,'Station boundary changed');wifi=wifi.replace(anchor,capture)
 require(x['etc/lynx/wifi-runtime.sh']['data']==wifi==(F/'wifi-runtime.sh').read_bytes(),'Unexpected worker change')
 require(wifi.count(b'/bin/lynx-wifi-control --station')==1,'Extra station attempt')
 m=json.loads((F/'build-validation.json').read_text())
 require(m['candidate_sha256']==SHA and m['init_sha256']==sha(e['init']['data']) and m['timing_runtime_sha256']==sha(timing) and m['radio_clock_guard_sha256']==sha(guard) and m['station_parser_sha256']==sha(parser),'Executable manifest differs')
 require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip(),'Token differs')
 require(e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode() and e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and m['supplement_sha256']==sha(payload),'Payload metadata differs')
 coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];offset=25165824
 require(raw[offset:offset+len(payload)]==payload and raw[coverage:offset]==old[coverage:offset] and raw[offset+max(len(payload),len(oldpayload)):]==old[offset+max(len(payload),len(oldpayload)):],'Protected metadata/footer or embedded payload differs')
 require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded metadata overlap')
 receipts={}
 for prefix in ['emulated-station-failure-timing-native-','emulated-radio-clock-abi-','emulated-native-vendor-wifi-v12-loop-','emulated-wifi-v12-image-']:
  files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Test absent: '+prefix);r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Test image differs')
  if prefix=='emulated-wifi-v12-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
  else:require(r['passed'] and all(r['checks'].values()),'Native test failed: '+prefix)
  if prefix=='emulated-station-failure-timing-native-':require(r['source_sha256']==sha(timing),'Tested timing differs')
  receipts[prefix]=str(files[-1])
 for prefix,source in [('radio-clock-guard-',guard),('station-parser-',parser)]:
  files=sorted((R/'tools/test-artifacts').glob(prefix+'*/result.json'));require(files,'Control absent')
  r=json.loads(files[-1].read_text());require(r['passed'] and r['source_sha256']==sha(source),'Control source differs');receipts[prefix]=str(files[-1])
 require(m['target_delays_seconds']=={str(i):480+5*i for i in range(40)} and m['observation_seconds']==780,'Timing bounds differ')
 trials=(R/'tools/lynx_boot_a_wifi_v12_trial.py').read_text();require('up to 780 seconds' in trials and 'time.monotonic()+780' in trials,'Host observer bounds differ')
 cases=0
 for code in range(40):
  for delta in [-2,-1,0,1,2,2.25,2.5]:
   elapsed=21.833501310+480+5*code+delta;op={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000}
   usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]}
   got=decode_progress_timing(op,usb,m,21.833501310);require(got['timing_module_progress_field']==(code if abs(delta)<=2 else None),'Timing corpus disagrees');cases+=1
 c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v12_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Pinned identity tests failed')
 model=R/'tools/avb-host/avb-boot-model';ref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==ref['binary_sha256'],'Boot model differs')
 for unlocked in ['1','0']:
  c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
 out=P/'docs/wifi-v12-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'timing_cases':cases,'kernel_modules_credentials_unchanged':True,'phone_contacted':False,'limits':'Stock suppliers are audited and guarded, not physically proved yet. Last matching station diagnostic is not a complete log or exact stopping point. Legacy slot9 not produced by V12.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
