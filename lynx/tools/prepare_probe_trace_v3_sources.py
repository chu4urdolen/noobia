"""Preserve v2; place the timeout in a return window after its deadline."""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / 'linux-port'


def main():
    classifier = (P / 'lynx-classify-driver-trace-v2.awk').read_text()
    assert classifier.count('else code=8') == 1
    classifier = classifier.replace('else code=8', 'else code=2', 1)
    builder = (P / 'prepare_probe_trace_v2.py').read_text()
    builder = builder.replace('busybox-probe-trace-v2', 'busybox-probe-trace-v3').replace('lynx-classify-driver-trace-v2.awk', 'lynx-classify-driver-trace-v3.awk')
    builder = builder.replace('case "$probe_code" in 4|5|6|7|8)', 'case "$probe_code" in 2|4|5|6|7)')
    builder = builder.replace("'            probe_code=2\\n            probe_status=65535'", "'            probe_code=8\\n            probe_status=65535'")
    builder = builder.replace("'2': 'worker exceeded 180 second deadline'", "'2': 'last MediaTek UFS probe returned success'")
    builder = builder.replace("'8': 'last MediaTek UFS probe returned success'", "'8': 'worker exceeded 180 second deadline'")
    for name, text in [('lynx-classify-driver-trace-v3.awk', classifier), ('prepare_probe_trace_v3.py', builder)]:
        target = P / name
        assert not target.exists(), 'Preserve existing sources'
        target.write_text(text)
    print('v3 sources ready. v2 remains offline-only: timeout code2 fell before worker deadline.')


if __name__ == '__main__':
    main()
