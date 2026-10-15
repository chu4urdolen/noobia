"""Create an independent image builder for the read-only live match profile."""
from pathlib import Path

P=Path(__file__).resolve().parent.parent/'linux-port'


def main():
    source=(P/'prepare_binding_profile_image.py').read_text()
    source=source.replace('busybox-binding-profile-v1','busybox-match-profile-v1').replace('lynx-binding-profile.sh','lynx-match-profile.sh').replace('lynx_binding_profile','lynx_match_profile')
    start=source.index('    meanings={');end=source.index('    report.update(',start)
    source=source[:start]+'''    meanings={1:'live UFS device/driver/profile interface unavailable',
              2:'live UFS device already bound to expected ufshcd-mtk driver',
              3:'unexpected bound driver or driver override',
              4:'live UFS compatible list lacks the exact stock driver match',
              5:'platform automatic probing disabled',
              6:'live UFS device present in deferred-device list',
              7:'expected match, override and automatic probing; unbound and not listed deferred',
              8:'bootstrap failed before profile or exceeded worker deadline'}
'''+source[end:]
    target=P/'prepare_match_profile_image.py';assert not target.exists(),'Preserve previous builder';target.write_text(source)
    print(target)


if __name__=='__main__':main()
