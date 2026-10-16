"""Use the newest verified continuous-session DHCP address with pinned SSH."""
import ipaddress,json,os,sys
from pathlib import Path
from lynx_wifi_v19_contact import ssh_command
ROOT=Path(__file__).resolve().parent.parent
def resolve():
 sessions=[]
 for path in (ROOT/'logs').glob('gauge-identity-trial-*/result.json'):
  try:
   r=json.loads(path.read_text())
   if r.get('native_identity_verified') and r.get('session_left_running') and r.get('keep_running_requested'):
    ip=r['phone_ip']
    if ipaddress.ip_address(ip) in ipaddress.ip_network('192.168.100.0/24'):sessions.append((r['started_ns'],ip,path))
  except (ValueError,KeyError,OSError):continue
 if not sessions:raise SystemExit('No verified continuous session found; start resume_battery_session.py first.')
 return max(sessions)
def main():
 _,ip,_=resolve();command=ssh_command(ip,'')[:-1]+sys.argv[1:];os.execvp(command[0],command)
if __name__=='__main__':main()
