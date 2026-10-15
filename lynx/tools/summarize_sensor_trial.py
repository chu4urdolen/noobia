"""Verify saved sensor-trial captures and publish only a sanitized result."""
import argparse,hashlib,json,re
from pathlib import Path
from lynx_wifi_v19_contact import proof_valid
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--receipt',type=Path,default=R/'logs/sensor-trial-1792100424200752360/result.json');args=parser.parse_args();receipt=args.receipt.resolve();folder=receipt.parent;r=json.loads(receipt.read_text());ops={op['name']:op for op in r['operations']}
 assert not r['flash_performed'] and not r['cpu_frequency_modules_allowed'] and r['native_identity_verified'] and r['stop_timer_armed'] and r['sensor_stage_exit_code']==0
 for op in r['operations']:
  data=(folder/(op['name']+'.stdout')).read_bytes();assert sha(data)==op['stdout_sha256'] and len(data)==op['stdout_bytes']
 assert proof_valid((folder/'identity.stdout').read_text(),ops['identity']['exit_code'])
 stage=(folder/'sensor-stage.stdout').read_text();assert all('INSMOD_RETURN '+name+' status=0' in stage for name in ['nvmem_mtk_devinfo','soc_temp_lvts'])
 kernel=(folder/'kernel-and-sensors.stdout').read_text(errors='replace');snapshot=kernel.split('THERMAL_FINAL\n',1)[1].split('\nBINDINGS\n',1)[0];temps={kind:int(value) for _,kind,value in re.findall(r'(?m)^thermal_zone(\d+) (\S+)\n(-?\d+)$',snapshot)};zones=re.findall(r'(?m)^thermal_zone\d+ (\S+)$',snapshot)
 assert 0<temps['soc_max']<125000 and any(n.startswith('cpu_') for n in temps)
 assert 'drivers/mtk-soc-temp-lvts' in kernel and 'drivers/mediatek,devinfo' in kernel
 assert ops['arm-stop-and-confirm']['finished_ns']<ops['sensor-stage']['started_ns']
 boot=P/'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img';baseline='5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851';assert sha(boot.read_bytes())==baseline
 summary={'milestone':'Stock LVTS SoC/CPU/GPU/memory sensor readings after pinned native SSH','native_identity_verified':True,'sensor_modules_inserted':['nvmem_mtk_devinfo','soc_temp_lvts'],'live_sensor_bindings_verified':True,'valid_zone_count':len(temps),'total_zones':len(zones),'temperatures_millidegrees_celsius':temps,'unavailable_zones':[n for n in zones if n not in temps],'battery_temperature_available':False,'cpu_frequency_control_tested':False,'charging_changes':False,'flash_performed':False,'baseline_image_sha256':baseline,'baseline_image_unchanged':True,'independent_stop_timer_armed_before_module_load':True,'kernel_bootloader_sensor_init_reuse_message_observed':'LK init LVTS' in kernel,'fake_calibration_warning_observed':'This sample is not calibrated, fake' in kernel,'poweroff_requested':True,'physical_poweroff_confirmed':r.get('physical_poweroff_confirmed',False),'thermal_safety_fully_validated':False,'private_capture_sha256':sha((folder/'kernel-and-sensors.stdout').read_bytes()),'limits':'One short sensor trial. Values are not independently calibrated against an external instrument. Battery/board/PMIC sensing and CPU throttling remain unverified; loss of SSH does not prove physical power-off.'}
 out=P/'docs/SENSOR-HARDWARE-RESULT.json';out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'result':str(out),'valid_zones':len(temps),'total_zones':len(zones),'soc_celsius':temps['soc_max']/1000,'unavailable_zones':len(zones)-len(temps)},indent=2))
if __name__=='__main__':main()
