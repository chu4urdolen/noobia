#!/usr/bin/env bash
# update_agents.sh — Robust updater for AGY, Codex, and Claude Code before Forge starts
set -u
NOOBIA="${NOOBIA:-/noobia}"

LOG_FILE="$HOME/.local/state/noobia/agent_updates.log"
mkdir -p "$(dirname "$LOG_FILE")" $HOME/.local/bin 2>/dev/null || true

log() {
    local msg="[$(date -u +'%Y-%m-%d %H:%M:%SZ')] [update-agents] $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log "=== Starting agent pre-flight update check ==="

# -----------------------------------------------------------------------------
# 1. AGY (Google Antigravity CLI)
# -----------------------------------------------------------------------------
log "Checking AGY..."
if command -v agy >/dev/null 2>&1; then
    current_agy="$(agy --version 2>/dev/null || echo 'unknown')"
    log "Current AGY: $current_agy"
    if out="$(timeout 30 agy update 2>&1)"; then
        log "AGY update output: $out"
    else
        log "warn: agy update exited with code $?: $out"
    fi
else
    log "warn: agy executable not found on PATH"
fi

# -----------------------------------------------------------------------------
# 2. Codex CLI (@openai/codex)
# -----------------------------------------------------------------------------
log "Checking Codex..."
if command -v npm >/dev/null 2>&1; then
    current_codex="$(codex --version 2>/dev/null | awk '{print $NF}' || echo "")"
    latest_codex="$(timeout 15 npm view @openai/codex version 2>/dev/null || echo "")"
    log "Codex installed: ${current_codex:-unknown}, latest on npm: ${latest_codex:-unknown}"

    if [[ -n "$latest_codex" && "$current_codex" != "$latest_codex" ]]; then
        log "Updating Codex from $current_codex to $latest_codex via npm..."
        if sudo -n npm install -g "@openai/codex@$latest_codex" >> "$LOG_FILE" 2>&1; then
            log "Codex successfully updated to $latest_codex"
        else
            log "warn: npm install -g @openai/codex failed"
        fi
    else
        log "Codex is up to date (${current_codex:-unknown})"
    fi

    # Ensure ~/.local/bin/codex points cleanly to the working global binary
    if [[ -x "/usr/local/bin/codex" ]]; then
        ln -sf /usr/local/bin/codex $HOME/.local/bin/codex
    fi

    # Pre-dismiss update notification in version.json so interactive prompt never blocks startup
    for vfile in $HOME/.codex/version.json $NOOBIA/dushich/solo/private/codex/version.json; do
        if [[ -f "$vfile" ]]; then
            python3 -c '
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    d = json.loads(p.read_text(encoding="utf-8"))
    lat = d.get("latest_version")
    if lat and d.get("dismissed_version") != lat:
        d["dismissed_version"] = lat
        p.write_text(json.dumps(d) + "\n", encoding="utf-8")
except Exception:
    pass
' "$vfile" 2>/dev/null || true
        fi
    done
else
    log "warn: npm not available for Codex update"
fi

# -----------------------------------------------------------------------------
# 3. Claude Code (@anthropic-ai/claude-code)
# -----------------------------------------------------------------------------
log "Checking Claude Code..."
# Ensure autoUpdatesChannel is set to "latest" (stable is slower and causes accidental downgrades)
python3 -c '
import json, pathlib
p = pathlib.Path.home() / ".claude/settings.json"
try:
    p.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    if d.get("autoUpdatesChannel") != "latest":
        d["autoUpdatesChannel"] = "latest"
        p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
except Exception:
    pass
' 2>/dev/null || true

if command -v claude >/dev/null 2>&1; then
    current_claude="$(claude --version 2>/dev/null || echo 'unknown')"
    log "Current Claude Code: $current_claude"
    if out="$(timeout 60 claude update 2>&1)"; then
        log "Claude update output: $out"
    else
        log "warn: claude update exited with code $?: $out"
    fi

    # Ensure symlink points to newest version if a newer binary was installed
    versions_dir="$HOME/.local/share/claude/versions"
    if [[ -d "$versions_dir" ]]; then
        newest_ver="$(ls -1v "$versions_dir" 2>/dev/null | tail -n 1 || true)"
        if [[ -n "$newest_ver" && -x "$versions_dir/$newest_ver" ]]; then
            ln -sf "$versions_dir/$newest_ver" $HOME/.local/bin/claude
        fi
    fi
else
    log "warn: claude executable not found on PATH"
fi

log "=== Agent update check finished ==="
exit 0
