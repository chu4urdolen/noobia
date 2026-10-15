"""Extract the August kernel's embedded configuration without executing it."""
import gzip
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
directory = BASE / 'artifacts/stock-cph2493-August-eu-ota'
kernel = gzip.decompress((directory / 'unpacked-boot/kernel').read_bytes())
offset = 0
configs = []
while True:
    start = kernel.find(b'IKCFG_ST', offset)
    if start < 0:
        break
    offset = start + 8
    end = kernel.find(b'IKCFG_ED', offset)
    if end < 0 or kernel[offset:offset + 2] != b'\x1f\x8b':
        continue
    config = gzip.decompress(kernel[offset:end])
    configs.append(config)
if len(configs) != 1:
    raise ValueError('Expected exactly one embedded kernel configuration')
data = configs[0]
(directory / 'kernel-config.txt').write_bytes(data)
values = {}
for line in data.decode().splitlines():
    if line.startswith('CONFIG_') and '=' in line:
        key, value = line.split('=', 1)
        values[key] = value
    elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
        values[line[2:-11]] = 'n'
names = ('CONFIG_DEVTMPFS', 'CONFIG_DEVTMPFS_MOUNT', 'CONFIG_BLK_DEV_INITRD',
         'CONFIG_RD_GZIP', 'CONFIG_PROC_FS', 'CONFIG_SYSFS', 'CONFIG_TMPFS',
         'CONFIG_BINFMT_ELF', 'CONFIG_MODVERSIONS', 'CONFIG_MODULE_SIG',
         'CONFIG_USB_CONFIGFS', 'CONFIG_USB_CONFIGFS_ACM', 'CONFIG_USB_CONFIGFS_ECM',
         'CONFIG_USB_MTU3', 'CONFIG_SERIAL_AMBA_PL011', 'CONFIG_SERIAL_AMBA_PL011_CONSOLE')
report = {'kernel_config_sha256': hashlib.sha256(data).hexdigest(),
          'selected_options': {name: values.get(name, 'absent') for name in names},
          'phone_contacted': False}
(directory / 'kernel-config-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
