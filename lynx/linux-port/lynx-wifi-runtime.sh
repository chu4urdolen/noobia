# All state/logs live in RAM. Only factory calibration is mounted read-only.
lynx_stage() {
    printf '%s\n' "$1" > /run/lynx/phase
    log "WIFI_STAGE $1"
}
lynx_wifi_worker() {
    lynx_stage BASE_DRIVERS
    lynx_load_checkpoint_modules /etc/lynx/wifi-base-modules.load || return 131
    lynx_stage STORAGE_DRIVERS
    lynx_load_checkpoint_modules /etc/lynx/wifi-storage-modules.load || return 132
    $BB mdev -s || return 133
    lynx_stage FACTORY_CALIBRATION_READONLY
    lynx_read_factory_calibration || return 134
    lynx_stage WIFI_DRIVERS
    lynx_load_checkpoint_modules /etc/lynx/wifi-radio-modules.load || return 135
    $BB mdev -s || return 136
    lynx_stage CONNECTIVITY_CHIP_CHECK
    /bin/lynx-wifi-control --chip || return 137
    lynx_stage FACTORY_CALIBRATION_TO_DRIVER_RAM
    /bin/lynx-wifi-control --nvram || return 138
    # Configuration handler is optional in vendor builds; preserve its status.
    /bin/lynx-wifi-control --drvcfg
    cfg_result=$?
    log "STOCK_DRIVER_CONFIG_SUBMISSION status=$cfg_result"
    lynx_stage WIFI_STATION_POWER_ON
    /bin/lynx-wifi-control --station || return 139
    lynx_stage WLAN_INTERFACE_WAIT
    wifi_interface=''
    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        for name in wlan0 wlan1; do
            [ -d "/sys/class/net/$name" ] || continue
            wifi_interface=$name
            break
        done
        [ -n "$wifi_interface" ] && break
        $BB sleep 1
    done
    [ -n "$wifi_interface" ] || return 140
    printf '%s\n' "$wifi_interface" > /run/lynx/interface
    $BB ip link set "$wifi_interface" up || return 141
    lynx_stage WPA_SUPPLICANT
    /sbin/wpa_supplicant -B -D nl80211 -i "$wifi_interface" -c /etc/lynx/wpa_supplicant.conf -f /run/lynx/wpa.log || return 142
    lynx_stage WPA_ASSOCIATION_WAIT
    connected=0
    for attempt in $($BB seq 1 45); do
        if /sbin/wpa_cli -p /run/wpa_supplicant -i "$wifi_interface" status | $BB grep -q '^wpa_state=COMPLETED$'; then connected=1; break; fi
        $BB sleep 1
    done
    [ "$connected" = 1 ] || return 143
    lynx_stage DHCP
    $BB udhcpc -f -n -q -t 6 -T 4 -i "$wifi_interface" -x hostname:lynx -s /bin/lynx-dhcp || return 144
    address=$($BB cat /run/lynx/address) || return 145
    lynx_stage SSH_SERVER
    /usr/sbin/dropbear -F -E -s -j -k -p "$address:22" -r /etc/dropbear/lynx_ed25519_host_key > /run/lynx/dropbear.log 2>&1 &
    ssh_pid=$!
    $BB sleep 2
    kill -0 "$ssh_pid" || return 146
    printf '%s\n' "$ssh_pid" > /run/lynx/ssh.pid
    lynx_stage SSH_READY_WAITING_FOR_PINNED_HOST
    printf '%s\n' ready > /run/lynx/ssh-ready
}
lynx_clock() {
    IFS=' ' read -r uptime unused < /proc/uptime || return 1
    seconds=${uptime%%.*}
    case "$seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_wifi_supervise() {
    # The kernel lacks devtmpfs, and ash background jobs require /dev/null.
    [ -c /dev/null ] || return 1
    lynx_clock || return 1
    start=$seconds
    (
        lynx_wifi_worker
        result=$?
        printf '%s\n' "$result" > /run/lynx/worker-result.tmp
        $BB mv /run/lynx/worker-result.tmp /run/lynx/worker-result
    ) >> /run/lynx/boot.log 2>&1 &
    worker=$!
    log "WIFI_WORKER_STARTED pid=$worker deadline_boot_seconds=$((start+240))"
    host=$($BB cat /etc/lynx/host-ip) || return 1
    token=$($BB cat /etc/lynx/session-token) || return 1
    while :; do
        lynx_clock || return 1
        if [ -f /run/lynx/host-confirmed ]; then
            if IFS= read -r confirmation < /run/lynx/host-confirmed && [ "$confirmation" = "$token" ]; then
                log 'PINNED_HOST_SSH_CONFIRMED; AUTOMATIC_REBOOT_CANCELLED'
                return 0
            fi
        fi
        if [ -f /run/lynx/worker-result ]; then
            IFS= read -r result < /run/lynx/worker-result || return 1
            case "$result" in ''|*[!0-9]*) return 1 ;; esac
            if [ "$result" != 0 ]; then
                log "WIFI_WORKER_FAILED status=$result"
                break
            fi
        fi
        [ "$seconds" -lt "$((start+240))" ] || { log 'WIFI_HOST_CONTACT_DEADLINE'; break; }
        if [ -f /run/lynx/ssh-ready ]; then
            # Only public discovery metadata leaves the phone before SSH.
            printf 'LYNX_HELLO %s\n' "$token" | /usr/bin/nc -u -w 1 "$host" 5514
        fi
        $BB sleep 1
    done
    # Avoid platform sysfs after probing; a failed probe could hold locks.
    log 'REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'REBOOT_RETURNED; NO_RETRY'
    return 1
}
