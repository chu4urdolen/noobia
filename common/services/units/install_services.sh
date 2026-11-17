#!/usr/bin/env bash
set -euo pipefail

unit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir=/etc/systemd/system

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --dry-run ) ]]; then
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
fi

mapfile -d '' -t units < <(
    find "$unit_dir" -maxdepth 1 -type f \
        \( -name '*.service' -o -name '*.timer' -o -name '*.socket' -o -name '*.target' \) \
        -print0 | sort -z
)

if (( ${#units[@]} == 0 )); then
    echo "No systemd unit files found in $unit_dir"
    exit 0
fi

if [[ "${1:-}" == --dry-run ]]; then
    for unit in "${units[@]}"; do
        echo "Would install $(basename -- "$unit") to $target_dir"
    done
    exit 0
fi

if (( EUID != 0 )); then
    echo "Run as root, for example: sudo -n $0" >&2
    exit 1
fi

for unit in "${units[@]}"; do
    install -o root -g root -m 0644 -- "$unit" "$target_dir/$(basename -- "$unit")"
    echo "Installed $(basename -- "$unit")"
done
systemctl daemon-reload
echo "Reloaded systemd; units were not enabled or started."
