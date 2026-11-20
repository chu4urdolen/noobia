#!/usr/bin/env bash
# ==============================================================================
# install_nexus_forge.sh - Portable installer for Nexus Forge
#
# Sets up system prerequisites (GTK3, VTE 2.91, PyGObject, tmux, chafa),
# generates ~/.config/nexus-forge/config.json, and puts Noobia's commands
# ($NOOBIA/common/bin, including nexus-forge) on PATH. Nothing is copied out of
# the repository: Noobia's tools never go in /usr/bin, /usr/local/bin, or
# ~/.local/bin.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOOBIA_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/nexus-forge"
CONFIG_FILE="$CONFIG_DIR/config.json"
BIN_DIR="$NOOBIA_DIR/common/bin"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/999-noobia.conf"
PROFILE="$HOME/.profile"
MARK_BEGIN="# >>> noobia >>>"
MARK_END="# <<< noobia <<<"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
    --check          Check system dependencies and display configuration status
    --config-only    Only create or reset the default ~/.config/nexus-forge/config.json
    --uninstall      Remove the NOOBIA/PATH setup this installer added
    -h, --help       Show this help message

Nexus Forge pairs 4 terminal quadrants with live AI avatar sidebars:
  - Top-Left:     Aria / Primary Agent
  - Bottom-Left:  Dushich Solo / Local LLM
  - Top-Right:    Banshee / Research Agent
  - Bottom-Right: Gwyn / Coding Agent
EOF
}

CHECK_ONLY=0
CONFIG_ONLY=0
UNINSTALL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)
            CHECK_ONLY=1
            shift
            ;;
        --config-only)
            CONFIG_ONLY=1
            shift
            ;;
        --uninstall)
            UNINSTALL=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ "$UNINSTALL" -eq 1 ]]; then
    echo "Removing Noobia's environment setup..."
    if [[ -f "$ENV_FILE" ]] && grep -q "$MARK_BEGIN" "$ENV_FILE"; then
        rm -- "$ENV_FILE"
        echo "  [✓] Removed $ENV_FILE"
    fi
    if [[ -f "$PROFILE" ]] && grep -q "$MARK_BEGIN" "$PROFILE"; then
        sed -i "/$MARK_BEGIN/,/$MARK_END/d" "$PROFILE"
        echo "  [✓] Removed the Noobia block from $PROFILE"
    fi
    echo "Done. Config directory remains at $CONFIG_DIR."
    exit 0
fi

# ------------------------------------------------------------------------------
# Check System Dependencies
# ------------------------------------------------------------------------------
check_dependencies() {
    local missing=()
    echo "Checking prerequisites..."

    # Python3
    if command -v python3 >/dev/null 2>&1; then
        echo "  [✓] python3: $(python3 --version 2>&1)"
    else
        missing+=("python3")
        echo "  [✗] python3 (missing)"
    fi

    # PyGObject / GTK3 / VTE
    if python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("Vte", "2.91"); gi.require_version("PangoCairo", "1.0"); from gi.repository import Gtk, Vte, PangoCairo' >/dev/null 2>&1; then
        echo "  [✓] GTK3, VTE 2.91, PangoCairo bindings"
    else
        missing+=("python3-gi" "python3-gi-cairo" "gir1.2-vte-2.91")
        echo "  [✗] python3-gi, python3-gi-cairo, gir1.2-vte-2.91 (missing)"
    fi

    # Tmux
    if command -v tmux >/dev/null 2>&1; then
        echo "  [✓] tmux: $(tmux -V)"
    else
        missing+=("tmux")
        echo "  [✗] tmux (missing)"
    fi

    # Chafa (optional avatar terminal renderer)
    if command -v chafa >/dev/null 2>&1; then
        echo "  [✓] chafa: $(chafa --version | head -n1)"
    else
        echo "  [!] chafa (optional, recommended for terminal graphics)"
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo
        echo "Missing required system packages: ${missing[*]}"
        if [[ "$CHECK_ONLY" -eq 1 ]]; then
            return 1
        fi

        echo "Attempting to install missing packages via apt (sudo required)..."
        if command -v apt-get >/dev/null 2>&1; then
            if [[ "$EUID" -eq 0 ]]; then
                apt-get update && apt-get install -y "${missing[@]}"
            elif command -v sudo >/dev/null 2>&1; then
                sudo apt-get update && sudo apt-get install -y "${missing[@]}"
            else
                echo "Error: sudo not available. Please install manually: apt-get install ${missing[*]}" >&2
                return 1
            fi
        else
            echo "Please install missing packages using your system package manager: ${missing[*]}" >&2
            return 1
        fi
    fi
    return 0
}

