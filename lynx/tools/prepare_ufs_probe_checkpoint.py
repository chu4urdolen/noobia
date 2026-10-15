"""Prepare main-UFS insertion checkpoint with one guarded emergency reset."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';T=R/'tools'
def save(path,text):
    assert not path.exists(),str(path)
    if path.suffix=='.py':compile(text,str(path),'exec')
    path.write_text(text)
def main():
    source=(P/'lynx-essential-storage-progress-runtime.sh').read_text()
    source=source[source.index('# Essential stock storage'):]
    start=source.index('        lynx_progress_write 42 || exit 1\n')
    end=source.index('        lynx_progress_write 0 || exit 1\n',start)
    source=source[:start]+source[end:]
    source=source.replace('    lynx_progress_clock || return 1\n    progress_started=', '    [ -w /proc/sysrq-trigger ] || return 1\n    lynx_progress_clock || return 1\n    progress_started=',1)
    source=source.replace('    /bin/boot-proof-reboot\n', '    /bin/boot-proof-reboot &\n    progress_reset_pid=$!\n    # Ordinary notifier prepares bootloader mode before shutdown waits.\n    # No logging or device-control reads between that request and fallback.\n    $BB sleep 5\n    printf \'b\' > /proc/sysrq-trigger\n')
    source=source.replace('MODULE_PROGRESS_REBOOT_RETURNED; NO_RETRY','MODULE_PROGRESS_EMERGENCY_RESET_RETURNED; NO_RETRY')
    source=source.replace('# Essential stock storage modules and verified own-boot payload read; no radio startup.','# Main UFS module insertion only; no payload read, radio or partition writes.')
    save(P/'lynx-ufs-probe-progress-runtime.sh',source)
    builder=(P/'prepare_essential_storage_progress_image.py').read_text().replace('lynx-essential-storage-progress-runtime.sh','lynx-ufs-probe-progress-runtime.sh').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-ufs-probe-emergency-v1'")
    builder=builder.replace("'all essential module insertions and verified own boot payload read completed'","'all essential module insertions completed; binding not proven'")
    builder=builder.replace("'42':'partition discovery or own boot payload read pending','84':'own boot payload verified and extracted','126':'partition discovery or own boot payload read failed',",'')
    builder=builder.replace("module_progress_count=args.count,", "module_progress_count=args.count,emergency_reset_offset_seconds=5,payload_read_attempted=False,")
    save(P/'prepare_ufs_probe_progress_image.py',builder)
    control=(T/'test_essential_storage_progress_control.py').read_text().replace('lynx-essential-storage-progress-runtime.sh','lynx-ufs-probe-progress-runtime.sh').replace('essential-storage-progress-control-','ufs-probe-progress-control-')
    # Test fixture must replace the host's reset interface before shell execution.
    control=control.replace("(folder/'count').write_text('41\\n')", "(folder/'count').write_text('41\\n');(folder/'sysrq').touch()")
    control=control.replace(".replace('/bin/boot-proof-reboot',str(reset))", ".replace('/bin/boot-proof-reboot',str(reset)).replace('/proc/sysrq-trigger',str(folder/'sysrq'))\n        assert '/proc/sysrq-trigger' not in source")
    control=control.replace("assert (folder/'resets').read_text().splitlines()==['reset'],name", "assert (folder/'resets').read_text().splitlines()==['reset'],name\n        assert (folder/'sysrq').read_bytes()==b'b',name")
    control=control.replace('range(1,42):','range(35,42):')
    save(T/'test_ufs_probe_progress_control.py',control)
    print('UFS probe/fallback sources prepared; no handset contacted.')
if __name__=='__main__':main()
