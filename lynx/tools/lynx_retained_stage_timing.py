"""Decode five-second snapshot slots; do not conflate them with the older grid."""
def decode_progress_timing(operation,usb,manifest,baseline=None):
    if baseline is None or not 10<=baseline<=40:raise ValueError('Verified baseline required')
    if manifest['target_delays_seconds']!={str(n):120+5*n for n in range(131)} or manifest['timing_match_tolerance_seconds']!=2:raise ValueError('Retained stage grid changed')
    if not usb.get('observation_complete') or not usb.get('fastboot_return_observed'):raise ValueError('Completed Fastboot return required')
    event=usb['events'][-1]
    if not any(item['identifier']=='0e8d:201c' for item in event['usb']):raise ValueError('Last event is not Fastboot')
    elapsed=event['monotonic_seconds']-operation['started_monotonic']-operation['elapsed_seconds'];wall=(event['wall_time_ns']-operation['finished_ns'])/1e9
    code,error=min(((n,abs(elapsed-baseline-120-5*n)) for n in range(131)),key=lambda item:item[1]);text=manifest['result_codes'][str(code)]
    accepted=error<=2 and not text.startswith('reserved')
    return {'return_seconds_after_reboot':elapsed,'wall_return_seconds_after_reboot':wall,'wall_monotonic_disagreement_seconds':wall-elapsed,'timing_clock':'monotonic','timing_nearest_code_hex':'0x'+format(code,'02x'),'timing_residual_seconds':error,'timing_inferred_outcome':text if accepted else None,'timing_module_progress_field':code if accepted else None,'outcome_limits':'Indirect 90-second snapshot with five-second slots and at most two seconds assumed profile/startup variation; require supported reset and non-interference. Last verified marker in one bounded reference record, not exact instruction stop, complete sequence or guaranteed newest boot across files.'}
