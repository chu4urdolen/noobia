"""Keep prior Wi-Fi tests/tools; derive checks for guarded clock startup."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='856e9f39f283593777608fc838afb66a130398732585035dc0c61bfd1925c3af';NEW='eb50fc9027c52453b4cc43e872900dff2c22037d0945a5d74490d854dd1c3dab'
def save(name,source):
    out=T/name;compile(source,str(out),'exec')
    if out.exists():assert out.read_text()==source,out
    else:out.write_text(source)
def update(source):return source.replace('busybox-wifi-ssh-twostage-v5','busybox-wifi-ssh-twostage-v6').replace(OLD,NEW).replace('wifi-v5-','wifi-v6-')
def main():
    source=update((T/'test_wifi_v5_image_vm.py').read_text()).replace("'cortex-a72'","'cortex-a710'");save('test_wifi_v6_image_vm.py',source)
    source=update((T/'lynx_wifi_v5_contact.py').read_text());save('lynx_wifi_v6_contact.py',source)
    source=update((T/'lynx_boot_a_wifi_v5_trial.py').read_text()).replace('validate_wifi_v5_image','validate_wifi_v6_image').replace("'module_prefix_count': 38","'module_prefix_count': 34");save('lynx_boot_a_wifi_v6_trial.py',source)
    source=update((T/'test_wifi_v5_journals.py').read_text()).replace("'cortex-a72'","'cortex-a710'")
    start=source.index('lynx_load_checkpoint_modules() {');end=source.index('lynx_read_own_boot_payload()',start)
    source=source[:start]+source[end:]
    marker="    init += bootstrap.replace(b'/sys/class/block', b'/run/fixture')"
    added="""    loader=frozen[frozen.index(b'lynx_load_checkpoint_modules() {'):frozen.index(b'\\numask 077')]
    put(entries,'bin/v6-fixture-busybox',b'''#!/bin/sh
if [ "$1" = insmod ]; then
    printf 'LOAD:%s\\\\n' "$2" >> /run/lynx/load-order
    exit 0
fi
exec /bin/busybox "$@"
''')
    init+=b'''BB=/bin/v6-fixture-busybox
lynx_stock_clock_helper_load() {
    if [ -f /run/fixture/clock-fail ]; then return 10; fi
    printf 'CLOCK_HELPER\\\\n' >> /run/lynx/load-order
    lynx_diag_emit 516 1; lynx_diag_emit 516 2; lynx_diag_emit 516 3
    return 0
}
'''+loader
"""
    assert marker in source;source=source.replace(marker,added+marker)
    start=source.index('\nlynx_wifi_bootstrap\n');end=source.index('\n. /etc/lynx/wifi-runtime.sh',start)
    source=source[:end]+"\n$BB cat /run/lynx/load-order\n$BB touch /run/fixture/clock-fail\nlynx_load_checkpoint_modules /etc/lynx/bootstrap-storage-modules.load\nprintf 'LYNX_VM_CLOCK_FAILURE_EXIT=%s\\\\n' \"$?\"\n$BB rm /run/fixture/clock-fail\n"+source[end:]
    marker="              'bootstrap_success': b'LYNX_VM_BOOTSTRAP_EXIT=0' in raw,"
    checks="""              'clock_failure_blocks_ufs': b'LYNX_VM_CLOCK_FAILURE_EXIT=1' in raw and b'STOCK_CLOCK_HELPER_FAILED_BEFORE_UFS status=10' in raw,
              'clock_helper_precedes_main_ufs': b'CLOCK_HELPER\\r\\nLOAD:/lib/modules/ufs-mediatek-mod.ko' in raw,
"""
    assert marker in source;source=source.replace(marker,marker+'\n'+checks)
    save('test_wifi_v6_journals.py',source)
    print('Wi-Fi v6 exact-image/native journal/contact/trial tools prepared; no phone contacted.')
if __name__=='__main__':main()
