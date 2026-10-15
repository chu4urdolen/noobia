# Diagnostic codes require an exact known userspace PID return as trace health.
# Only completed MediaTek probe returns classify storage success or failure.
BEGIN { health=0; count=0; entries=0; result="unknown"; bad=0 }
/health_pid:/ {
    if (match($0, /ret=[-]?[0-9]+/)) {
        value=substr($0,RSTART+4,RLENGTH-4)
        if (expected_pid ~ /^[0-9]+$/ && expected_pid > 0 && value == expected_pid) health++
    }
}
/mtk_probe_enter:/ { entries++ }
/mtk_probe_return:/ {
    if (match($0, /ret=[-]?[0-9]+/)) {
        result=substr($0,RSTART+4,RLENGTH-4)+0; count++
    } else bad++
}
END {
    if (!health) code=4
    else if (!count || bad) code=5
    else if (result == -517) code=6
    else if (result != 0) code=7
    else code=8
    print code, count, result, health, entries
}
