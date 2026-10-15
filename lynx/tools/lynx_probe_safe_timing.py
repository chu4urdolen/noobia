"""Decode disjoint ordinary/emergency timing interpretations conservatively."""
from lynx_progress_timing import decode_progress_timing as ordinary_decode
def decode_progress_timing(operation,usb,manifest,baseline=None):
    offset=manifest.get('emergency_reset_offset_seconds')
    if offset!=5 or baseline is None:raise ValueError('Verified five-second fallback profile required')
    options=[]
    normal=ordinary_decode(operation,usb,manifest,baseline)
    emergency=ordinary_decode(operation,usb,manifest,baseline+offset)
    for path,result in [('ordinary',normal),('emergency-candidate',emergency)]:
        if result.get('timing_inferred_outcome') is not None:
            options.append({'reset_path':path,**result})
    result=dict(normal)
    result['timing_interpretations']=options
    result['emergency_fastboot_destination_independently_verified']=False
    if len(options)==1:
        result.update(options[0])
    else:
        result.update(timing_module_progress_field=None,timing_inferred_outcome=None,reset_path='ambiguous-or-unclassified')
    result['outcome_limits']='Indirect 90-second checkpoint; normal or five-second-later emergency candidate only when unique. Require reset evidence/non-interference. Inserted module is not binding proof; no persistent handset log retrieval.'
    return result
