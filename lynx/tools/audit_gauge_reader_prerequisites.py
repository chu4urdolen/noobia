"""Inventory exact stock headers/symbol CRCs for a future gauge reader.

Offline only. No module build/loading, handset access, or gauge commands.
"""
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import elf64

KERNEL_COMMIT = '81ec42ad5e803be0cba619f9f7bb298db7d33d7b'
MODULE_COMMIT = 'b7485501b2c4e0abae154e44c3861bd0fc6d605a'
SYMBOLS = {'module_layout', 'i2c_register_driver', 'i2c_del_driver',
           'i2c_smbus_read_word_data', 'of_property_read_variable_u32_array',
           'of_property_read_bool', 'of_device_is_compatible'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    out = PORT / 'artifacts' / ('gauge-reader-prerequisites-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    saved = []
    requests = [('modules-mt6983', MODULE_COMMIT, 'vendor/oplus/kernel/charger/gauge_ic/oplus_bq27541.h'),
                ('kernel-mt6983', KERNEL_COMMIT, 'kernel/gen_kheaders.sh'),
                ('kernel-mt6983', KERNEL_COMMIT, 'drivers/i2c/i2c-core-smbus.c')]
    for repo, commit, name in requests:
        data = subprocess.run(['git', '-C', str(PORT / 'sources' / repo), 'show', commit + ':' + name],
                              capture_output=True, check=True, timeout=45).stdout
        target = out / name.replace('/', '__')
        target.write_bytes(data)
        saved.append({'repository': repo, 'commit': commit, 'path': name, 'sha256': sha(data)})
    config = (PORT / 'artifacts/stock-cph2493-August-eu-ota/kernel-config.txt').read_text()
    options = {}
    for key in ['CONFIG_I2C_CHARDEV', 'CONFIG_IKHEADERS', 'CONFIG_MODVERSIONS',
                'CONFIG_LTO_CLANG_FULL', 'CONFIG_CFI_CLANG', 'CONFIG_CFI_PERMISSIVE',
                'CONFIG_MODULE_SIG', 'CONFIG_CC_VERSION_TEXT']:
        match = re.search(r'(?m)^' + key + r'=(.*)$', config)
        options[key] = match.group(1) if match else 'not set' if '# ' + key + ' is not set' in config else 'absent'
    roots = [PORT / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules',
             PORT / 'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules']
    imports = {name: {} for name in SYMBOLS}
    modules = 0
    for folder in roots:
        for path in sorted(folder.glob('*.ko')):
            modules += 1
            versions = elf64(path.read_bytes())['sections'].get('__versions', b'')
            for crc, symbol in struct.iter_unpack('<Q56s', versions):
                name = symbol.split(b'\0')[0].decode()
                if name in imports:
                    imports[name].setdefault(f'{crc:08x}', []).append(path.name)
    conflicts = [name for name, values in imports.items() if len(values) > 1]
    result = {'phone_contacted': False, 'modules_built_or_loaded': False,
              'stock_configuration': options, 'saved_primary_sources': saved,
              'stock_modules_examined': modules, 'observed_import_crcs': imports,
              'conflicting_crcs': conflicts,
              'reader_ready_for_hardware': False,
              'remaining_requirements': [
                  'Match exact headers and Android clang 12.0.5/r416183b LTO/CFI toolchain.',
                  'Build using normal Kbuild and genuine stock symbol-version evidence; do not force load or disable CFI.',
                  'Check exact gauge model and temperature units, including OPLUS-compatible alternatives.',
                  'Review an explicitly read-only command whitelist and exact DT/client binding.',
                  'Test successful/error paths offline before a short supervised RAM-only hardware trial.'
              ],
              'limits': 'Imported CRCs prove only observed symbol-version requirements, not complete Module.symvers, struct compatibility, CFI compatibility, or module safety.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'modules': modules,
                      'symbols_with_observed_crcs': sorted(n for n, v in imports.items() if v),
                      'conflicting_crcs': conflicts, 'hardware_ready': False}, indent=2))
    if conflicts:
        raise SystemExit('Conflicting stock symbol versions')


if __name__ == '__main__':
    main()
