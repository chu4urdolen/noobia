"""Separate native checks/contact/trial for the corrected vendor firmware layout."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c';NEW='0b0da995892b072fa17de86c814584c0eca918130431a0e49566e07a67449c13'
def update(s):return s.replace(OLD,NEW).replace('busybox-wifi-ssh-twostage-v7','busybox-wifi-ssh-twostage-v9').replace('wifi-v7-','wifi-v9-')
def save(name,s):
    out=T/name;assert not out.exists(),out;compile(s,str(out),'exec');out.write_text(s)
def main():
    for old,new in [('test_wifi_v7_journals.py','test_wifi_v9_journals.py'),('test_wifi_v7_image_vm.py','test_wifi_v9_image_vm.py'),('lynx_wifi_v7_contact.py','lynx_wifi_v9_contact.py')]:save(new,update((T/old).read_text()))
    save('lynx_boot_a_wifi_v9_trial.py',update((T/'lynx_boot_a_wifi_v7_trial.py').read_text()).replace('validate_wifi_v7_image','validate_wifi_v9_image'))
    s=(T/'test_native_vendor_payload_loop.py').read_text().replace('9df9229dba14a1b29e17a5bcdb8c34fb813682998a63ff57718ed1bb7f6f9226',NEW).replace('busybox-payload-timing-v1','busybox-wifi-ssh-twostage-v9').replace('emulated-native-vendor-payload-loop-','emulated-native-vendor-payload-fixed-loop-')
    save('test_native_vendor_payload_fixed_loop.py',s)
    print('Separate corrected-layout checks/contact/trial prepared.')
if __name__=='__main__':main()
