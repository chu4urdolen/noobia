"""Verify saved resume/install streams and publish sanitized hardware results."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;PORT=ROOT/'linux-port'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--resume',type=Path,required=True);a=p.parse_args();resume=json.loads(a.resume.read_text())
 if resume['state']!='online' or resume['flash_performed'] or resume['unconditional_shutdown']:raise ValueError('Not a successful continuous resume')
 if any(op['exit_code']!=0 for op in resume['operations']):raise ValueError('Resume operation failed')
 session=json.loads(Path(resume['session']).read_text());analysis=json.loads((Path(resume['session']).parent/'analysis.json').read_text())
 if not(session['native_identity_verified'] and session['session_left_running'] and not session['stop_timer_armed'] and analysis['identity_query_verified'] and analysis['raw_register_word']==42495):raise ValueError('Live ZY0603 identity/continuous policy not verified')
 receipt=Path(resume['monitor_install_receipt']);install=json.loads(receipt.read_text());folder=receipt.parent
 if not install['native_identity_verified'] or install['load_command_exit_code']!=0 or not install['monitor_loaded_marker'] or install['flash_performed']:raise ValueError('Monitor install failed')
 for op in install['operations']:
  raw=(folder/(op['name']+'.stdout')).read_bytes()
  if sha(raw)!=op['stdout_sha256'] or len(raw)!=op['stdout_bytes']:raise ValueError('Capture integrity failure: '+op['name'])
 data=(folder/'load-and-snapshot.stdout').read_text();values=dict(line.split('=',1) for line in data.splitlines() if '=' in line)
 for field in ['temperature_error','voltage_error','current_error','capacity_error']:
  if values.get(field)!='0':raise ValueError('Invalid battery field: '+field)
 if int(values['gauge_device_type'])!=42495:raise ValueError('Unexpected gauge family')
 result={'device':'OnePlus Nord 3 CPH2493','kernel_release':'5.10.149-android12-9-o-g311738fbb5a8','gauge_family':'ZY0603','device_type_reply':'0xa5ff','native_ssh_identity_verified':True,'ram_monitor_module_sha256':install['module_sha256'],'fixed_read_registers':['0x06','0x08','0x0c','0x2c'],'snapshot':{k:int(values[k]) for k in ['temperature_raw','temperature_millidegrees_celsius','pack_voltage_mv','gauge_current_ma_signed','capacity_percent']},'all_snapshot_field_errors_zero':True,'live_battery_observations_verified':True,'configuration_or_charger_writes':False,'current_session_partition_writes':False,'unconditional_shutdown_enabled':False,'cpu_soc_temperature_stop_millidegrees':60000,'battery_temperature_stop_millidegrees':45000,'phone_sampling_interval_seconds':5,'host_capture_interval_seconds':10,'host_logger_started':True,'repeat_boot_and_automatic_ram_setup_verified':True,'baseline_v19_boot_image_unchanged':True,'thermal_safety_fully_validated':False,'external_temperature_calibration_performed':False,'limits':'Direct stock-family register observations. Temperature uses the rounded OEM kelvin offset without optional balancing compensation. Voltage is pack total, not individual-cell telemetry. Charging, active throttling response and deep idle are not validated; software cannot guarantee physical shutdown during a kernel hang.'}
 out=PORT/'docs/BATTERY-HARDWARE-RESULT.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out),'snapshot':result['snapshot']},indent=2))
if __name__=='__main__':main()
