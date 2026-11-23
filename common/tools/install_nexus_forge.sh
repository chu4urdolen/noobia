#!/usr/bin/env bash
# ==============================================================================
# install_nexus_forge.sh - Portable installer for Nexus Forge
#
# Sets up system prerequisites (GTK3, VTE 2.91, PyGObject, tmux, chafa),
# generates ~/.config/nexus-forge/config.json, provisions local Dushich configs,
# and puts Noobia's commands ($NOOBIA/common/bin, including nexus-forge) on PATH.
# Nothing is copied out of the repository: Noobia's tools never go in /usr/bin,
# /usr/local/bin, or ~/.local/bin.
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
    --dry-run        Show what would be installed and configured without making changes
    --config-only    Only create or reset the default ~/.config/nexus-forge/config.json
    --uninstall      Remove the NOOBIA/PATH setup this installer added
    -h, --help       Show this help message

Nexus Forge pairs 4 terminal quadrants with live AI avatar sidebars:
  - Top-Left:     Aria / Primary Agent (OpenAI Codex)
  - Bottom-Left:  Dushich Solo / Local LLM (Ollama qwen3.8:27b)
  - Top-Right:    Banshee / Research Agent (Google Antigravity)
  - Bottom-Right: Gwyn / Coding Agent (Claude Code)
EOF
}

CHECK_ONLY=0
CONFIG_ONLY=0
DRY_RUN=0
UNINSTALL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)
            CHECK_ONLY=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
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
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] Would remove $ENV_FILE and the Noobia block from $PROFILE"
        exit 0
    fi
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
    echo "Checking core prerequisites..."

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
        echo "  [!] chafa (optional, recommended for terminal graphics: apt install chafa)"
    fi

    echo "Checking optional tools and runtimes..."

    # uv
    if command -v uv >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/uv" ]]; then
        local uv_bin="$(command -v uv || echo "$HOME/.local/bin/uv")"
        echo "  [✓] uv: $($uv_bin --version 2>&1 | head -n1)"
    else
        echo "  [!] uv (optional, recommended for building local runtimes; install via https://docs.astral.sh/uv/)"
    fi

    # Ollama & local models
    if curl -fsS --max-time 1 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        echo "  [✓] Ollama: local service active on 127.0.0.1:11434"
        local tags
        tags="$(curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
        if echo "$tags" | grep -q "qwen3.8:27b"; then
            echo "  [✓] Ollama model: qwen3.8:27b (Dushich's mind)"
        else
            echo "  [!] Ollama model qwen3.8:27b not loaded (run: ollama pull qwen3.8:27b)"
        fi
        if echo "$tags" | grep -q "qwen3-embedding"; then
            echo "  [✓] Ollama model: qwen3-embedding (forge-db semantic search)"
        elif [[ -x "$NOOBIA_DIR/common/runtime/forge-venv/bin/python" ]]; then
            echo "  [✓] FastEmbed CPU fallback: available in common/runtime/forge-venv"
        else
            echo "  [!] Meaning search: run 'ollama pull qwen3-embedding:0.6b' or 'common/runtime/install.sh forge'"
        fi
    else
        echo "  [!] Ollama not running (optional: needed for local Dushich assistant; https://ollama.com)"
    fi

    # Cloud Agent CLIs
    if command -v codex >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/codex" ]] || [[ -x "/usr/local/bin/codex" ]]; then
        echo "  [✓] OpenAI Codex CLI detected"
    else
        echo "  [!] OpenAI Codex CLI not found (optional for Aria quadrant: npm install -g @openai/codex)"
    fi

    if command -v agy >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/agy" ]]; then
        echo "  [✓] Google Antigravity CLI ('agy') detected"
    else
        echo "  [!] Google Antigravity CLI ('agy') not found (optional for Banshee quadrant)"
    fi

    if command -v claude >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/claude" ]]; then
        echo "  [✓] Anthropic Claude Code detected"
    else
        echo "  [!] Anthropic Claude Code not found (optional for Gwyn quadrant)"
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo
        echo "Missing required system packages: ${missing[*]}"
        if [[ "$CHECK_ONLY" -eq 1 ]]; then
            return 1
        fi
        if [[ "$DRY_RUN" -eq 1 ]]; then
            echo "  [dry-run] Would install missing packages via apt: ${missing[*]}"
            return 0
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
# Provision Solo Dushich configuration (create-if-missing, relative links)
# ------------------------------------------------------------------------------
setup_solo_dushich() {
    local solo_dir="$NOOBIA_DIR/dushich/solo/private/codex"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        if [[ ! -d "$solo_dir" ]]; then
            echo "  [dry-run] Would create $solo_dir and default configuration"
        fi
        return 0
    fi

    mkdir -p "$solo_dir"
    chmod 700 "$NOOBIA_DIR/dushich/solo/private" "$solo_dir"

    # Relative symlink to solo AGENTS.md (safe across any checkout path)
    if [[ ! -e "$solo_dir/AGENTS.md" ]]; then
        ln -sf "../../AGENTS.md" "$solo_dir/AGENTS.md"
        echo "  [✓] Linked $solo_dir/AGENTS.md -> ../../AGENTS.md"
    fi

    # Model definition catalog
    if [[ ! -e "$solo_dir/model.json" ]]; then
        cat > "$solo_dir/model.json" <<'EOF'
{
  "models": [
    {
      "base_instructions": "",
      "context_window": 131072,
      "default_reasoning_level": null,
      "default_verbosity": "low",
      "display_name": "qwen3.8:27b",
      "experimental_supported_tools": [],
      "input_modalities": [
        "text"
      ],
      "priority": 0,
      "shell_type": "default",
      "slug": "qwen3.8:27b",
      "support_verbosity": true,
      "supported_in_api": true,
      "supported_reasoning_levels": [],
      "supports_parallel_tool_calls": false,
      "supports_reasoning_summaries": false,
      "truncation_policy": {
        "limit": 10000,
        "mode": "bytes"
      },
      "visibility": "list"
    }
  ]
}
EOF
        echo "  [✓] Created default $solo_dir/model.json"
    fi

    # Solo Dushich config
    if [[ ! -e "$solo_dir/config.toml" ]]; then
        cat > "$solo_dir/config.toml" <<EOF
model = "qwen3.8:27b"
model_provider = "ollama"
oss_provider = "ollama"
model_catalog_json = "$solo_dir/model.json"
model_context_window = 131072
model_auto_compact_token_limit = 114688
model_reasoning_effort = "medium"
model_reasoning_summary = "none"
approval_policy = "never"
sandbox_mode = "danger-full-access"
web_search = "disabled"

[projects."$NOOBIA_DIR"]
trust_level = "trusted"

[tui]
screen_reader_detection_done = true
EOF
        chmod 600 "$solo_dir/config.toml"
        echo "  [✓] Created default $solo_dir/config.toml"
    fi
}

