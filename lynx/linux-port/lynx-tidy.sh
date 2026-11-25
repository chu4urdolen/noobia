#!/bin/sh
# lynx-tidy: keep Lynx's growing logs and job files bounded (Gwyn, 2026-11-22).
#
# Trims IN PLACE (same inode), so services that keep a log open with
# O_APPEND go on writing without a restart. Never deletes a file a service
# needs, never touches /etc, never reboots or powers off.
#
#   lynx-tidy.sh --once     one pass, prints what it did
#   lynx-tidy.sh --watch    one pass every TIDY_INTERVAL seconds (default 3600)
#
# Disable: touch /etc/lynx/tidy.disable
set -u
BB=/bin/busybox
DISABLE=/etc/lynx/tidy.disable
INTERVAL=${TIDY_INTERVAL:-3600}
KEEP_BYTES=${TIDY_KEEP_BYTES:-1048576}        # keep the newest 1 MiB of each log
DONE_DAYS=${TIDY_DONE_DAYS:-2}                # finished agent jobs kept 2 days
JOBS=/var/lib/lynx-agent/jobs
LOGS="/var/log/lynx-agent.jsonl /var/log/lynx-agent-worker.log /var/log/lynx-senses.log
      /var/log/lynx-bluetoothd.log /var/lib/noobia/lynx_thought.txt
      /var/log/lynx-tidy.log /var/log/lynx-charge-guard.log /var/log/lynx-camera-sense.log
      /run/lynx/alpine-dropbear-2222.log /run/lynx/dropbear.log"
# The dropbear logs live in /run (RAM, 128 MiB) and grew ~0.8 MiB/h; dropbear holds
# them with O_APPEND (fdinfo flags 0402001, checked 2026-11-25), so in-place
# trimming is safe and SSH itself is never touched (Tom: leave 22 alone).

# Files whose writers open them anew for every append: replaced atomically
# (a reader such as the display never sees a half-written file). All other
# logs are held open by their service with O_APPEND and are trimmed in place.
ATOMIC="/var/lib/noobia/lynx_thought.txt /var/log/lynx-agent.jsonl"

trim() {
    f=$1
    [ -f "$f" ] && [ ! -L "$f" ] || return 0
    size=$("$BB" stat -c %s "$f") || return 0
    [ "$size" -gt $((KEEP_BYTES * 2)) ] || return 0
    tmp="$f.tidy.$$"
    # Keep whole lines: drop the first (partial) line of the kept tail.
    "$BB" tail -c "$KEEP_BYTES" "$f" | "$BB" sed '1d' > "$tmp" || { rm -f "$tmp"; return 0; }
    case " $ATOMIC " in
        *" $f "*)   # BusyBox has no chmod --reference: copy mode and owner by hand
            chmod "$("$BB" stat -c %a "$f")" "$tmp" 2>/dev/null
            chown "$("$BB" stat -c %u:%g "$f")" "$tmp" 2>/dev/null
            mv -f "$tmp" "$f" ;;
        *) cat "$tmp" > "$f" && rm -f "$tmp" ;;
    esac
    echo "LYNX_TIDY_TRIMMED $f from=$size to=$("$BB" stat -c %s "$f")"
}

once() {
    if [ -e "$DISABLE" ]; then
        echo "LYNX_TIDY_DISABLED $DISABLE"
        return 0
    fi
    for f in $LOGS; do trim "$f"; done
    if [ -d "$JOBS" ]; then
        before=$("$BB" find "$JOBS" -maxdepth 1 -type f -name '*.done' | wc -l)
        "$BB" find "$JOBS" -maxdepth 1 -type f -name '*.done' -mtime +"$DONE_DAYS" \
            -exec rm -f {} + 2>/dev/null
        after=$("$BB" find "$JOBS" -maxdepth 1 -type f -name '*.done' | wc -l)
        [ "$before" -gt "$after" ] && \
            echo "LYNX_TIDY_JOBS_REMOVED count=$((before - after)) older_than_days=$DONE_DAYS"
    fi
    echo "LYNX_TIDY_OK"
}

case "${1:-}" in
    --once) once ;;
    --watch)
        trap 'rm -f /var/log/*.tidy.* /var/lib/noobia/*.tidy.* /run/lynx/*.tidy.* 2>/dev/null; exit 0' TERM INT
        while :; do once; "$BB" sleep "$INTERVAL" & wait $!; done ;;
    *) echo 'Usage: lynx-tidy.sh --once|--watch' >&2; exit 2 ;;
esac
