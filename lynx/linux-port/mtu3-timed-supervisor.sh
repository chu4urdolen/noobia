# Runtime state lives only in tmpfs. One guarded reset request, from the parent.
# The caller must validate the real watchdog/reboot-mode guards before invoking.
lynx_mtu3_supervise() {
    # ash redirects asynchronous stdin to /dev/null before running the child.
    # This stock kernel has no devtmpfs: create the node explicitly.
    [ -c /dev/null ] || $BB mknod -m 666 /dev/null c 1 3 || return 1
    $BB mkdir -p /run || return 1
    $BB mount -t tmpfs -o size=1m tmpfs /run || return 1
    lynx_now || return 1
    start=$lynx_seconds
    (
        $BB insmod /lib/modules/mtu3.ko
        code=$?
        printf '%s\n' "$code" > /run/mtu3-result.tmp
        $BB mv /run/mtu3-result.tmp /run/mtu3-result
    ) &
    loader=$!
    log "MTU3_CHILD_STARTED pid=$loader boot_seconds=$start"
    # Observe a fixed window, then encode the outcome in the reset deadline.
    lynx_wait_until "$((start+15))" || return 1
    if [ -f /run/mtu3-result ]; then
        IFS= read -r result < /run/mtu3-result || return 1
        case "$result" in
            0) deadline=$((start+20)); outcome=load-returned-success ;;
            ''|*[!0-9]*) log 'INVALID_CHILD_RESULT'; return 1 ;;
            *) deadline=$((start+40)); outcome=load-returned-error ;;
        esac
    else
        deadline=$((start+60)); outcome=no-result-within-15-seconds
    fi
    log "MTU3_OUTCOME $outcome reboot_at_boot_seconds=$deadline"
    lynx_wait_until "$deadline" || return 1
    # Do not enumerate platform sysfs again: a blocked probe could hold locks.
    # These exact reset devices were checked immediately before starting child.
    log 'REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'REBOOT_RETURNED; NO_RETRY'
}
lynx_now() {
    IFS=' ' read -r uptime remainder < /proc/uptime || return 1
    lynx_seconds=${uptime%%.*}
    case "$lynx_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_wait_until() {
    target=$1
    while :; do
        lynx_now || return 1
        [ "$lynx_seconds" -ge "$target" ] && return 0
        $BB sleep 1
    done
}
