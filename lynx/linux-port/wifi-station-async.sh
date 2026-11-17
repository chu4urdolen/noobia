# Normal stock station requests; at most one evidence-gated completion attempt.
lynx_wifi_station_once() {
    station_token=$($BB cat /etc/lynx/session-token) || return 1
    printf '<6>LYNX_STATION_ATTEMPT_BEGIN %s\n' "$station_token" > /dev/kmsg || true
    /bin/lynx-wifi-control --station
    station_status=$?
    printf '%s\n' "$station_status" > /run/lynx/station-result
    if [ "$station_status" != 0 ]; then
        $BB dmesg | $BB tail -c 1048576 > /run/lynx/station-dmesg
        lynx_capture_wifi_worker_stack
        return 1
    fi
    return 0
}
lynx_wifi_station_request() {
    . /etc/lynx/power-stack-parser.sh || return 1
    . /etc/lynx/wifi-worker-stack.sh || return 1
    . /etc/lynx/wifi-async-ready.sh || return 1
    if lynx_wifi_station_once; then return 0; fi
    for station_record in station-result station-dmesg wifi-worker-pid wifi-worker-stack wifi-worker-stack-result wifi-worker-status wifi-worker-wchan; do
        if [ -f "/run/lynx/$station_record" ]; then
            $BB cp "/run/lynx/$station_record" "/run/lynx/$station_record.first" || true
        fi
    done
    log 'WIFI_ASYNC_COMPLETION_WAIT; NO_OVERLAPPING_REQUEST'
    lynx_wifi_async_ready || return 1
    log 'WIFI_ASYNC_PROBE_SUCCESS_IDLE_AND_DRIVER_BOUND; ONE_COMPLETION_REQUEST'
    lynx_wifi_station_once
}
