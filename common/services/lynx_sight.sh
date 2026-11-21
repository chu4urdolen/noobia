#!/bin/bash
set -euo pipefail

# Ensure NOOBIA environment is set
export NOOBIA="${NOOBIA:-/noobia}"
export PATH="${NOOBIA}/common/bin:${PATH}"

exec /usr/bin/python3 /noobia/lynx/tools/camera/lynx_sight_service.py --interval 4.0
