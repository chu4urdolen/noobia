# Read one bounded current-boot snapshot after our exact attempt marker.
lynx_station_failure_code() {
    nt_station_code=35
    IFS= read -r nt_station_status < /run/lynx/station-result || return 0
    case "$nt_station_status" in
        114) nt_station_code=25 ;;
        115) nt_station_code=26 ;;
        117) nt_station_code=27 ;;
        116)
            nt_station_token=$($BB cat /etc/lynx/session-token) || return 0
            case "$nt_station_token" in ''|*[!0-9a-f]*) return 0 ;; esac
            [ "${#nt_station_token}" = 32 ] || return 0
            [ -f /run/lynx/station-dmesg ] || return 0
            nt_station_code=$($BB awk -v marker="LYNX_STATION_ATTEMPT_BEGIN $nt_station_token" '
                $0 ~ ("(^|[[:space:]])" marker "$") { active=1; code=34; next }
                active {
                    if (index($0,"WMT turn on WIFI fail!")) code=28;
                    else if (index($0,"Set p2p mode handler is NULL")) code=29;
                    else if ($0 ~ /Get [a-zA-Z0-9_.-]+ net device timeout/) code=30;
                    else if (index($0,"Set wlan mode fail")) code=31;
                    else if (index($0,"Wi-Fi is resetting")) code=32;
                    else if (index($0,"WIFI_write invalid param")) code=33;
                }
                END { if (active) print code; else print 35 }
            ' /run/lynx/station-dmesg) || { nt_station_code=35; return 0; }
            ;;
    esac
    case "$nt_station_code" in 25|26|27|28|29|30|31|32|33|34|35) ;; *) nt_station_code=35 ;; esac
}
