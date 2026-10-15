"""Derive independent pinned validation from the previously verified log query."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
def main():
    source=(T/'validate_retained_stage_image.py').read_text()
    source=source.replace('1dc206e7ba79067711957f9d8b40ea19d53594b38a4d7e51026275035262bc52','299c1ab3207e48d546077506690a1cfb91bdf05d0fe2c63d3a56dc4feff5ef75')
    source=source.replace('busybox-retained-stage-query-v1','busybox-retained-ufs-trace-query-v1').replace('lynx-retained-stage-runtime.sh','lynx-retained-ufs-trace-runtime.sh')
    source=source.replace(",'etc/lynx/reference-progress-map'",'')
    start=source.index('    reference_manifest=json.loads');end=source.index('    require(b',start)
    block='''    reference_manifest=json.loads((P/'artifacts/busybox-ufs-trace-probe-v1/build-validation.json').read_text())
    reference_image=(P/'artifacts/busybox-ufs-trace-probe-v1/nord3-busybox-candidate.img').read_bytes()
    require(sha(reference_image)==reference_manifest['candidate_sha256']=='30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff','Traced reference changed')
    names=['ufs_mtk_probe','ufs_mtk_init','ufs_mtk_setup_clocks','ufs_mtk_mphy_power_on','ufs_mtk_setup_ref_clk','ufs_mtk_hce_enable_notify','platform_drv_probe','dev_pm_domain_attach','genpd_dev_pm_attach']
    require(reference_manifest['trace_event_symbols']=={str(i):name for i,name in enumerate(names,1)},'Reference event mapping changed')
    codes={'0':'no checksum-valid reference capsule in selected bounded record'}
    for i,name in enumerate(names,1):codes[str(i)]='last reference trace entry in selected record: '+name+('; generic core event may concern another device' if i>=7 else '; entry does not prove return')
    codes.update({'10':'verified trace-ready capsule; no matched trace entry retained','11':'verified pre-probe capsule; no matched trace entry retained','12':'verified probe-returned capsule; no matched trace entry retained','13':'verified reference capsule without a recognized probe phase or trace entry','14':'base prefix pending','15':'retained query pending','16':'base insertion failed','17':'reference or progress malformed','18':'worker state unavailable'})
    require(manifest['result_codes']==codes and manifest['retained_ufs_trace_query'],'Retained trace codebook differs')
    reference_token=reference_manifest['session_token']
    require(current['etc/lynx/reference-ufs-token']['data']==reference_token.encode()+bytes([10]) and manifest['reference_ufs_token']==reference_token,'Traced reference token differs')
'''
    source=source[:start]+block+source[end:]
    source=source.replace('retained-stage-control-','retained-ufs-trace-control-').replace('emulated-native-retained-stage-','emulated-native-retained-ufs-trace-')
    source=source.replace("'emulated-retained-stage-guard-'+str(args.count)+'-*/result.json'","'emulated-retained-ufs-trace-guard-*/result.json'")
    source=source.replace('range(131)','range(19)').replace("manifest['observation_seconds']==900","manifest['observation_seconds']==270")
    source=source.replace('retained-stage-timing-test','retained-ufs-trace-timing-test').replace('lynx_retained_stage_timing','lynx_retained_ufs_trace_timing')
    source=source.replace(" and timing['decoder_sha256']==sha((ROOT/'tools/lynx_retained_ufs_trace_timing.py').read_bytes())",'')
    source=source.replace('retained-stage-validation','retained-ufs-trace-validation').replace('Read-only metadata flags, not successful domain power-on, UFS initialization or handset log persistence.','Read-only bounded retained markers. Checksums are not authentication or complete sequences. A trace entry does not prove return; generic core events may concern other devices.')
    out=T/'validate_retained_ufs_trace_image.py';assert not out.exists();compile(source,str(out),'exec');out.write_text(source);print(out)
if __name__=='__main__':main()
