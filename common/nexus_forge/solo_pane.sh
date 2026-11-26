#!/usr/bin/env bash
# Nexus Forge's Solo Dushich quadrant.
#
# Attach to an unattached Solo Dushich session, or start one with the Solo
# launcher. Never leave the pane dead: on failure show the error, retry with
# bounded backoff (5, 10, 20, 40, 60 s), and after five failures wait for
# Enter. When Solo ends normally, wait for Enter before starting a new one.
# Launcher failures are logged in dushich/solo/private/launch.log.
set -u
NOOBIA="${NOOBIA:-/noobia}"
LAUNCH="$NOOBIA/dushich/solo/launch"
MAX_TRIES="${NOOBIA_SOLO_PANE_TRIES:-5}"
SOCKET="${NOOBIA_SOLO_TMUX_SOCKET:-dushich-clean}"

free_session() {
    tmux -L"$SOCKET" list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null \
        | awk -F: '/^noobia-dushich-solo-.*:0$/{print $1; exit}'
}

fails=0
while true; do
    s=$(free_session)
    if [[ -n "$s" ]]; then
        tmux -L"$SOCKET" attach-session -t "$s"
        rc=$?
    else
        NOOBIA_DUSHICH_NO_GUI=1 "$LAUNCH" --no-gui
        rc=$?
    fi
    if (( rc == 0 )); then
        fails=0
        printf '\n\033[2mSolo Dushich ended. Press Enter to start or attach again.\033[0m\n'
        read -r _ || exit 0
        continue
    fi
    fails=$((fails + 1))
    if (( fails >= MAX_TRIES )); then
        printf '\n\033[33mSolo Dushich failed to start %d times (last exit %d).\033[0m\n' "$fails" "$rc"
        printf 'See %s. Press Enter to try again.\n' "$NOOBIA/dushich/solo/private/launch.log"
        read -r _ || exit "$rc"
        fails=0
        continue
    fi
    delay=$((5 << (fails - 1)))
    (( delay > 60 )) && delay=60
    printf '\n\033[33mSolo Dushich did not start (exit %d); retry %d/%d in %ds...\033[0m\n' \
        "$rc" "$fails" "$((MAX_TRIES - 1))" "$delay"
    sleep "$delay"
done
