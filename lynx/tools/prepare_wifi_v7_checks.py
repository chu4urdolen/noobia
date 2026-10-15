"""Separate checks for preserving the physically verified guarded UFS sequence."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='eb50fc9027c52453b4cc43e872900dff2c22037d0945a5d74490d854dd1c3dab';NEW='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c'
def save(name,source):
    out=T/name;assert not out.exists(),out;compile(source,str(out),'exec');out.write_text(source)
def update(source):return source.replace('busybox-wifi-ssh-twostage-v6','busybox-wifi-ssh-twostage-v7').replace(OLD,NEW).replace('wifi-v6-','wifi-v7-')
def main():
    save('test_wifi_v7_image_vm.py',update((T/'test_wifi_v6_image_vm.py').read_text()))
    save('lynx_wifi_v7_contact.py',update((T/'lynx_wifi_v6_contact.py').read_text()))
    save('lynx_boot_a_wifi_v7_trial.py',update((T/'lynx_boot_a_wifi_v6_trial.py').read_text()).replace('validate_wifi_v6_image','validate_wifi_v7_image'))
    source=update((T/'test_wifi_v6_journals.py').read_text())
    marker="    init+=b'''BB=/bin/v6-fixture-busybox\n"
    stubs='''lynx_ufs_registration_guard() { return 0; }
lynx_ufs_guarded_probe() {
    [ ! -f /run/fixture/probe-fail ] || return 9
    log UFS_V7_CONTROLLED_PROBE_RETURNED
    return 0
}
'''
    assert marker in source;source=source.replace(marker,marker+stubs)
    marker='$BB rm /run/fixture/clock-fail\n';assert marker in source
    source=source.replace(marker,marker+'''$BB touch /run/fixture/probe-fail
lynx_load_checkpoint_modules /etc/lynx/bootstrap-storage-modules.load
printf 'LYNX_VM_PROBE_FAILURE_EXIT=%s\\n' "$?"
$BB rm /run/fixture/probe-fail
''')
    marker='for owner in supervisor bootstrap wifi; do\n';assert marker in source
    source=source.replace(marker,'$BB cat /run/lynx/boot.log\n'+marker)
    marker="              'clock_failure_blocks_ufs':"
    source=source.replace(marker,"              'controlled_probe_refusal_blocks_bootstrap': b'LYNX_VM_PROBE_FAILURE_EXIT=1' in raw,\n"+marker)
    save('test_wifi_v7_journals.py',source)
    print('Guarded UFS Wi-Fi checks/contact/trial tools prepared; no phone contacted.')
if __name__=='__main__':main()
