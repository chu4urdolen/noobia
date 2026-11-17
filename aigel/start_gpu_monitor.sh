#!/usr/bin/env bash

set -euo pipefail

# Create log directory
mkdir -p /var/log/noobia_gpu


# Run the monitor
exec /usr/bin/python3 -u /noobia/aigel/noobia_gpu_restart_monitor/monitor.py
