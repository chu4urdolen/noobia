"""Decode a calibrated harmless-interface status, not a boot-time calibration."""
def decode_progress_timing(operation,usb,manifest,baseline=None):
    if baseline is None or not 10<=baseline<=40 or not manifest.get('reset_interface_check'):raise ValueError('Verified interface profile required')
    if not usb.get('observation_complete') or not usb.get('fastboot_return_observed'):raise ValueError('Completed Fastboot capture required')
    event=usb['events'][-1]
    if not any(item['identifier']=='0e8d:201c' for item in event['usb']):raise ValueError('Last event is not Fastboot')
    elapsed=event['monotonic_seconds']-operation['started_monotonic']-operation['elapsed_seconds']
    wall=(event['wall_time_ns']-operation['finished_ns'])/1e9
    tolerance=manifest['timing_match_tolerance_seconds']
    if not 0<tolerance<1:raise ValueError('Ambiguous timing tolerance')
    candidates=[(n,abs(elapsed-baseline-120-2*n)) for n in [0,1,2,3,125,127]]
    matches=[(n,error) for n,error in candidates if error<=tolerance]
    code,error=min(candidates,key=lambda item:item[1])
    accepted=len(matches)==1
    return {'return_seconds_after_reboot':elapsed,'wall_return_seconds_after_reboot':wall,'wall_monotonic_disagreement_seconds':wall-elapsed,'timing_clock':'monotonic','timing_nearest_code_hex':'0x'+format(code,'02x'),'timing_residual_seconds':error,'timing_inferred_outcome':manifest['result_codes'][str(code)] if accepted else None,'reset_interface_presence_field':code if accepted else None,'outcome_limits':'Indirect harmless help write status at90s; require matching software reset and non-interference. Accepted help does not prove an emergency reset reaches Fastboot.'}
