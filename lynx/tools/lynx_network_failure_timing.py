"""Decode a completed bootstrap-only timed Fastboot return."""
def decode_progress_timing(operation,usb,manifest,baseline=None):
    if baseline is None or not 10<=baseline<=40:raise ValueError('Verified baseline required')
    if manifest['target_delays_seconds']!={str(n):480+5*n for n in range(25)} or manifest['timing_match_tolerance_seconds']!=2:raise ValueError('Timing grid changed')
    if not usb.get('observation_complete') or not usb.get('fastboot_return_observed'):raise ValueError('Completed return required')
    event=usb['events'][-1]
    if not any(x['identifier']=='0e8d:201c' for x in event['usb']):raise ValueError('Not Fastboot')
    elapsed=event['monotonic_seconds']-operation['started_monotonic']-operation['elapsed_seconds'];wall=(event['wall_time_ns']-operation['finished_ns'])/1e9
    code,error=min(((n,round(abs(elapsed-baseline-480-5*n),9)) for n in range(25)),key=lambda x:x[1])
    return dict(return_seconds_after_reboot=elapsed,wall_return_seconds_after_reboot=wall,wall_monotonic_disagreement_seconds=wall-elapsed,timing_nearest_code_hex='0x'+format(code,'02x'),timing_residual_seconds=error,timing_module_progress_field=code if error<=2 else None,timing_inferred_outcome=manifest['result_codes'][str(code)] if error<=2 else None,outcome_limits='Indirect bootstrap result, requiring software-reset evidence, physical non-interference and stable calibrated startup. Radio trial; interpret result only after normal reset evidence.')
