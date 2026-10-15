"""Pin the complementary context image and boot_a-only restoration path."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='b5d0ac87efdf209e849f43c842e0e06e3e4690d0dd3fc0a02f19b4ade7562d98'
NEW='21d10aad02191ce95e6c7b8fec70528b57504d56d2f3b8c03654e5826427b832'
def save(name,text):
    path=T/name;assert not path.exists();path.write_text(text)
def main():
    validator=(T/'validate_timeout_log_image.py').read_text().replace(OLD,NEW).replace('busybox-timeout-log-v2','busybox-timeout-site-v1').replace('timeout-log-control-','timeout-site-control-').replace('emulated-timeout-log-image-','emulated-timeout-site-image-').replace('emulated-native-timeout-logs-','emulated-native-timeout-sites-').replace('timeout-log-timing-','timeout-site-timing-').replace('lynx_timeout_log_timing.py','lynx_timeout_site_timing.py').replace('docs/timeout-log-image-validation.json','docs/timeout-site-image-validation.json')
    validator=validator.replace("(P/'lynx-classify-timeout-logs.awk')","(P/'lynx-classify-timeout-sites.awk')")
    save('validate_timeout_site_image.py',validator)
    trial=(T/'lynx_boot_a_timeout_log_trial.py').read_text().replace(OLD,NEW).replace('busybox-timeout-log-v2','busybox-timeout-site-v1').replace('validate_timeout_log_image.py','validate_timeout_site_image.py').replace('boot-a-timeout-log-trial-','boot-a-timeout-site-trial-').replace('lynx_timeout_log_timing','lynx_timeout_site_timing').replace('decode_timeout_log_timing','decode_timeout_site_timing')
    save('lynx_boot_a_timeout_site_trial.py',trial)
    print('Pinned complementary context trial prepared; no phone contacted.')
if __name__=='__main__':main()
