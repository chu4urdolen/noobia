"""Pin V19 tools without repeating unchanged V18 timing tests."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port'
old='62bfed751f3793f63132d2ca3181a5aa869f4f5ce6efcb640abbcaecc9ba4f40'
new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v19/build-validation.json').read_text())['candidate_sha256']
for name in ['lynx_wifi_v18_contact.py','lynx_boot_a_wifi_v18_trial.py','run_wifi_v18_trial.py','test_native_vendor_wifi_v18_loop.py']:
 f=T/name.replace('v18','v19');assert not f.exists(),f
 source=(T/name).read_text().replace(old,new).replace('v18','v19');compile(source,str(f),'exec');f.write_text(source)
print(new)
