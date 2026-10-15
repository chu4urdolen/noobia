"""Pin independent Wi-Fi v5 checks and reuse reviewed network/recovery paths."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7'
NEW='856e9f39f283593777608fc838afb66a130398732585035dc0c61bfd1925c3af'
def save(name,text):
    path=T/name;assert not path.exists(),str(path);path.write_text(text)
def replace(text):return text.replace('busybox-wifi-ssh-twostage-v4','busybox-wifi-ssh-twostage-v5').replace(OLD,NEW).replace('wifi-v4-','wifi-v5-')
def main():
    for old,new in [('test_wifi_v4_image_vm.py','test_wifi_v5_image_vm.py'),('test_wifi_v4_journals.py','test_wifi_v5_journals.py'),('lynx_wifi_v4_contact.py','lynx_wifi_v5_contact.py')]:save(new,replace((T/old).read_text()))
    validator=replace((T/'validate_wifi_v4_image.py').read_text())
    validator=validator.replace("require(image[:12]==base[:12] and image[16:4096]==base[16:4096],'Unrelated boot header changes')", "require(image[:12]==base[:12] and image[16:44]==base[16:44] and image[1580:4096]==base[1580:4096],'Unrelated boot header changes')\n require(boot['cmdline']==ref['cmdline']+' fw_devlink=permissive','Unexpected commandline')")
    marker=" require(set(first)-set(original)==allowed,'Unexpected bootstrap files')";assert validator.count(marker)==1
    validator=validator.replace(marker," added=['clk-mt6983-cam.ko','clk-mt6983-img.ko','clk-mt6983-mdp_grp.ko','clk-mt6983-mm.ko','clk-mt6983-vcodec.ko']\n allowed.update('lib/modules/'+name for name in added)\n"+marker,1)
    validator=validator.replace('len(base_names)==33','len(base_names)==38')
    marker=" report=json.loads((F/'build-validation.json').read_text())"
    extra=''' require('etc/lynx/session-token' not in extra,'Supplement would overwrite fresh experiment identity')
 require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded area overlaps unchanged metadata')
 native=sorted((P/'artifacts').glob('emulated-native-power-clocks-v2-cortex-a710-*/result.json'));require(native,'Native clock ABI test missing')
 nt=json.loads(native[-1].read_text());require(nt['passed'] and nt['checks']['clean_poweroff'] and nt['checks']['no_kernel_exception'],'Native stock module test failed')
 for name in added:
  expected_module=(S/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes()
  require(first['lib/modules/'+name]['data']==expected_module and nt['clock_module_sha256'][name]==digest(expected_module),'Exact tested stock clock module differs: '+name)
 expected_base=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v4/build-validation.json').read_text())['base_modules']
 insert=expected_base.index('mtk-scpsys.ko');expected_base[insert:insert]=added
 require(base_names==expected_base,'Unexpected base driver ordering')
'''
    assert validator.count(marker)==1;validator=validator.replace(marker,extra+marker,1)
    save('validate_wifi_v5_image.py',validator)
    trial=replace((T/'lynx_boot_a_wifi_v4_trial.py').read_text()).replace('validate_wifi_v4_image.py','validate_wifi_v5_image.py').replace("'module_prefix_count': 33","'module_prefix_count': 38")
    save('lynx_boot_a_wifi_v5_trial.py',trial)
    print('Pinned Wi-Fi v5 tools prepared; no phone contacted.')
if __name__=='__main__':main()
