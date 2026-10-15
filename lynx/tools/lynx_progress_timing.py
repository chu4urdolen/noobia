"""Bounded monotonic checkpoint decoder; count0 is calibration only."""
def decode_progress_timing(operation,usb,manifest,baseline=None):
    if not usb.get('observation_complete') or not usb.get('fastboot_return_observed'):raise ValueError('Completed Fastboot return required')
    event=usb['events'][-1]
    if not any(item['identifier']=='0e8d:201c' for item in event['usb']):raise ValueError('Last USB event is not Fastboot')
    elapsed=event['monotonic_seconds']-(operation['started_monotonic']+operation['elapsed_seconds'])
    wall=(event['wall_time_ns']-operation['finished_ns'])/1e9
    if manifest['target_delays_seconds']!={str(n):120+2*n for n in range(128)}:raise ValueError('Timing grid differs')
    result={'return_seconds_after_reboot':elapsed,'wall_return_seconds_after_reboot':wall,'wall_monotonic_disagreement_seconds':wall-elapsed,'timing_clock':'monotonic'}
    if manifest['module_progress_count']==0:
        offset=elapsed-120
        result.update(timing_baseline_candidate_seconds=offset,baseline_range_plausible=10<=offset<=40,timing_inferred_outcome=None,outcome_limits='Known-field0 calibration candidate only; require matching software-reset record and physical non-interference before reuse.')
        return result
    if baseline is None or not 10<=baseline<=40:raise ValueError('Verified debug baseline required')
    tolerance=manifest['timing_match_tolerance_seconds']
    if not 0<tolerance<1:raise ValueError('Ambiguous tolerance')
    code,residual=min(((n,abs(elapsed-baseline-120-2*n)) for n in range(128)),key=lambda item:item[1])
    text=manifest['result_codes'][str(code)];accepted=residual<=tolerance and not text.startswith('reserved')
    result.update(timing_nearest_code_hex='0x'+format(code,'02x'),timing_residual_seconds=residual,timing_inferred_outcome=text if accepted else None,timing_module_progress_field=code if accepted else None,outcome_limits='Indirect checkpoint at90s. Pending means no completed marker, not proof of an infinite hang. Inserted module does not prove binding. Require matching software reset and non-interference.')
    return result
