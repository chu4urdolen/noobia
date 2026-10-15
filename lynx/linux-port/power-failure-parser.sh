# Classify only the current marked attempt; retain raw numeric probe reasons.
lynx_station_failure_code() {
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
