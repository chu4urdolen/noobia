"""Run the native reboot helper under exact stock kernel in isolated QEMU."""
import gzip
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'linux-port'))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import compress_legacy,decompress

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--guard-candidate',action='store_true')
    parser.add_argument('--console-candidate',action='store_true')
    parser.add_argument('--module-checkpoint',choices=['suppliers','with-mtu3'])
    parser.add_argument('--hold-control',action='store_true')
    parser.add_argument('--module-prefix',choices=['5','17','26'])
    parser.add_argument('--mtu3-supervisor',action='store_true')
    parser.add_argument('--count',type=int,choices=[40],required=True)
    parser.add_argument('--wifi-candidate',action='store_true')
    args=parser.parse_args()
    require(sum(bool(x) for x in [args.guard_candidate,args.console_candidate,args.module_checkpoint,args.hold_control,args.module_prefix,args.mtu3_supervisor,args.wifi_candidate])<=1,'Select one candidate')
    stamp=str(time.time_ns())
    prefix='emulated-busybox-console-' if args.console_candidate else ('emulated-boot-proof-guard-' if args.guard_candidate else 'emulated-reboot-helper-')
    if args.module_checkpoint:
        prefix='emulated-module-checkpoint-'+args.module_checkpoint+'-'
    if args.hold_control:
        prefix='emulated-minimal-hold-control-'
    if args.module_prefix:
        prefix='emulated-module-prefix-'+args.module_prefix+'-'
    if args.mtu3_supervisor:
        prefix='emulated-mtu3-supervisor-'
    if args.wifi_candidate:
        prefix='emulated-ufs-registration-guard-'
    output=ROOT/'linux-port/artifacts'/(prefix+stamp)
    output.mkdir(mode=0o700)
    helper=ROOT/'linux-port/artifacts/boot-proof-reboot.elf'
    data=helper.read_bytes()
    require(data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183,'Expected ELF64 ARM64')
    phoff,shoff=struct.unpack_from('<QQ',data,32)
    phsize,phcount,shsize,shcount,shnames=struct.unpack_from('<5H',data,54)
    require(phsize==56 and shsize==64,'Unexpected ELF tables')
    require(not any(struct.unpack_from('<I',data,phoff+n*phsize)[0]==3 for n in range(phcount)),'Unexpected interpreter')
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+n*shsize) for n in range(shcount)]
    names=data[sections[shnames][4]:sections[shnames][4]+sections[shnames][5]]
    text=next(x for x in sections if names[x[0]:].split(b'\0',1)[0]==b'.text')
    instructions=[dict(address=hex(i.address),mnemonic=i.mnemonic,operands=i.op_str)
                  for i in Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(data[text[4]:text[4]+text[5]],text[3])]
    require(sum(x['mnemonic']=='svc' for x in instructions)==2,'Unexpected syscall count')
    require(b'bootloader\0' in helper.read_bytes(),'Missing command string')
    stock=ROOT/'linux-port/artifacts/stock-cph2493-August-eu-ota'
    image_path=ROOT/'linux-port/artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img' if args.guard_candidate else stock/'boot.img'
    if args.console_candidate:
        image_path=ROOT/'linux-port/artifacts/busybox-August-busybox-console/nord3-busybox-candidate.img'
    if args.module_checkpoint:
        image_path=ROOT/'linux-port/artifacts/busybox-usb-module-checkpoints'/args.module_checkpoint/'nord3-busybox-candidate.img'
    if args.hold_control:
        image_path=ROOT/'linux-port/artifacts/busybox-minimal-hold-control/nord3-busybox-candidate.img'
    if args.module_prefix:
        image_path=ROOT/'linux-port/artifacts/busybox-usb-module-prefixes'/args.module_prefix/'nord3-busybox-candidate.img'
    if args.mtu3_supervisor:
        image_path=ROOT/'linux-port/artifacts/busybox-mtu3-timed-supervisor/nord3-busybox-candidate.img'
    if args.wifi_candidate:
        image_path=ROOT/'linux-port/artifacts'/'busybox-ufs-registration-only-v1'/'nord3-busybox-candidate.img'
    image_data=image_path.read_bytes()
    boot=read_boot_v4(image_data)
    require(hashlib.sha256(boot['kernel']).hexdigest()=='cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af','Stock kernel changed')
    entries=read_newc(decompress(boot['ramdisk']))
    if not (args.guard_candidate or args.console_candidate or args.module_checkpoint or args.hold_control or args.module_prefix or args.mtu3_supervisor or args.wifi_candidate):
        entries['init']=dict(mode=0o100755,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=helper.read_bytes())
    archive=bytearray()
    for inode,(name,item) in enumerate([*entries.items(),('TRAILER!!!',dict(mode=0,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=b''))],1):
        encoded=name.encode()+b'\0'
        fields=[inode,item['mode'],item['uid'],item['gid'],1,0,len(item['data']),0,0,item['rdevmajor'],item['rdevminor'],len(encoded),0]
        archive+=b'070701'+''.join(f'{value:08x}' for value in fields).encode()+encoded
        archive+=b'\0'*(-len(archive)%4);archive+=item['data'];archive+=b'\0'*(-len(archive)%4)
    archive+=b'\0'*(-len(archive)%512)
    require(read_newc(archive)==entries,'CPIO round trip failed')
    (output/'Image').write_bytes(gzip.decompress(boot['kernel']))
    initrd=(stock/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()+compress_legacy(bytes(archive))
    (output/'initramfs').write_bytes(initrd)
    runtime=ROOT/'tools/qemu/noble/root'
    command=[str(runtime/'usr/bin/qemu-system-aarch64'),'-L',str(runtime/'usr/share/qemu'),
             '-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg',
             '-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none',
             '-serial','stdio','-nic','none','-no-reboot','-kernel',str(output/'Image'),
             '-initrd',str(output/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env=dict(os.environ,LD_LIBRARY_PATH=str(runtime/'usr/lib/x86_64-linux-gnu'),
             QEMU_MODULE_DIR=str(runtime/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(ROOT/'tools/mtk-tmp'))
    started=time.monotonic()
    try:
        process=subprocess.run(command,env=env,capture_output=True,timeout=45 if args.console_candidate else (15 if args.guard_candidate or args.module_checkpoint or args.hold_control or args.module_prefix or args.mtu3_supervisor or args.wifi_candidate else 25))
        raw=process.stdout+process.stderr;code=process.returncode;timed_out=False
    except subprocess.TimeoutExpired as error:
        raw=(error.stdout or b'')+(error.stderr or b'');code=None;timed_out=True
    (output/'console.log').write_bytes(raw)
    observed=b"Restarting system with command 'bootloader'" in raw
    guarded=b'LYNX_BOOT_PROOF: NATIVE_PID1_ENTERED pid=1' in raw and b'DRIVER_GUARD_STOP wdt=0 mode=0' in raw
    console_guarded=b'LYNX_BUSYBOX: NATIVE_PID1_ENTERED pid=1' in raw and b'USB_SETUP_FAILED' in raw and b'RESET_GUARD_REFUSED' in raw
    checkpoint_guarded=b'LYNX_BOOT_PROOF: NATIVE_PID1_ENTERED pid=1' in raw and b'CHECKPOINT_RESET_GUARD_STOP' in raw and b'CHECKPOINT_MODULE_BEGIN' not in raw
    report=dict(phone_contacted=False,hardware_boot_proven=False,command=command,
                helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),instructions=instructions,
                console_sha256=hashlib.sha256(raw).hexdigest(),kernel_reboot_command_observed=observed,
                candidate_sha256=hashlib.sha256(image_data).hexdigest(),guard_stop_observed=guarded,
                busybox_console_failure_guard_observed=console_guarded,
                module_checkpoint_failure_guard_observed=checkpoint_guarded,
                exit_code=code,timed_out=timed_out,elapsed_seconds=time.monotonic()-started,
                limits='Validates helper execution and syscall under stock kernel; MT6983 reboot-mode drivers are not emulated.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(output/'result.json'),observed=observed,exit_code=code,timed_out=timed_out),indent=2))
    if args.module_checkpoint or args.module_prefix or args.mtu3_supervisor or args.wifi_candidate:
        require(checkpoint_guarded and not observed and timed_out,'Checkpoint must refuse hardware module loads and reboot without the real reset devices')
    elif args.console_candidate:
        require(console_guarded and not observed and timed_out,'BusyBox console failure guard missing or unexpected reboot')
    elif args.guard_candidate or args.hold_control:
        require(guarded and not observed and timed_out,'Expected guard stop absent or unexpected reboot')
    else:
        require(observed and code==0 and not timed_out,'Expected software-reboot proof absent')

if __name__=='__main__':main()
