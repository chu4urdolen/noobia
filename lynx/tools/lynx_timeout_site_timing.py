"""Decode timeout-context bits without misreporting them as errno values."""
from lynx_errno_timing import decode_errno_timing

BITS={1:'MediaTek UFS probe error -110',2:'ufs0 power-provider error -110',
      4:'UFS platform initialization error',8:'UFS variant initialization -110',
      16:'UFS regulator error',32:'UFS clock error'}

def decode_timeout_site_timing(operation,usb,manifest):
    report=decode_errno_timing(operation,usb,manifest)
    report.pop('timing_decoded_platform_return')
    code=int(report['timing_nearest_code_hex'],16)
    accepted=report['timing_inferred_outcome'] is not None
    mask=code if accepted and code<64 else None
    report.update(timing_kernel_log_mask=mask,
                  timing_kernel_log_indications=[text for bit,text in BITS.items() if mask is not None and mask & bit],
                  producer_platform_return_gate=-110 if mask is not None else None,
                  outcome_limits='Indirect timing field, gated on same-boot live-target platform return -110 and PID health. Require reset/non-interference evidence. Log errors can cascade; no matched message does not imply no failure.')
    if accepted and 64<=code<124:report['timing_inferred_outcome']=None
    return report
