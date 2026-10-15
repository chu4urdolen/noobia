"""Compare embedded Wi-Fi settings with active Noobia profile without logging keys."""
import gzip,hashlib,hmac,json,re,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_newc
F=P/'artifacts/busybox-wifi-ssh-twostage-v17';x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()));config=x['etc/lynx/wpa_supplicant.conf']['data'].decode()
def nm(*args):
    p=subprocess.run(['nmcli',*args],capture_output=True,text=True,timeout=15)
    if p.returncode:raise RuntimeError('NetworkManager query failed (output omitted): '+str(p.returncode))
    return p.stdout.strip()
connection=nm('-g','GENERAL.CONNECTION','device','show','wlx40a5ef5f66f1')
fields={k:nm('-g',k,'connection','show',connection) for k in ['802-11-wireless.ssid','802-11-wireless.hidden','802-11-wireless.band','802-11-wireless-security.key-mgmt','802-11-wireless-security.proto','802-11-wireless-security.pmf']}
ssid_value=re.search(r'^\s*ssid=(.*?)\s*$',config,re.M).group(1)
ssid=json.loads(ssid_value) if ssid_value.startswith('"') else bytes.fromhex(ssid_value).decode()
allowed=['country','ctrl_interface','update_config','scan_ssid','key_mgmt','proto','ieee80211w','freq_list','scan_freq']
safe={key:re.findall(r'^\s*'+re.escape(key)+r'=(.*?)\s*$',config,re.M) for key in allowed}
secret=nm('--show-secrets','-g','802-11-wireless-security.psk','connection','show',connection)
key=re.search(r'^\s*psk=([0-9a-fA-F]{64})\s*$',config,re.M)
known=bool(secret and key and ssid==fields['802-11-wireless.ssid'])
match=None
if known:
    derived=bytes.fromhex(secret) if re.fullmatch('[0-9a-fA-F]{64}',secret) else hashlib.pbkdf2_hmac('sha1',secret.encode(),ssid.encode(),4096,32)
    match=hmac.compare_digest(derived,bytes.fromhex(key.group(1)))
ap=nm('-t','--escape','no','-f','SSID,CHAN,FREQ,SECURITY,IN-USE','device','wifi','list','ifname','wlx40a5ef5f66f1','--rescan','no')
ap=[line for line in ap.splitlines() if line.startswith(ssid+':')]
report={'phone_contacted':False,'network_changed':False,'active_profile':connection,'active_settings':fields,'embedded_ssid':ssid,'embedded_nonsecret_settings':safe,'secret_available_for_comparison':bool(secret),'psk_matches_active_profile':match,'cached_matching_access_points':ap,'password_or_key_logged':False,'limits':'Read-only host profile and cached scan; no physical phone association log or RF scan retrieved.'}
out=P/'docs'/('wifi-network-profile-audit-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o600);print(json.dumps({'report':str(out),**report},indent=2))
