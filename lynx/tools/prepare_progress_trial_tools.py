"""Pin calibration and camera-only boot_a trials to tested images."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='8856714bafaabc6869ab58fa46194babcd055afd22b88ba93d3d0bf02901afaa'
SHAS={0:'465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2',28:'9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4'}
def main():
    for count,digest in SHAS.items():
        path=T/('lynx_boot_a_progress_debug_'+str(count)+'_trial.py');assert not path.exists()
        source=(T/'lynx_boot_a_platform_errno_trial.py').read_text().replace('busybox-platform-errno-v1','busybox-module-progress-debug-'+str(count)+'-v1').replace(OLD,digest)
        source=source.replace('from lynx_errno_timing import decode_errno_timing','from lynx_progress_timing import decode_progress_timing')
        source=source.replace("str(ROOT / 'tools/validate_platform_errno_image.py')]", "str(ROOT / 'tools/validate_progress_debug_image.py'), '--count', '"+str(count)+"']")
        source=source.replace('boot-a-platform-errno-trial-','boot-a-progress-debug-'+str(count)+'-trial-').replace('up to 380 seconds','up to 420 seconds').replace('deadline=time.monotonic()+380','deadline=time.monotonic()+420')
        source=source.replace("report.update(decode_errno_timing(report['operations'][-1],usb,manifest))", "report.update(decode_progress_timing(report['operations'][-1],usb,manifest,calibrated_baseline))")
        marker='    checks = []';assert source.count(marker)==1
        calibration="    calibrated_baseline=None\n"
        if count:
            calibration+='''    if args.flash_linux:
        calibration=json.loads((PROJECT/'docs/progress-debug-calibration.json').read_text())
        if not calibration.get('passed') or calibration.get('calibration_image_sha256')!='465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2':
            raise ValueError('Verified debug timing calibration required; no phone contacted')
        calibrated_baseline=calibration['baseline_seconds']
'''
        source=source.replace(marker,calibration+marker,1)
        source=source.replace("'diagnostic_goal': 'coarse storage result via one timed standard reboot'", "'diagnostic_goal': 'debug timing calibration'" if not count else "'diagnostic_goal': 'one additional camera clock module with per-module checkpoints'")
        source=source.replace("'module_prefix_count': 33","'module_prefix_count': "+str(count))
        compile(source,str(path),'exec');path.write_text(source)
    print('Pinned trial tools ready; no phone contacted.')
if __name__=='__main__':main()
