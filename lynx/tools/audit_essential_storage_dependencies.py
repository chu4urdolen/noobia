"""Audit dependencies of the exact 41-module essential storage candidate."""
from pathlib import Path
P=Path(__file__).resolve().parent
source=(P/'audit_progress_dependencies.py').read_text()
source=source.replace('busybox-module-progress-debug-28-v1','busybox-module-progress-debug-41-v1').replace('module-progress-dependencies.json','essential-storage-dependencies.json')
exec(compile(source,str(P/'audit_progress_dependencies.py'),'exec'))
