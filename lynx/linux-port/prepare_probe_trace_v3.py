"""Prepare a trace diagnostic that separates worker, capture and probe failures."""
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

P = Path(__file__).resolve().parent
OUT = P / 'artifacts/busybox-probe-trace-v3'


def main():
    require(not OUT.exists(), 'Preserve prior candidate')
    reference = P / 'artifacts/busybox-probe-trace-v1'
    data = (reference / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest() == '2154dbd63d2de8bab56669db2dabf5f26bb9a8a16774a968717164e8dffccfd4', 'Reference changed')
    audit = json.loads((P / 'docs/ufs-trace-target-audit.json').read_text())
    require(audit['passed'] and audit['module_name'] == 'ufs_mediatek_mod', 'Missing stock target audit')
    module = P / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/ufs-mediatek-mod.ko'
    require(hashlib.sha256(module.read_bytes()).hexdigest() == audit['module_sha256'], 'Audited storage module changed')
    trace = (P / 'lynx-driver-trace.sh').read_text()
    marker = "    printf '256\\n' >"
    require(trace.count(marker) == 1, 'Unexpected collector boundary')
    extra = '''    # Standard deferred module probes: enabled before the driver is loaded.
    printf '%s\\n' 'p:lynx_ufs/mtk_probe_enter ufs_mediatek_mod:ufs_mtk_probe' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/mtk_probe_return ufs_mediatek_mod:ufs_mtk_probe ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/health_pid __arm64_sys_getpid ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
'''
    trace = trace.replace(marker, extra + marker, 1)
    trace = trace.replace('for trace_event in init_return domain_enter domain_return;', 'for trace_event in init_return domain_enter domain_return mtk_probe_enter mtk_probe_return health_pid;', 1)
    trace = trace.replace("    printf '1\\n' > \"$trace_instance/tracing_on\" || return 1\n", "    printf '1\\n' > \"$trace_instance/tracing_on\" || return 1\n    $BB sh -c 'echo $$' > /run/lynx/trace-health-pid || return 1\n", 1)
    classifier = (P / 'lynx-classify-driver-trace-v3.awk').read_bytes()
    old_runtime = (reference / 'trace-runtime.sh').read_text()
    boundary = old_runtime.index('# Coarse timing channel')
    runtime = trace + old_runtime[boundary:]
    start = runtime.index('        probe_code=8\n')
    end = runtime.index("        printf '%s %s\\n'", start)
    runtime = runtime[:start] + '''        probe_code=3
        if [ "$trace_ready" != 1 ]; then
            probe_code=1
        elif lynx_driver_trace_capture; then
            trace_expected_pid=$($BB cat /run/lynx/trace-health-pid)
            if $BB awk -v expected_pid="$trace_expected_pid" -f /etc/lynx/classify-driver-trace.awk /run/lynx/driver-trace.log > /run/lynx/driver-trace-result; then
                if IFS=' ' read -r probe_code trace_probe_count trace_probe_ret trace_health_count trace_entry_count < /run/lynx/driver-trace-result; then
                    case "$probe_code" in 2|4|5|6|7) ;; *) probe_code=3 ;; esac
                    log "TRACE_V2_CLASSIFIED code=$probe_code probe_count=$trace_probe_count probe_ret=$trace_probe_ret health_count=$trace_health_count entry_count=$trace_entry_count"
                fi
            fi
        fi
''' + runtime[end:]
    runtime = runtime.replace('            probe_code=8\n            probe_status=65535', '            probe_code=8\n            probe_status=65535', 1)
    boot = read_boot_v4(data)
    entries = read_newc(decompress(boot['ramdisk']))
    init = entries['init']['data']
    require(init.count(old_runtime.encode()) == 1, 'Original runtime changed')
    init = init.replace(old_runtime.encode(), runtime.encode(), 1)
    put(entries, 'init', init)
    put(entries, 'etc/lynx/classify-driver-trace.awk', classifier, 0o100644)
    token = secrets.token_hex(16)
    put(entries, 'etc/lynx/session-token', (token + '\n').encode(), 0o100644)
    ramdisk = pack(entries)
    header = bytearray(data[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda n: (n + 4095) // 4096 * 4096
    loaded = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    coverage = struct.unpack('!4sIIQQQ28x', data[-64:])[3]
    require(len(loaded) <= coverage, 'Original loaded area exceeded')
    image = loaded.ljust(coverage, b'\0') + data[coverage:]
    require(len(image) == len(data) and image[coverage:] == data[coverage:], 'Supplement or metadata changed')
    OUT.mkdir(mode=0o700)
    for name, raw in [('nord3-busybox-candidate.img', image), ('init-source', init), ('trace-runtime.sh', runtime.encode()), ('collector-source.sh', trace.encode())]:
        path = OUT / name
        path.write_bytes(raw)
        path.chmod(0o600)
    report = json.loads((reference / 'build-validation.json').read_text())
    report.update(candidate=str(OUT / 'nord3-busybox-candidate.img'), candidate_sha256=hashlib.sha256(image).hexdigest(),
                  init_sha256=hashlib.sha256(init).hexdigest(), ramdisk_bytes=len(ramdisk), session_token=token,
                  runtime_sha256=hashlib.sha256(runtime.encode()).hexdigest(), trace_source_sha256=hashlib.sha256(trace.encode()).hexdigest(),
                  classifier_sha256=hashlib.sha256(classifier).hexdigest(), phone_contacted=False, flash_eligible=False,
                  result_codes={'1': 'trace setup failed', '2': 'last MediaTek UFS probe returned success',
                                '3': 'trace capture or classifier read failed', '4': 'expected PID health event missing',
                                '5': 'healthy tracing but no completed MediaTek UFS probe', '6': 'last MediaTek UFS probe returned -517',
                                '7': 'last MediaTek UFS probe returned another error', '8': 'worker exceeded 180 second deadline'})
    (OUT / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['candidate_sha256', 'ramdisk_bytes', 'flash_eligible']}, indent=2))


if __name__ == '__main__':
    main()
