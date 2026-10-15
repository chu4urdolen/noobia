"""Generate fixed readiness/trial tools for the read-only matching profile."""
from pathlib import Path

T=Path(__file__).resolve().parent
OLD='571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0'
NEW='13f82774e2bc6f20e03917c9cf97f8fae100186f91a3477badf1c66c3a36f8c6'


def main():
    pairs=[('test_binding_profile_control.py','test_match_profile_control.py'),
           ('test_binding_profile_image_vm.py','test_match_profile_image_vm.py'),
           ('validate_binding_profile_image.py','validate_match_profile_image.py'),
           ('lynx_boot_a_binding_profile_trial.py','lynx_boot_a_match_profile_trial.py')]
    for original,name in pairs:
        source=(T/original).read_text().replace(OLD,NEW)
        source=source.replace('busybox-binding-profile-v1','busybox-match-profile-v1').replace('binding-profile-control-','match-profile-control-')
        source=source.replace('emulated-binding-profile-image-','emulated-match-profile-image-').replace('emulated-native-binding-profile-','emulated-native-match-profile-')
        source=source.replace('binding-profile-image-validation.json','match-profile-image-validation.json').replace('boot-a-binding-profile-trial-','boot-a-match-profile-trial-')
        source=source.replace('lynx-binding-profile.sh','lynx-match-profile.sh').replace('lynx_binding_profile','lynx_match_profile').replace('validate_binding_profile_image.py','validate_match_profile_image.py')
        path=T/name;assert not path.exists(),'Preserve prior tools';path.write_text(source)
    print('Match profile host tools ready; no phone contacted.')


if __name__=='__main__':main()