# ------------------------------------------------------------------------------
# Create / Verify Configuration
# ------------------------------------------------------------------------------
setup_config() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        if [[ ! -f "$CONFIG_FILE" ]]; then
            echo "  [dry-run] Would create default configuration at $CONFIG_FILE"
        else
            echo "  [dry-run] Configuration exists at $CONFIG_FILE"
        fi
        return 0
    fi

    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "Creating default configuration at $CONFIG_FILE..."
        cat > "$CONFIG_FILE" <<EOF
{
  "title": "Nexus Forge",
  "pics_dir": "$NOOBIA_DIR/pics",
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
        "s=\$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-aria-.*:0\$/{print \$1; exit}'); if [ -n \"\$s\" ]; then if tmux list-panes -t \"\$s\":0 -F '#{pane_current_command}' 2>/dev/null | grep -qx 'codex'; then exec tmux attach-session -t \"\$s\"; else tmux kill-session -t \"\$s\" 2>/dev/null || true; fi; fi; NOOBIA_ARIA_NO_GUI=1 exec \${NOOBIA:-$NOOBIA_DIR}/aria/codex-with-dushich"
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
        "s=\$(tmux -Ldushich-clean list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-dushich-solo-.*:0\$/{print \$1; exit}'); if [ -n \"\$s\" ]; then exec tmux -Ldushich-clean attach-session -t \"\$s\"; fi; exec \${NOOBIA:-$NOOBIA_DIR}/dushich/solo/launch --no-gui"
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
        "s=\$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-banshee-.*:0\$/{print \$1; exit}'); if [ -n \"\$s\" ]; then exec tmux attach-session -t \"\$s\"; fi; exec \${NOOBIA:-$NOOBIA_DIR}/banshee/launch"
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
        "s=\$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-gwyn-.*:0\$/{print \$1; exit}'); if [ -n \"\$s\" ]; then exec tmux attach-session -t \"\$s\"; fi; exec \${NOOBIA:-$NOOBIA_DIR}/gwyn-app-nub/launch"
      ]
    }
  }
}
EOF
        echo "  [✓] Config written: $CONFIG_FILE"
    else
        echo "  [✓] Existing configuration found at $CONFIG_FILE"
    fi
}

# ------------------------------------------------------------------------------
# Put Noobia's commands on PATH
# ------------------------------------------------------------------------------
setup_environment() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] Would put $BIN_DIR on PATH (NOOBIA=$NOOBIA_DIR) in $ENV_FILE and $PROFILE"
        return 0
    fi

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

    setup_solo_dushich
    setup_config

    if [[ "$CONFIG_ONLY" -eq 1 ]]; then
        echo "Config setup complete."
        exit 0
    fi

    if [[ "$CHECK_ONLY" -eq 1 ]]; then
        echo "All core checks passed."
        exit 0
    fi

    setup_environment

    echo
    echo "================================================================================"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "Dry run complete! No changes were made."
    else
        echo "Installation complete!"
        echo "Run Nexus Forge with:"
        echo "    nexus-forge"
        echo "Or zoom into any quadrant with Ctrl+Shift+Z, F11, or double-clicking the header!"
    fi
    echo "================================================================================"
}

main
