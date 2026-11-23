#!/usr/bin/env bash
# ==============================================================================
# install.sh - Top-level installer wrapper for Noobia Nexus Forge
#
# Sets up system prerequisites (GTK3, VTE 2.91, PyGObject, tmux, chafa),
# generates ~/.config/nexus-forge/config.json, provisions local Dushich configs,
# and puts Noobia's commands ($NOOBIA/common/bin, including nexus-forge) on PATH.
#
# Usage:
#   ./install.sh           Install prerequisites, configure quadrants, and set PATH
#   ./install.sh --check   Check system dependencies and configuration status
#   ./install.sh --dry-run Show what would be installed/configured without changes
#   ./install.sh --help    Show all options
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/common/tools/install_nexus_forge.sh" "$@"
