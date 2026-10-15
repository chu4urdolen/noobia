"""Prepare a separately named reader for the finer trial's token/event meanings."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def main():
    source=(P/'prepare_retained_ufs_trace_image.py').read_text().replace('busybox-retained-ufs-trace-query-v1','busybox-retained-refclk-trace-query-v1').replace('busybox-ufs-trace-probe-v1','busybox-refclk-trace-probe-v2').replace('30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff','b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1')
    old="    for index,name in reference_manifest['trace_event_symbols'].items():codes[index]='last reference trace entry in selected record: '+name+('; generic core event may concern another device' if int(index)>=7 else '; entry does not prove return')"
    new="""    require(reference_manifest['trace_events_all_ufs_specific'],'Unexpected generic event mapping')
    for index,name in reference_manifest['trace_event_symbols'].items():codes[index]='last retained reference checkpoint: '+name+('; return marker retained, retval not retrieved' if index=='8' else '; marker brackets execution, not exact stop')"""
    assert old in source;source=source.replace(old,new)
    out=P/'prepare_retained_refclk_trace_image.py';assert not out.exists();compile(source,str(out),'exec');out.write_text(source);print(out)
if __name__=='__main__':main()
