# Compact, checksummed stage records. RAM first; pmsg only when available.
# Source after /run and manual /dev setup. Never opens a block device.
lynx_diag_init() {
    diag_owner=${1:-main}
    case "$diag_owner" in main|supervisor|bootstrap|wifi) ;; *) return 1 ;; esac
    diag_token=$($BB cat /etc/lynx/session-token) || return 1
    case "$diag_token" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#diag_token}" = 32 ] || return 1
    [ -d /run/lynx ] || return 1
    diag_sequence=0
    diag_file=/run/lynx/stages-$diag_owner.hex
    : > "$diag_file" || return 1
    $BB chmod 600 "$diag_file" || return 1
}
lynx_diag_emit() {
    # Caller supplies numeric stage and numeric status; no arbitrary log text.
    [ "$#" = 2 ] || return 1
    case "$1:$2" in *[!0-9:]*|:*|*:) return 1 ;; esac
    case "$1" in 0|[1-9]|[1-9][0-9]*) ;; *) return 1 ;; esac
    case "$2" in 0|[1-9]|[1-9][0-9]*) ;; *) return 1 ;; esac
    [ "${#1}" -le 5 ] && [ "${#2}" -le 5 ] || return 1
    [ "$1" -le 65535 ] && [ "$2" -le 65535 ] || return 1
    [ "$diag_sequence" -lt 4096 ] || return 1
    IFS=' ' read -r diag_uptime diag_unused < /proc/uptime || return 1
    diag_seconds=${diag_uptime%%.*}
    case "$diag_seconds" in ''|*[!0-9]*) return 1 ;; esac
    # One producer per file. Supervisor and worker must use separate journals
    # if they run concurrently; mixing sequences would conceal lost records.
    diag_record=$(printf 'LXDG1 %s %08x %08x %04x %04x' "$diag_token" "$diag_sequence" "$diag_seconds" "$1" "$2") || return 1
    diag_digest=$(printf '%s' "$diag_record" | $BB sha256sum) || return 1
    diag_digest=${diag_digest%% *}
    printf '%s %s\n' "$diag_record" "$diag_digest" >> "$diag_file" || return 1
    # These copies do not prove persistence; backend/retrieval need hardware verification.
    [ ! -c /dev/kmsg ] || printf '<6>%s %s\n' "$diag_record" "$diag_digest" > /dev/kmsg
    [ ! -c /dev/pmsg0 ] || printf '%s %s\n' "$diag_record" "$diag_digest" > /dev/pmsg0
    diag_sequence=$((diag_sequence+1))
    return 0
}
