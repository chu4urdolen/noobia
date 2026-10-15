"""Prepare authorized Noobia Wi-Fi config privately; never print credentials."""
import hashlib,json,re,subprocess
from pathlib import Path
root=Path('/noobia/lynx'); secret=root/'secrets'; secret.mkdir(mode=0o700,exist_ok=True); secret.chmod(0o700)
uuid='dfa26e16-06b4-4746-95fd-4ad3bbc57f63'
def profile(field,show=False):
 args=['nmcli']+(['--show-secrets'] if show else [])+['-g',field,'connection','show',uuid]
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 if p.returncode: raise RuntimeError('NetworkManager profile field unavailable')
 return p.stdout.rstrip('\n')
ssid=profile('802-11-wireless.ssid'); assert ssid=='Noobia'
keymgmt=profile('802-11-wireless-security.key-mgmt'); assert keymgmt=='wpa-psk'
password=profile('802-11-wireless-security.psk',True)
if re.fullmatch('[0-9a-fA-F]{64}',password): psk=password.lower()
else:
 if not 8<=len(password.encode())<=63: raise RuntimeError('No usable saved Wi-Fi credential available')
 psk=hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex()
config='ctrl_interface=/run/wpa_supplicant\nupdate_config=0\ncountry=BG\nnetwork={\n ssid='+ssid.encode().hex()+'\n psk='+psk+'\n key_mgmt=WPA-PSK\n proto=RSN\n}\n'
path=secret/'noobia-wpa_supplicant.conf'
if path.exists() and path.read_text()!=config: raise RuntimeError('Preserve existing credential configuration')
path.write_text(config); path.chmod(0o600)
(root/'linux-port/docs/wifi-credential-preparation.json').write_text(json.dumps({'ssid':ssid,'security':'WPA2-PSK','country':'BG','country_basis':'Nexus timezone Europe/Sofia; verify before trial if operating elsewhere.','private_config_path':str(path),'password_logged':False,'phone_contacted':False,'source':'User-authorized existing NetworkManager Noobia profile'},indent=2)+'\n')
print('Noobia WPA2 configuration prepared privately; password not printed.')
