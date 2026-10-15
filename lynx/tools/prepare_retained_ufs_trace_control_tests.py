"""Derive an extensive bounded trace parser corpus, retaining earlier tests."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
def main():
    source=(T/'test_retained_stage_control.py').read_text().replace('lynx-retained-stage-runtime.sh','lynx-retained-ufs-trace-runtime.sh').replace('busybox-retained-stage-query-v1','busybox-retained-ufs-trace-query-v1').replace('retained-stage-control-','retained-ufs-trace-control-')
    source=source.replace('0000000a 0200 0029','0000000a 0203 0010')
    start=source.index('specs=[');end=source.index('for mode,expected,records in specs:',start)
    source=source[:start]+'''def make_frame(status,sequence=2,stage=515):
    p=f'LXDG1 {reference} {sequence:08x} 0000000a {stage:04x} {status:04x}'
    return p+' '+hashlib.sha256(p.encode()).hexdigest()+'\\n'
def event(index,token=reference):return f'lx{token}_{index}: (fixture-function+0x0/0x20)\\n'
specs=[('empty',0,[]),('unrelated',0,['ordinary log\\n']),('invalid-checksum',0,[bad]),('valid-ready',10,[frame]),('before-probe',11,[make_frame(17)]),('after-probe',12,[make_frame(18)]),('other-stage',13,[make_frame(0,stage=512)]),('invalid-last-phase',10,[frame+bad]),('unverified-trace',0,[event(4)]),('invalid-capsule-trace',0,[bad+event(4)]),('wrong-token',10,[frame+event(4,'f'*32)]),('no-cross-file-mixing',10,[frame,event(4)]),('prefer-valid-trace',4,[frame+crash,frame+event(4)]),('eight-file-limit',0,['ordinary\\n']*8+[frame+event(4)]),('one-megabyte-limit',0,['N'*1048576+frame+event(4)]),('base-failed',16,[]),('base-pending',14,[]),('query-pending',15,['pending']),('last-entry',9,[frame+event(2)+event(9)]),('invalid-entry',10,[frame+event(0)+event(10)]),('checksum-valid-no-phase',13,[make_frame(0,stage=512)])]
specs.extend(('entry-'+str(i),i,[frame+event(i)]) for i in range(1,10))
cases=[]
'''+source[end:]
    source=source.replace(";(folder/'progress-map').write_bytes((P/'artifacts/busybox-retained-ufs-trace-query-v1/reference-progress-map').read_bytes())",'')
    source=source.replace(".replace('/etc/lynx/reference-progress-map',str(folder/'progress-map'))",'')
    out=T/'test_retained_ufs_trace_control.py';assert not out.exists();compile(source,str(out),'exec');out.write_text(source);print(out)
if __name__=='__main__':main()
