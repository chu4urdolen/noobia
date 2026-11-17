#!/usr/bin/env bash
set -euo pipefail

# Memory usage report
free -h | awk 'NR==2{print "Memory: " $3 "/" $2 " used ($4 free)"}'
