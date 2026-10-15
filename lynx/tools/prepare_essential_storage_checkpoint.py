"""Prepare essential storage checkpoint without the unrelated USB drivers."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent; P=R/'linux-port'; T=R/'tools'
def save(path, text):
    assert not path.exists(), str(path)
    if path.suffix=='.py': compile(text,str(path),'exec')
    path.write_text(text)
def main():
    source=(P/'lynx-power-controller-progress-runtime.sh').read_text()
    source=source.replace('# Clock registration checkpoint only: no scpsys, UFS, radio or network startup.', '# Essential stock storage modules and verified own-boot payload read; no radio startup.')
    source=source.replace('in 0|28|29|30|31|32|34)', 'in 41)')
    source=source.replace('progress_index+40','progress_index+42').replace('progress_index+80','progress_index+84').replace('progress_code=125','progress_code=127')
    marker='        lynx_progress_write 0 || exit 1'
    before='''        lynx_progress_write 42 || exit 1
        if lynx_storage_payload_checkpoint; then
            lynx_progress_write 84 || exit 1
        else
            lynx_progress_write 126 || exit 1
            log 'PROGRESS_STORAGE_PAYLOAD_FAILED'
            exit 1
        fi
'''
    assert source.count(marker)==1
    source=source.replace(marker,before+marker)
    reader='''lynx_storage_payload_checkpoint() {
    boot_seen=0
    for bootstrap_attempt in $($BB seq 1 30); do
        $BB mdev -s || return 1
        for bootstrap_entry in /sys/class/block/*/uevent; do
            [ -f "$bootstrap_entry" ] || continue
            if $BB grep -q '^PARTNAME=boot_a$' "$bootstrap_entry"; then boot_seen=1; break; fi
        done
        [ "$boot_seen" = 1 ] && break
        $BB sleep 1
    done
    [ "$boot_seen" = 1 ] || return 1
    lynx_read_own_boot_payload
}
'''
    save(P/'lynx-essential-storage-progress-runtime.sh',reader+source)
    builder=(P/'prepare_power_controller_progress_image.py').read_text()
    builder=builder.replace('choices=[34]','choices=[41]').replace('lynx-power-controller-progress-runtime.sh','lynx-essential-storage-progress-runtime.sh')
    builder=builder.replace("prefix=modules[:args.count]", "prefix=modules[:34]+entries['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()")
    builder=builder.replace("require(prefix[-2:]==['mtk-scpsys.ko','mtk-scpsys-mt6983.ko'],'Unexpected controller prefix')", "require(len(prefix)==41 and prefix[33]=='mtk-scpsys-mt6983.ko' and prefix[-1]=='ufs-mediatek-mod.ko','Unexpected storage list')")
    builder=builder.replace('i+40','i+42').replace('i+80','i+84')
    builder=builder.replace("'125':'malformed progress record','127':'worker progress unavailable'", "'42':'partition discovery or own boot payload read pending','84':'own boot payload verified and extracted','126':'partition discovery or own boot payload read failed','127':'worker progress unavailable or malformed'")
    builder=builder.replace("'all selected prefix insertions completed; binding not proven'", "'all essential module insertions and verified own boot payload read completed'")
    save(P/'prepare_essential_storage_progress_image.py',builder)
    print('Essential storage sources prepared; no phone contacted.')
if __name__=='__main__':main()
