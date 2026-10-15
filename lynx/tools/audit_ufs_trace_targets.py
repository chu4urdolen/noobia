"""Inspect exact stock module symbols; retain the published tracing reference."""
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'linux-port'
sys.path.insert(0, str(P))
from image_formats import elf64, module_metadata, require


def main():
    module = P / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/ufs-mediatek-mod.ko'
    raw = module.read_bytes()
    sections = elf64(raw)['sections']
    symbols, names = sections['.symtab'], sections['.strtab']
    require(len(symbols) % 24 == 0, 'Unexpected ELF symbol table')
    targets = []
    for offset in range(0, len(symbols), 24):
        name_offset, info, _, section, value, size = struct.unpack_from('<IBBHQQ', symbols, offset)
        end = names.find(b'\0', name_offset)
        require(end >= 0, 'Unterminated symbol')
        name = names[name_offset:end].decode()
        if name == 'ufs_mtk_probe':
            require(section != 0 and info & 15 == 2, 'Probe target is not a defined function')
            targets.append({'name': name, 'symbol_index': offset // 24, 'section_index': section, 'section_offset': value, 'bytes': size})
    require(len(targets) == 1, 'Expected one exact storage probe function')
    metadata = module_metadata(raw)['values']
    require(metadata.get('name') == ['ufs_mediatek_mod'], 'Unexpected module name')
    repo = P / 'sources/kernel-mt6983'
    source = subprocess.run(['git', '-C', str(repo), 'show', 'HEAD:kernel/trace/trace_kprobe.c'], check=True, capture_output=True).stdout
    revision = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    require(b'trace_kprobe_module_callback' in source and b'MODULE_STATE_COMING' in source, 'Deferred module reference missing')
    reference = P / 'docs/wifi-source-reference/trace_kprobe.c'
    require(not reference.exists() or reference.read_bytes() == source, 'Preserve earlier reference')
    reference.write_bytes(source)
    result = {'passed': True, 'phone_contacted': False, 'module_sha256': hashlib.sha256(raw).hexdigest(),
              'module_name': metadata['name'][0], 'vermagic': metadata['vermagic'], 'targets': targets,
              'ftrace_sections': {name: len(payload) for name, payload in sections.items() if 'mcount' in name or 'ftrace' in name},
              'standard_event': 'r32:lynx_ufs/mtk_probe_return ufs_mediatek_mod:ufs_mtk_probe ret=$retval:s32',
              'published_source_revision': revision, 'published_trace_source_sha256': hashlib.sha256(source).hexdigest(),
              'limits': 'Exact stock ELF target verified. Published Git revision is not the exact stock build. Physical probe tracing untested.'}
    path = P / 'docs/ufs-trace-target-audit.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
