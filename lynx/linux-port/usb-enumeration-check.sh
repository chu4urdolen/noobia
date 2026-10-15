# Called after gadget binding. UDC binding alone is not a host connection.
lynx_wait_usb_configured() {
    controller=$1
    attempts=0
    while [ "$attempts" -lt 30 ]; do
        state=$($BB cat "$controller/state" 2>/dev/null) || return 1
        [ "$state" = configured ] && return 0
        attempts=$((attempts+1))
        $BB sleep 1
    done
    return 1
}
