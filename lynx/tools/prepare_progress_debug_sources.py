"""Add preserved hex checkpoints and prepare debug calibration/one-module images."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';T=ROOT/'tools'
def save(path,text):
    assert not path.exists();path.write_text(text)
def main():
    source=(P/'lynx-module-progress-v2-runtime.sh').read_text().replace('in 28|29|30|31|32)', 'in 0|28|29|30|31|32)')
    source=source.replace('    $BB mv /run/lynx/module-progress.tmp /run/lynx/module-progress\n','''    $BB mv /run/lynx/module-progress.tmp /run/lynx/module-progress || return 1
    if [ "${progress_diag_ready:-0}" = 1 ]; then lynx_diag_emit 512 "$1" || true; fi
    return 0
''',1)
    source=source.replace('        progress_index=0\n','''        progress_diag_ready=0
        if lynx_diag_init bootstrap; then progress_diag_ready=1; fi
        progress_index=0
''',1)
    save(P/'lynx-module-progress-debug-runtime.sh',source)
    builder=(P/'prepare_module_progress_v2_image.py').read_text()
    builder=builder.replace('import hashlib,json,secrets,struct','import argparse,hashlib,json,secrets,struct')
    builder=builder.replace(";OUT=P/'artifacts/busybox-module-progress-v2'",'')
    builder=builder.replace('def main():\n',"def main():\n    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[0,28,29,30,31,32],required=True);args=parser.parse_args()\n    OUT=P/'artifacts'/('busybox-module-progress-debug-'+str(args.count)+'-v1')\n",1)
    builder=builder.replace('lynx-module-progress-v2-runtime.sh','lynx-module-progress-debug-runtime.sh')
    builder=builder.replace('prefix=modules[:28]','prefix=modules[:args.count]')
    start=builder.index('    require(len(prefix)==28');end=builder.index("    put(entries,'etc/lynx/progress-modules.load'",start)
    builder=builder[:start]+"    require(args.count==0 or prefix[-1].startswith('clk-mt6983-'),'Unexpected prefix')\n    put(entries,'etc/lynx/progress-count',(str(args.count)+'\\n').encode(),0o100644)\n"+builder[end:]
    marker="    align =" # Existing builder packs before constructing header.
    target="struct.pack_into('<I',header,12,len(rd));align="
    assert builder.count(target)==1
    builder=builder.replace(target,"struct.pack_into('<I',header,12,len(rd));cmdline=(boot['cmdline']+' initcall_debug').encode();require(len(cmdline)<1536,'Commandline size');header[44:1580]=cmdline.ljust(1536,b'\\0');align=",1)
    builder=builder.replace("'0':'all28prefix insertions completed; binding not proven'", "'0':'all selected prefix insertions completed; binding not proven'")
    builder=builder.replace("module_progress_prefix=prefix,", "module_progress_prefix=prefix,module_progress_count=args.count,initcall_debug_enabled=True,calibration_only=args.count==0,")
    builder=builder.replace("    report=json.loads((F/'build-validation.json').read_text());", "    codebook=json.loads(entries['etc/lynx/diag-codebook.json']['data']);codebook['512']='module progress field';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(codebook,indent=2)+'\\n').encode(),0o100644)\n    report=json.loads((F/'build-validation.json').read_text());")
    # Codebook must enter the compressed ramdisk, not just the report.
    block="    codebook=json.loads(entries['etc/lynx/diag-codebook.json']['data']);codebook['512']='module progress field';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(codebook,indent=2)+'\\n').encode(),0o100644)\n"
    builder=builder.replace(block,'');builder=builder.replace('    rd=pack(entries);',block+'    rd=pack(entries);',1)
    builder=builder.replace('report.update(candidate=', 'report.update(diagnostic_codebook=codebook,candidate=',1)
    save(P/'prepare_module_progress_debug_image.py',builder)
    with (P/'.gitignore').open('a') as f:f.write('\nartifacts/busybox-module-progress-*/\n')
    print('Debug baseline and one-module builders prepared; no handset access.')
if __name__=='__main__':main()
