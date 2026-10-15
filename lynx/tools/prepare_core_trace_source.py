"""Prepare observational tracing of checks before the platform driver probe."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / 'linux-port'


def main():
    source = (P / 'artifacts/busybox-probe-trace-v3/collector-source.sh').read_text()
    marker = "    printf '256\\n' >"
    assert source.count(marker) == 1
    events = '''    printf '%s\\n' 'p:lynx_ufs/supplier_enter device_links_check_suppliers name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/supplier_return device_links_check_suppliers ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'p:lynx_ufs/pins_enter pinctrl_bind_pins name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/pins_return pinctrl_bind_pins ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
'''
    source = source.replace(marker, events + marker, 1)
    source = source.replace('mtk_probe_return health_pid;', 'mtk_probe_return health_pid supplier_enter supplier_return pins_enter pins_return;', 1)
    capture = '    return 0\n}\n'
    assert source.count(capture) == 2
    # Additional raw read-only context; none of this is a persistent log promise.
    at = source.rindex(capture)
    source = source[:at] + '''    if [ ! -f /sys/kernel/debug/devices_deferred ]; then
        $BB mount -t debugfs debugfs /sys/kernel/debug
    fi
    if [ -f /sys/kernel/debug/devices_deferred ]; then
        $BB cat /sys/kernel/debug/devices_deferred > /run/lynx/devices-deferred.log
        $BB chmod 600 /run/lynx/devices-deferred.log
    fi
''' + source[at:]
    path = P / 'lynx-driver-trace-core-v1.sh'
    assert not path.exists(), 'Preserve prior source'
    path.write_text(source)
    print(path)


if __name__ == '__main__':
    main()
