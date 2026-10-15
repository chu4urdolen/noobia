"""Decode the bounded errno field using monotonic USB/reboot timestamps."""


def decode_errno_timing(operation,usb,manifest):
    if not usb.get('observation_complete') or not usb.get('fastboot_return_observed'):
        raise ValueError('Complete USB return receipt required')
    event=usb['events'][-1]
    if not any(item['identifier']=='0e8d:201c' for item in event['usb']):
        raise ValueError('Final USB event is not Fastboot')
    finish=operation['started_monotonic']+operation['elapsed_seconds']
    elapsed=event['monotonic_seconds']-finish
    wall_elapsed=(event['wall_time_ns']-operation['finished_ns'])/1e9
    targets=manifest['target_delays_seconds'];tolerance=manifest['timing_match_tolerance_seconds']
    if set(targets)!=set(str(n) for n in range(128)) or any(targets[str(n)]!=60+2*n for n in range(128)):
        raise ValueError('Unexpected timing field geometry')
    if not 0<tolerance<1:
        raise ValueError('Tolerance must reject ambiguous midpoint returns')
    nearest,residual=min(((n,abs(elapsed-manifest['baseline_reference_seconds']-targets[str(n)])) for n in range(128)),key=lambda item:item[1])
    accepted=residual<=tolerance
    value=0 if nearest==0 else (-nearest if nearest<=120 else (-517 if nearest==121 else None))
    return {'return_seconds_after_reboot':elapsed,'wall_return_seconds_after_reboot':wall_elapsed,
            'wall_monotonic_disagreement_seconds':wall_elapsed-elapsed,'timing_clock':'monotonic',
            'timing_nearest_code_hex':'0x'+format(nearest,'02x'),'timing_residual_seconds':residual,
            'timing_inferred_outcome':manifest['result_codes'][str(nearest)] if accepted else None,
            'timing_decoded_platform_return':value if accepted else None,
            'outcome_limits':'Indirect finer timing. Require matching reset evidence and physical non-interference; reject ambiguous or variable-latency returns. Zero is wrapper success only.'}
