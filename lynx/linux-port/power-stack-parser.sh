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
