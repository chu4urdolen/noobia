"""Decode timeout-context bits without misreporting them as errno values."""
from lynx_errno_timing import decode_errno_timing

BITS={1:'ufs0 power-on error',2:'ufs0 SRAM/bus power-on error',
      4:'UFS controller enable error',8:'UFS link startup -110',
      16:'UFS UIC completion timeout',32:'targeted timeout context'}

def decode_timeout_log_timing(operation,usb,manifest):
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
