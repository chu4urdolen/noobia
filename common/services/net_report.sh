#!/usr/bin/env bash
set -euo pipefail

# Network interface statistics
printf "\nNetwork interface statistics:\n"
ip -s link show

# Active connections (last 10 lines)
printf "\nActive connections (last 10 lines):\n"
ss -t -a | tail -n 10

# Latency to public DNS
printf "\nLatency to public DNS (8.8.8.8):\n"
ping -c 4 8.8.8.8
