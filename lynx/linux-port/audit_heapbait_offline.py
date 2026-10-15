"""Run only saved-loader address analysis; transport/exploit methods are excluded."""
import ast
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Optional, Tuple

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'sources/mtkclient-readback/mtkclient/Library/Exploit'
layout = json.loads((BASE / 'docs/download-agent-audit.json').read_text())
loader = (BASE / 'artifacts/service-reference/DA_BR.bin').read_bytes()
assert hashlib.sha256(loader).hexdigest() == layout['loader_sha256']
regions = layout['entries'][0]['regions']
da1 = loader[regions[1]['file_offset']:regions[1]['file_offset'] + regions[1]['bytes']]
da2 = loader[regions[2]['file_offset']:regions[2]['file_offset'] + regions[2]['bytes']]
namespace = {'Optional': Optional, 'Tuple': Tuple, 're': re}
hashes = {}
for filename, names in [('exptools/arch.py', ['ArchTools']),
                        ('exptools/arm_tools.py', ['ArmTools']),
                        ('exptools/aarch_tools.py', ['Aarch64Tools'])]:
    path = SOURCE / filename
    text = path.read_text()
    hashes[filename] = hashlib.sha256(text.encode()).hexdigest()
    tree = ast.parse(text)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    assert len(classes) == len(names)
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), 'exec'), namespace)
path = SOURCE / 'heapbait.py'
text = path.read_text()
hashes[path.name] = hashlib.sha256(text.encode()).hexdigest()
tree = ast.parse(text)
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'find_pattern']
selected += [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in ('HeapParams', 'HakuParams', 'PatchParams')]
heap = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Heapbait')
allow = {'parse_heap_init', 'find_dpc_address', 'extract_heap_params', 'find_uart_base',
         'find_free_func', 'find_register_xml_cmd_func', 'find_download_func', 'find_get_node',
         'find_mxml_load_string_func', 'find_dagent_command_loop2', 'extract_haku_params',
         'extract_patch_params', 'find_heap_struct', 'extract_params', 'is_vulnerable'}
heap.body = [node for node in heap.body if isinstance(node, ast.FunctionDef) and node.name in allow]
assert {node.name for node in heap.body} == allow
heap.bases = []
heap.keywords = []
heap.decorator_list = []
selected.append(heap)
exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
analysis = namespace['Heapbait']()
messages = []
for method in ('info', 'warning', 'error', 'debug'):
    setattr(analysis, method, lambda value: messages.append(str(value)))
analysis.da2 = da2
analysis.is_arm64 = (int.from_bytes(da2[4:8], 'little') & 0xf0) == 0xc0
analysis.mtk = SimpleNamespace(daloader=SimpleNamespace(daconfig=SimpleNamespace(
    da2=da2, da_loader=SimpleNamespace(region=[None, None, SimpleNamespace(m_start_addr=int(regions[2]['load_address'], 16))]))))
params = analysis.extract_params()
report = {'loader_sha256': layout['loader_sha256'], 'source_hashes': hashes,
          'loader_architecture_heuristic': 'aarch64' if analysis.is_arm64 else 'arm32',
          'upstream_patch_string_absent': analysis.is_vulnerable(),
          'parameters': [vars(value) if value else None for value in params],
          'messages': messages, 'all_parameter_sets_extracted': all(value is not None for value in params),
          'device_contacted': False, 'exploit_executed': False, 'payload_prepared': False,
          'limits': ['Missing patch string is not proof of exploitability.',
                     'Pattern-derived addresses require independent verification before a live RAM write.',
                     'No transport, payload creation, patching or exploit method was loaded into this analysis class.',
                     'The earlier Carbonara-style hash redirect was already rejected on Lynx; it was not repeated.']}
(BASE / 'docs/heapbait-offline-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
