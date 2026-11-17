#!/usr/bin/env bash
set -euo pipefail

# CPU usage report
top -bn1 | head -n 5
