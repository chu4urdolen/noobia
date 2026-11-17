"""Record the reviewed diagnostic files and loader inputs for the local probe."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path('/noobia/lynx')
source = root / 'linux-port/sources/mtkclient-readback'
files = [source / 'mtk.py', root / 'tools/mtk_readonly.py']
files += list((source / 'mtkclient').rglob('*.py'))
files += [root / 'linux-port/artifacts/service-reference' / name for name in ('DA_BR.bin', 'auth_sv5.auth')]
files += [root / 'linux-port/artifacts/service-reference/da2-upstream-patch-OFFLINE-ONLY.bin']
files += [root / 'linux-port/docs' / name for name in ('download-agent-audit.json', 'ram-readback-audit.json', 'ram-payload-preparation.json')]
report = {'source_commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
          'files': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
          'notes': 'Local pin for the reviewed checkout; not an independent publisher signature.'}
(root / 'tools/mtk-readonly-source-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print('Pinned', len(files), 'diagnostic inputs at', report['source_commit'])
