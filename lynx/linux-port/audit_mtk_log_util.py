"""Offline source audit; never import MTKClient or contact USB."""
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'sources/mtk-log-util-review'


def main():
    manifest = json.loads((SOURCE / 'source-manifest.json').read_text())
    for record in manifest['sources']:
        for name, expected in record['files'].items():
            if hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Reviewed source changed: ' + name)
    source = (SOURCE / 'logutil.py').read_text()
    tree = ast.parse(source)
    # Extract only the reviewed pure command builder. Replace its execution
    # dependency with a string collector; no upstream imports or main run.
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'extract_with_mtkclient')
    commands = []
    namespace = {'MTK_CLIENT_CMD': 'python mtkclient/mtk.py', 'MTK_CLIENT_ARGS': '',
                 'run_command': lambda command: commands.append(command) or True}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<reviewed-command-builder>', 'exec'), namespace)
    builder = namespace['extract_with_mtkclient']
    builder('expdb', 'expdb.bin')
    builder('pstore', 'pstore.bin', '0x48090000', '0xe0000', True)
    builder('pstore', 'pstore.bin', '0x48090000', '0xe0000', False)
    expected = [['python', 'mtkclient/mtk.py', 'r', 'expdb', 'expdb.bin'],
                ['python', 'mtkclient/mtk.py', 'da', 'peek', '0x48090000', '0xe0000', '--filename', 'pstore.bin'],
                ['python', 'mtkclient/mtk.py', 'peek', '0x48090000', '0xe0000', '--filename', 'pstore.bin']]
    assert [command.split() for command in commands] == expected
    captured = BASE.parent / 'logs/pllk-1791606541890396711.clean.txt'
    matches = re.findall(r'pstore_addr:\s*(0x[0-9a-fA-F]+),\s*pstore_size:\s*(0x[0-9a-fA-F]+)', captured.read_text())
    assert matches and all((int(address, 16), int(size, 16)) == (0x48090000, 0xe0000) for address, size in matches)
    report = {'wrapper_commit': manifest['sources'][0]['commit'], 'mtkclient_commit': manifest['sources'][1]['commit'],
              'command_builder_checks_passed': True, 'generated_commands_not_executed': commands,
              'soc_recognized_by_dependency': 'MT6983, hardware code 0x907, XML DA mode',
              'device_pstore_address_from_saved_log': '0x48090000', 'device_pstore_size_from_saved_log': '0xe0000',
              'default_address_matches_saved_device_log': True,
              'phone_contacted': False, 'mtkclient_imported_or_executed': False,
              'subprocess_or_usb_used_by_audit': False, 'live_read_access_established': False,
              'live_wrapper_use_compatible_with_no_bypass_constraint': False,
              'findings': ['No independent acquisition transport: delegates to MTKClient preloader/DA operations, not Fastboot.',
                           'Default expdb/DA initialization has security-handling and loader-patching paths.',
                           'XML DA upload can attempt dummy or known-key SLA authentication after the session check, including stock mode.',
                           'Non-DA peek calls bypass_security when DAA is enabled; the flag is not a no-bypass mode.',
                           'Lynx previously required session authentication before guarded partition readback could proceed.',
                           'Pstore RAM availability after intervening boot/recovery transitions is unknown.',
                           'ASCII extraction ignores compression; stock config selects deflate pstore compression.',
                           'Wrapper deletes temporary raw dumps after ASCII extraction and does not provide an offline-input command.',
                           'Auto-detection failure falls back to defaults instead of refusing an unknown memory map.',
                           'Shell interpolation and missing bounded/serial-scoped transport make the wrapper unsuitable for direct guarded use.']}
    output = BASE / 'docs/mtk-log-util-audit.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('Offline source/hash and three command-builder checks passed.')
    print('MT6983 recognized; pstore address matches saved Lynx log.')
    print('No compatible unauthenticated live-read route established; wrapper not run.')
    print('Report:', output)


if __name__ == '__main__':
    main()
