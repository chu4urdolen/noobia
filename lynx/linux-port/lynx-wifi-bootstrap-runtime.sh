lynx_wifi_bootstrap_child() {
    log 'BOOTSTRAP_BASE_DRIVERS'
    lynx_load_checkpoint_modules /etc/lynx/bootstrap-base-modules.load || return 151
    log 'BOOTSTRAP_STORAGE_DRIVERS'
    lynx_load_checkpoint_modules /etc/lynx/bootstrap-storage-modules.load || return 152
    # UFS partition scanning can finish asynchronously after insmod returns.
    boot_seen=0
    for bootstrap_attempt in $($BB seq 1 30); do
        $BB mdev -s || return 153
        for bootstrap_entry in /sys/class/block/*/uevent; do
            [ -f "$bootstrap_entry" ] || continue
            if $BB grep -q '^PARTNAME=boot_a$' "$bootstrap_entry"; then boot_seen=1; break; fi
        done
        [ "$boot_seen" = 1 ] && break
        $BB sleep 1
    done
    [ "$boot_seen" = 1 ] || return 153
    log 'BOOTSTRAP_READ_OWN_BOOT_A'
    lynx_read_own_boot_payload || return 154
}
lynx_wifi_bootstrap() {
    IFS=' ' read -r bootstrap_uptime unused < /proc/uptime || return 1
    bootstrap_start=${bootstrap_uptime%%.*}
    case "$bootstrap_start" in ''|*[!0-9]*) return 1 ;; esac
    (
        lynx_wifi_bootstrap_child
        result=$?
        printf '%s\n' "$result" > /run/lynx/bootstrap-result.tmp
        $BB mv /run/lynx/bootstrap-result.tmp /run/lynx/bootstrap-result
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        if [ -f /run/lynx/bootstrap-result ]; then
            IFS= read -r result < /run/lynx/bootstrap-result || return 1
            [ "$result" = 0 ] && return 0
            log "BOOTSTRAP_FAILED status=$result"
            break
        fi
        IFS=' ' read -r bootstrap_uptime unused < /proc/uptime || return 1
        bootstrap_seconds=${bootstrap_uptime%%.*}
        case "$bootstrap_seconds" in ''|*[!0-9]*) return 1 ;; esac
        [ "$bootstrap_seconds" -lt "$((bootstrap_start+180))" ] || { log 'BOOTSTRAP_DEADLINE'; break; }
        $BB sleep 1
    done
    log 'BOOTSTRAP_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'BOOTSTRAP_REBOOT_RETURNED; NO_RETRY'
    return 1
}
