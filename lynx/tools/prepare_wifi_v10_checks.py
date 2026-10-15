"""Preserve earlier tests; validate firmware and ODM repairs against stock ramdisk."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='0b0da995892b072fa17de86c814584c0eca918130431a0e49566e07a67449c13';NEW='bd0f541c93507b296865699e7c972c9468600bdc516e2bfed234dbb12497606f'
def update(s):return s.replace(OLD,NEW).replace('busybox-wifi-ssh-twostage-v9','busybox-wifi-ssh-twostage-v10').replace('wifi-v9-','wifi-v10-')
def save(name,s):
    out=T/name;assert not out.exists(),out;compile(s,str(out),'exec');out.write_text(s)
for name in ['test_wifi_v9_journals.py','test_wifi_v9_image_vm.py','lynx_wifi_v9_contact.py']:
    save(name.replace('_v9','_v10'),update((T/name).read_text()))
save('lynx_boot_a_wifi_v10_trial.py',update((T/'lynx_boot_a_wifi_v9_trial.py').read_text()).replace('validate_wifi_v9_image','validate_wifi_v10_image'))
s=update((T/'test_native_vendor_payload_fixed_loop.py').read_text()).replace('emulated-native-vendor-payload-fixed-loop-','emulated-native-vendor-payload-odm-fixed-loop-')
s=s.replace("checks={'real_loop_64MiB':","checks={'odm_alias_resolved':b'PAYLOAD_VM_ODM_ALIAS_RESOLVED' in console,'firmware_directory_preserved':b'PAYLOAD_VM_FIRMWARE_DIRECTORY_PRESERVED' in console,'real_loop_64MiB':")
s=s.replace('$BB df -k /run',"""if [ -L /odm/etc ] && [ -f /odm/etc/wifi/wifi.cfg ] && [ -f /vendor/odm/etc/wifi/wifi.cfg ]; then echo PAYLOAD_VM_ODM_ALIAS_RESOLVED; fi
if [ -d /vendor/firmware ] && [ ! -L /vendor/firmware ] && $BB cmp /lib/firmware/WIFI_RAM_CODE_soc7_0_1_1.bin /vendor/firmware/WIFI_RAM_CODE_soc7_0_1_1.bin; then echo PAYLOAD_VM_FIRMWARE_DIRECTORY_PRESERVED; fi
$BB df -k /run""")
save('test_native_vendor_payload_odm_fixed_loop.py',s)
s=update((T/'validate_wifi_v9_image.py').read_text())
s=s.replace('emulated-native-vendor-payload-fixed-loop-','emulated-native-vendor-payload-odm-fixed-loop-').replace('emulated-wifi-v10-guard-','emulated-wifi-v10-image-')
start=s.index("    require(set(current)-set(original)");end=s.index("    require(len(mirrored)",start)
replacement=r'''    relocated={name:'vendor/odm/etc'+name[len('odm/etc'):] for name in original if name=='odm/etc' or name.startswith('odm/etc/')}
    require(relocated,'No ODM relocation')
    for name,target in relocated.items():require(current[target]==original[name],'ODM configuration bytes/permissions changed')
    require(set(current)-set(original)==set(mirrored)|set(relocated.values())|{'vendor/odm'},'Unexpected supplementary files')
    require(set(original)-set(current)==set(relocated),'Unexpected removed supplementary files')
    require(current['vendor/odm']['mode']&0o170000==0o040000,'ODM target parent missing')
    for name in original:
        if name!='vendor/firmware' and name not in relocated:require(current[name]==original[name],'Unrelated module/key/config changed: '+name)
'''
s=s[:start]+replacement+s[end:]
s=s.replace("    for target,name in mirrored.items():","    require(vendor['odm/etc']['mode']&0o170000==0o120000 and vendor['odm/etc']['data']==b'/vendor/odm/etc','Stock ODM alias differs')\n    for target,name in mirrored.items():")
s=s.replace("R/'tools/lynx_wifi_v9_contact.py'","R/'tools/lynx_wifi_v10_contact.py'").replace('wifi-v9-image-validation.json','wifi-v10-image-validation.json')
save('validate_wifi_v10_image.py',s)
print('Separate full-layout validation/contact/trial tools prepared.')
