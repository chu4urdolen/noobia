"""Preserve earlier fixes; relocate ODM configuration beneath the stock alias target."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
s=(P/'prepare_wifi_v9_image.py').read_text().replace('busybox-wifi-ssh-twostage-v9','busybox-wifi-ssh-twostage-v10')
anchor='    payload=gzip.compress(decompress(pack(extra)),mtime=0)'
assert s.count(anchor)==1
fix="""    # Stock /odm/etc is a symlink to /vendor/odm/etc; retain that link.
    relocated={}
    for name,item in list(extra.items()):
        if name=='odm/etc' or name.startswith('odm/etc/'):
            target='vendor/odm/etc'+name[len('odm/etc'):]
            require(target not in extra,'ODM destination collision')
            relocated[target]=item
            del extra[name]
    require(relocated,'No ODM configuration to relocate')
    put(extra,'vendor/odm',b'',0o40755)
    extra.update(relocated)
"""
s=s.replace(anchor,fix+anchor)
s=s.replace('firmware_directory_preserved=True,mirrored_firmware=mirrored,','firmware_directory_preserved=True,mirrored_firmware=mirrored,odm_configuration_relocated=list(relocated),')
out=P/'prepare_wifi_v10_image.py';assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
