#!/usr/bin/env bash
# Build Noobia's local runtimes in this folder from the pinned recipes beside
# this script. Safe to re-run: each part is rebuilt to the same pinned versions.
#
#   common/runtime/install.sh            # everything
#   common/runtime/install.sh codex      # Dushich's and Aigel's Codex CLI
#   common/runtime/install.sh forge      # forge-db meaning search (fastembed)
#   common/runtime/install.sh web        # Playwright and its Chromium
#
# Needs: node/npm, uv (https://docs.astral.sh/uv/), /usr/bin/python3, network.
set -euo pipefail
NOOBIA="${NOOBIA:-/noobia}"
R="$NOOBIA/common/runtime"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

step() { printf '== %s\n' "$*"; }

codex() {
    step "Codex CLI (pinned in codex/package-lock.json)"
    npm ci --prefix "$R/codex" --no-audit --no-fund --loglevel=error
    "$R/codex/node_modules/.bin/codex" --version
}

venv() {  # venv NAME: build NAME-venv from NAME-requirements.txt
    step "$1-venv (pinned in $1-requirements.txt)"
    "$UV" venv --quiet --allow-existing --python /usr/bin/python3 "$R/$1-venv"
    "$UV" pip install --quiet --python "$R/$1-venv/bin/python" -r "$R/$1-requirements.txt"
    "$R/$1-venv/bin/python" -c "import sys; print(sys.prefix)"
}

forge() {
    venv forge
    # The embedding model downloads into models/ on first meaning search.
    mkdir -p "$R/models"
}

web() {
    venv web
    step "Chromium for Playwright (into playwright/)"
    PLAYWRIGHT_BROWSERS_PATH="$R/playwright" "$R/web-venv/bin/python" -m playwright install chromium
}

case "${1:-all}" in
    codex) codex ;;
    forge) forge ;;
    web) web ;;
    all) codex; forge; web ;;
    *) echo "usage: install.sh [all|codex|forge|web]" >&2; exit 2 ;;
esac
step done
