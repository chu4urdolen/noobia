#!/usr/bin/env bash
set -euo pipefail

# Disk usage report
# Show usage per filesystem
# Skip loop devices

df -h | awk 'NR>1{print $NF ": " $5 " used (" $4 " free)"}'
