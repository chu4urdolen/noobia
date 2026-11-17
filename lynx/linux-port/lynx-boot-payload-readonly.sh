# Supplementary Linux files live in unused boot_a space. Verify before extraction.
lynx_read_own_boot_payload() {
    candidates=''
    for entry in /sys/class/block/*/uevent; do
        [ -f "$entry" ] || continue
        part=''; name=''
        while IFS='=' read -r key value; do
            case "$key" in PARTNAME) part=$value ;; DEVNAME) name=$value ;; esac
        done < "$entry"
        [ "$part" = boot_a ] || continue
        case "$name" in ''|*[!a-zA-Z0-9._-]*) return 1 ;; esac
        candidates="$candidates $name"
    done
    set -- $candidates
    [ "$#" = 1 ] || { log 'BOOT_A_NOT_UNIQUE_OR_ABSENT'; return 1; }
    device=/dev/$1
    [ -b "$device" ] || return 1
    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ] || return 1
    $BB blockdev --setro "$device" || return 1
    [ "$($BB blockdev --getro "$device")" = 1 ] || return 1
    bytes=$($BB cat /etc/lynx/payload-bytes) || return 1
    expected=$($BB cat /etc/lynx/payload-sha256) || return 1
    case "$bytes" in ''|*[!0-9]*) return 1 ;; esac
    [ "$bytes" -gt 0 ] && [ "$bytes" -lt 40000000 ] || return 1
    [ "$($BB expr length "$expected")" = 64 ] || return 1
    case "$expected" in *[!0-9a-f]*) return 1 ;; esac
    blocks=$(((bytes+4095)/4096))
    $BB dd if="$device" of=/run/lynx/payload-blocks bs=4096 skip=6144 count="$blocks" || return 1
    $BB head -c "$bytes" /run/lynx/payload-blocks > /run/lynx/payload.cpio.gz || return 1
    actual=$($BB sha256sum /run/lynx/payload.cpio.gz) || return 1
    actual=${actual%% *}
    [ "$actual" = "$expected" ] || { log 'BOOT_A_PAYLOAD_HASH_MISMATCH'; return 1; }
    $BB gzip -dc /run/lynx/payload.cpio.gz > /run/lynx/payload.cpio || return 1
    (cd / && $BB cpio -idmu < /run/lynx/payload.cpio) || return 1
    log "BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED bytes=$bytes storage_readonly=1"
}
