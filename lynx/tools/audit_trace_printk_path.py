"""Retain primary local published source for tracepoint-to-printk support."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def main():
    repo=P/'sources/kernel-mt6983'
    revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    rows=[]
    for name in ['trace.c','trace_events.c']:
        raw=subprocess.run(['git','-C',str(repo),'show','HEAD:kernel/trace/'+name],check=True,capture_output=True).stdout
        path=P/'docs/wifi-source-reference'/('printk-'+name)
        assert not path.exists() or path.read_bytes()==raw,'Preserve source reference'
        path.write_bytes(raw)
        lines=raw.decode().splitlines();matches=[]
        for i,line in enumerate(lines):
            if 'tp_printk' in line or 'trace_event_printk' in line or 'output_printk' in line:
                matches.append(dict(line=i+1,context=lines[max(0,i-3):i+6]))
        rows.append(dict(file=str(path),sha256=hashlib.sha256(raw).hexdigest(),matches=matches))
    report=dict(phone_contacted=False,published_revision=revision,sources=rows,limits='Published source differs from exact stock build. Native VM test required before assuming trace events reach printk/pstore.')
    out=P/'docs/trace-printk-source-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
