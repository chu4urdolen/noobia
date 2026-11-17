# Bounded current-boot supplicant snapshots, with no key logging or active scan.
lynx_wpa_snapshot() {
    $BB cat /etc/lynx/session-token > /run/lynx/wpa-snapshot-token || return 1
    $BB timeout 3 /sbin/wpa_cli -p /run/wpa_supplicant -i "$wifi_interface" status > /run/lynx/wpa-status 2>/run/lynx/wpa-status.err
    printf '%s\n' "$?" > /run/lynx/wpa-status-result
    $BB timeout 3 /sbin/wpa_cli -p /run/wpa_supplicant -i "$wifi_interface" scan_results > /run/lynx/wpa-scan 2>/run/lynx/wpa-scan.err
    printf '%s\n' "$?" > /run/lynx/wpa-scan-result
    wpa_blocked=0
    : > /run/lynx/wpa-rfkill
    for wpa_rf in /sys/class/rfkill/*; do
        [ -f "$wpa_rf/type" ] || continue
        IFS= read -r wpa_type < "$wpa_rf/type" || continue
        [ "$wpa_type" = wlan ] || continue
        wpa_soft='?'; wpa_hard='?'
        IFS= read -r wpa_soft < "$wpa_rf/soft" || true
        IFS= read -r wpa_hard < "$wpa_rf/hard" || true
        printf '%s %s %s\n' "$wpa_rf" "$wpa_soft" "$wpa_hard" >> /run/lynx/wpa-rfkill
        if [ "$wpa_soft" = 1 ] || [ "$wpa_hard" = 1 ]; then wpa_blocked=1; fi
    done
    printf '%s\n' "$wpa_blocked" > /run/lynx/wpa-rfkill-blocked
    lynx_wpa_failure_code
    printf '%s\n' "$nt_wpa" > /run/lynx/wpa-failure-code
}
lynx_wpa_failure_code() {
    nt_wpa=59
    wpa_token=$($BB cat /etc/lynx/session-token) || return 0
    wpa_snapshot_token=$($BB cat /run/lynx/wpa-snapshot-token) || return 0
    [ "$wpa_token" = "$wpa_snapshot_token" ] || return 0
    IFS= read -r wpa_status_rc < /run/lynx/wpa-status-result || return 0
    if [ "$wpa_status_rc" != 0 ]; then nt_wpa=50; return 0; fi
    wpa_state=$($BB sed -n 's/^wpa_state=//p' /run/lynx/wpa-status)
    case "$wpa_state" in ''|*'
'*) nt_wpa=50; return 0 ;; COMPLETED) nt_wpa=51; return 0 ;; esac
    IFS= read -r wpa_blocked < /run/lynx/wpa-rfkill-blocked || wpa_blocked=0
    if [ "$wpa_blocked" = 1 ]; then nt_wpa=54; return 0; fi
    wpa_log_code=$($BB awk '
        /WRONG_KEY|pre-shared key may be incorrect|4-Way Handshake failed/ { code=52 }
        /CTRL-EVENT-ASSOC-REJECT|CTRL-EVENT-AUTH-REJECT|CTRL-EVENT-EAP-FAILURE/ { code=53 }
        /CTRL-EVENT-CONNECTED/ { code=0 }
        END { print code+0 }
    ' /run/lynx/wpa.log) || wpa_log_code=0
    case "$wpa_log_code" in 52|53) nt_wpa=$wpa_log_code; return 0 ;; esac
    case "$wpa_state" in
        AUTHENTICATING|ASSOCIATING|ASSOCIATED|4WAY_HANDSHAKE|GROUP_HANDSHAKE) nt_wpa=57; return 0 ;;
        INTERFACE_DISABLED|INACTIVE) nt_wpa=58; return 0 ;;
    esac
    IFS= read -r wpa_scan_rc < /run/lynx/wpa-scan-result || return 0
    [ "$wpa_scan_rc" = 0 ] || return 0
    if $BB grep -q '^FAIL' /run/lynx/wpa-scan; then return 0; fi
    wpa_ssid=$($BB cat /etc/lynx/wpa-target-ssid) || return 0
    [ -n "$wpa_ssid" ] || return 0
    if $BB awk -F '\t' -v target="$wpa_ssid" '$5 == target { found=1 } END { exit found ? 0 : 1 }' /run/lynx/wpa-scan; then nt_wpa=56
    else nt_wpa=55; fi
}
