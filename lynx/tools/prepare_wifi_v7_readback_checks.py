"""Create pinned checks/trial tools for the separately preserved v7 readback."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port'
OLD='4eec20add7e57d70c5f29b11f02b7f726e8cc8ff24be1395aa738605c39bccf5'
NEW='8af0ebdcc356256a540dfdaa5fd5eff27bd9220737c880782d9ef53eb5becc22'
def common(s):
    return s.replace(OLD,NEW).replace('busybox-retained-refclk-trace-query-v1','busybox-retained-wifi-v7-query-v1').replace('lynx-retained-ufs-trace-runtime.sh','lynx-retained-wifi-v7-runtime.sh').replace('retained-refclk','retained-wifi-v7')
def save(name,s):
    p=T/name;assert not p.exists(),p;compile(s,str(p),'exec');p.write_text(s)
def main():
    s=common((T/'test_retained_refclk_control.py').read_text())
    start=s.index('specs=[');end=s.index('\ncases=[]',start)
    specs="""specs=[('empty',0,[]),('unrelated',0,['ordinary log'+chr(10)]),('invalid-checksum',0,[bad]),
        ('raw-token-only',0,[reference]),('trace-only',0,[event(4)]),
        ('other-stage',13,[make_frame(0,stage=512)]),
        ('eight-file-limit',0,['ordinary'+chr(10)]*8+[frame]),
        ('one-megabyte-limit',0,['N'*1048576+frame]),
        ('base-failed',16,[]),('base-pending',14,[]),('query-pending',15,['pending']),
        ('invalid-after-failure',2,[make_frame(152,stage=254)+bad]),
        ('reset-after-failure',2,[make_frame(152,stage=254)+make_frame(0,stage=240)]),
        ('major-after-failure',2,[make_frame(152,stage=254)+make_frame(0,stage=19)]),
        ('latest-byte-order',4,[make_frame(151,sequence=99,stage=254)+make_frame(154,sequence=1,stage=254)]),
        ('prefer-failure-record',3,[make_frame(0,stage=19),make_frame(153,stage=254)]),
        ('tied-files-first',1,[make_frame(151,stage=254),make_frame(154,stage=254)]),
        ('wrong-token',0,[make_frame(152,stage=254).replace(reference,'f'*32)]),
        ('symlink-ignored',0,[])]
for i,status in enumerate([151,152,153,154,99],1): specs.append(('failure-'+str(status),i,[make_frame(status,stage=254)]))
specs.append(('wifi-failure',6,[make_frame(134,stage=255)]))
for code,stage in [(7,16),(8,17),(8,515),(8,516),(8,4135),(9,18),(10,19),(11,20),(11,32),(12,33),(12,34),(12,35),(12,36),(13,37),(13,38),(13,39),(13,40)]:
    specs.append(('stage-'+str(stage),code,[make_frame(0,stage=stage)]))
"""
    s=s[:start]+specs+s[end:]
    needle='    for i,data in enumerate(records):'
    s=s.replace(needle,"    if mode=='symlink-ignored':\n        (folder/'outside').write_text(make_frame(152,stage=254));(folder/'pstore'/'link').symlink_to(folder/'outside')\n"+needle)
    save('test_retained_wifi_v7_control.py',s)
    s=common((T/'test_native_retained_refclk.py').read_text())
    s=s.replace('0203 0011','00fe 009a')
    s=s.replace("+'lx'+reference_token+'_4: (fixture-function+0x0/0x20)'+chr(10)","+'noise after failure'+chr(10)")
    save('test_native_retained_wifi_v7.py',s)
    save('test_retained_wifi_v7_guard.py',common((T/'test_retained_refclk_guard.py').read_text()))
    s=common((T/'validate_retained_refclk_image.py').read_text())
    s=s.replace('busybox-refclk-trace-probe-v2','busybox-wifi-ssh-twostage-v7').replace('b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1','9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c')
    start=s.index('    names=');end=s.index("    require(manifest['result_codes']",start)
    codes=json.loads((P/'docs/retained-wifi-v7-codebook.json').read_text())
    s=s[:start]+'    codes='+repr(codes)+'\n'+s[end:]
    s=s.replace("'log_index\\\" -le 8'", "'log_index\\\" -le 8'")
    s=s.replace('generic core events may concern other devices.','Record selection does not establish newest boot or the precise stopping point.')
    save('validate_retained_wifi_v7_image.py',s)
    s=common((T/'lynx_boot_a_retained_refclk_trial.py').read_text()).replace('validate_retained_refclk_image','validate_retained_wifi_v7_image')
    save('lynx_boot_a_retained_wifi_v7_trial.py',s)
    print('Pinned control/native/guard/independent validator and boot_a trial prepared.')
if __name__=='__main__':main()
