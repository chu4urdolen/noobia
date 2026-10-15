# Classify only the current marked attempt; retain raw numeric probe reasons.
lynx_power_failure_code() {
    nt_station_code=35
    IFS= read -r nt_station_status < /run/lynx/station-result || return 0
    [ "$nt_station_status" = 116 ] || return 0
    nt_station_token=$($BB cat /etc/lynx/session-token) || return 0
    case "$nt_station_token" in ''|*[!0-9a-f]*) return 0 ;; esac
    [ "${#nt_station_token}" = 32 ] || return 0
    [ -f /run/lynx/station-dmesg ] || return 0
    nt_station_code=$($BB awk -v marker="LYNX_STATION_ATTEMPT_BEGIN $nt_station_token" '
        $0 ~ ("(^|[[:space:]])" marker "$") { active=1; detail=35; result=35; next }
        active {
            if ($0 ~ /WiFi on\/off takes more than [0-9]+ seconds/) detail=25;
            else if (index($0,"[WIFI-FW]") && index($0,"Invalid pointer")) detail=26;
            else if ($0 ~ /wlanProbe: probe failed, reason:[0-7][[:space:]]*$/) {
                value=$0; sub(/^.*wlanProbe: probe failed, reason:/,"",value);
                detail=27+value;
            }
            if (index($0,"WMT turn on WIFI fail!")) result=detail;
        }
        END { if (active) print result; else print 35 }
    ' /run/lynx/station-dmesg) || { nt_station_code=35; return 0; }
    case "$nt_station_code" in 25|26|27|28|29|30|31|32|33|34|35) ;; *) nt_station_code=35 ;; esac
}
# Called only after the current marked attempt reported power-control timeout.
lynx_stack_failure_code() {
    lynx_power_failure_code
    [ "$nt_station_code" = 25 ] || { nt_station_code=34; return 0; }
    nt_station_code=33
    IFS= read -r ws_result < /run/lynx/wifi-worker-stack-result || return 0
    case "$ws_result" in
        31|32|33) nt_station_code=$ws_result; return 0 ;;
        0) ;;
        *) return 0 ;;
    esac
    [ -s /run/lynx/wifi-worker-stack ] || return 0
    if $BB grep -Eq '(^|[^a-zA-Z0-9_])mtk_wland_thread_main\+0x214/0x[0-9a-f]+([[:space:]]|$)' /run/lynx/wifi-worker-stack; then
        nt_station_code=25
    elif $BB grep -Eq '(request_firmware|firmware_request|fw_get_filesystem_firmware|fw_load_from_user_helper)' /run/lynx/wifi-worker-stack; then
        nt_station_code=27
    elif $BB grep -Eq '(conninfra|consys_|wlanPowerOn|wf_pwr_on)' /run/lynx/wifi-worker-stack; then
        nt_station_code=28
    elif $BB grep -Eq '(^|[^a-zA-Z0-9_])wlanProbe\+0x[0-9a-f]+/' /run/lynx/wifi-worker-stack; then
        nt_station_code=26
    elif $BB grep -Eq '(schedule|completion|mutex|msleep|wait_)' /run/lynx/wifi-worker-stack; then
        nt_station_code=29
    else nt_station_code=30; fi
}