# ------------------------------------------------------------------------------
# Create / Verify Configuration
# ------------------------------------------------------------------------------
setup_config() {
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "Creating default configuration at $CONFIG_FILE..."
        cat > "$CONFIG_FILE" <<'EOF'
{
  "title": "Nexus Forge",
  "pics_dir": "/noobia/pics",
  "sidebar_width": 140,
  "interval": 0.4,
  "aria_socket": "default",
  "quadrants": {
    "top_left": {
      "title": "Aria + Dushich Helper",
      "agent": "Aria",
      "helper_agent": "",
      "badge": "",
      "command": [
        "/bin/bash",
        "-lc",
        "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-aria-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then if tmux list-panes -t \"$s\":0 -F '#{pane_current_command}' 2>/dev/null | grep -qx 'codex'; then exec tmux attach-session -t \"$s\"; else tmux kill-session -t \"$s\" 2>/dev/null || true; fi; fi; NOOBIA_ARIA_NO_GUI=1 exec ${NOOBIA:-/noobia}/aria/codex-with-dushich"
      ]
    },
    "bottom_left": {
      "title": "Dushich Solo",
      "agent": "Dushich",
      "helper_agent": "",
      "badge": "Local: 100%",
      "command": [
        "/bin/bash",
        "-lc",
        "s=$(tmux -Ldushich-clean list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-dushich-solo-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux -Ldushich-clean attach-session -t \"$s\"; fi; exec ${NOOBIA:-/noobia}/dushich/solo/launch --no-gui"
      ]
    },
    "top_right": {
      "title": "Banshee + Dushich Helper",
      "agent": "Banshee",
      "helper_agent": "",
      "badge": "",
      "command": [
        "/bin/bash",
        "-lc",
        "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-banshee-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; exec ${NOOBIA:-/noobia}/banshee/launch"
      ]
    },
    "bottom_right": {
      "title": "Gwyn + Dushich Helper",
      "agent": "Gwyn",
      "helper_agent": "",
      "badge": "",
      "command": [
        "/bin/bash",
        "-lc",
        "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-gwyn-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; exec ${NOOBIA:-/noobia}/gwyn-app-nub/launch"
      ]
    }
  }
}
EOF
        # The default points at this checkout's avatars, wherever it lives.
        sed -i "s#\"/noobia/pics\"#\"$NOOBIA_DIR/pics\"#" "$CONFIG_FILE"
        echo "  [✓] Config written: $CONFIG_FILE"
    else
        echo "  [✓] Existing configuration found at $CONFIG_FILE"
    fi
}

# ------------------------------------------------------------------------------
# Put Noobia's commands on PATH
# ------------------------------------------------------------------------------
setup_environment() {
    echo "Putting $BIN_DIR on PATH (NOOBIA=$NOOBIA_DIR)..."
    # The desktop session and systemd --user services read environment.d.
    if [[ -f "$ENV_FILE" ]] && ! grep -q "$MARK_BEGIN" "$ENV_FILE"; then
        echo "  [=] $ENV_FILE exists and was not written by this installer; left as is"
    else
        mkdir -p "$(dirname "$ENV_FILE")"
        printf '%s\n' "$MARK_BEGIN" "NOOBIA=$NOOBIA_DIR" "PATH=$BIN_DIR:\${PATH}" \
            "PLAYWRIGHT_BROWSERS_PATH=$NOOBIA_DIR/common/runtime/playwright" "$MARK_END" > "$ENV_FILE"
        echo "  [✓] $ENV_FILE"
    fi
    # Login shells read ~/.profile.
    if [[ -f "$PROFILE" ]] && grep -q "export NOOBIA=" "$PROFILE"; then
        echo "  [=] $PROFILE already sets NOOBIA"
    else
        printf '\n%s\n' "$MARK_BEGIN" >> "$PROFILE"
        printf '%s\n' "export NOOBIA=\"$NOOBIA_DIR\"" \
            'case ":$PATH:" in *":$NOOBIA/common/bin:"*) ;; *) PATH="$NOOBIA/common/bin:$PATH" ;; esac' \
            'export PLAYWRIGHT_BROWSERS_PATH="$NOOBIA/common/runtime/playwright"' "$MARK_END" >> "$PROFILE"
        echo "  [✓] $PROFILE"
    fi
    echo "  Log out and back in (or run: source $PROFILE) to pick it up."
}

# ------------------------------------------------------------------------------
# Main Flow
# ------------------------------------------------------------------------------
main() {
    echo "================================================================================"
    echo "Nexus Forge Installer"
    echo "================================================================================"

    if ! check_dependencies; then
        if [[ "$CHECK_ONLY" -eq 1 ]]; then
            exit 1
        fi
    fi

    setup_config

    if [[ "$CONFIG_ONLY" -eq 1 ]]; then
        echo "Config setup complete."
        exit 0
    fi

    if [[ "$CHECK_ONLY" -eq 1 ]]; then
        echo "All checks passed."
        exit 0
    fi

    setup_environment

    echo
    echo "================================================================================"
    echo "Installation complete!"
    echo "Run Nexus Forge with:"
    echo "    nexus-forge"
    echo "Or zoom into any quadrant with Ctrl+Shift+Z or double-clicking the header!"
    echo "================================================================================"
}

main
