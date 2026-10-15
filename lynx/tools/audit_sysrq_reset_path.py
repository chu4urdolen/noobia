"""Save published supported emergency-reset sources; no handset commands."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';D=P/'docs/wifi-source-reference';repo=P/'sources/kernel-mt6983'
paths={'sysrq':'drivers/tty/sysrq.c','arm64_process':'arch/arm64/kernel/process.c','arm64_emergency':'include/asm-generic/emergency-restart.h','arm64_kbuild':'arch/arm64/include/asm/Kbuild','generic_kbuild':'include/asm-generic/Kbuild','reboot_mode':'drivers/power/reset/reboot-mode.c','syscon_reboot_mode':'drivers/power/reset/syscon-reboot-mode.c'}
sources={};hashes={}
for name,path in paths.items():
    raw=subprocess.check_output(['git','-C',str(repo),'show','HEAD:'+path]);sources[name]=raw.decode();(D/(name+'.c.txt')).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
cfg=(P/'artifacts/stock-cph2493-August-eu-ota/kernel-config.txt').read_text()
checks={'stock_magic_sysrq_enabled':'CONFIG_MAGIC_SYSRQ=y\n' in cfg,
        'proc_trigger_available':'__handle_sysrq(c, false);' in sources['sysrq'],
        'sysrq_b_uses_emergency_restart':'emergency_restart();' in sources['sysrq'].split('static void sysrq_handle_reboot')[1].split('\n}')[0],
        'arm64_emergency_calls_machine_restart':'machine_restart(NULL);' in sources['arm64_emergency'],
        'generic_emergency_header_mandatory':'emergency-restart.h' in sources['generic_kbuild'],
        'reboot_mode_preparation_notifier':'register_reboot_notifier' in sources['reboot_mode'],
        'mode_persisted_by_syscon':'regmap_update_bits' in sources['syscon_reboot_mode']}
report={'passed':all(checks.values()),'checks':checks,'source_sha256':hashes,'published_revision':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'phone_contacted':False,'hardware_fastboot_destination_proven':False,'limits':'Reference source differs from exact stock commit. SysRq resets bypass normal shutdown. Bootloader mode depends on ordinary notifier having executed first; destination requires a controlled hardware test. No raw register access, authentication changes, partition writes or reset performed by this audit.'}
out=P/'docs/sysrq-reset-path.json'
if out.exists() and not json.loads(out.read_text()).get('passed'):
    out.rename(out.with_name('sysrq-reset-path-failed-'+str(time.time_ns())+'.json'))
out.write_text(json.dumps(report,indent=2)+'\n');print(out)
assert report['passed'],checks
