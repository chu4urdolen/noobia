#!/usr/bin/env bash
# noobia_wifi_guard.sh — Nexus Network Defense & Noobia Wi-Fi Stability Watchdog
#
# Shared service entry script calling Banshee's network defense and Wi-Fi
# auto-heal tool (/noobia/banshee/tools/nexus_net_guard.py).
set -euo pipefail

exec /usr/bin/python3 /noobia/banshee/tools/nexus_net_guard.py --watch --interval 15 --heal-wifi
