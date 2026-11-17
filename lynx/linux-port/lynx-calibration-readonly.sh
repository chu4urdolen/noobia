# Read existing factory calibration without journal replay or writable storage.
lynx_read_factory_calibration() {
    candidates=''
    for entry in /sys/class/block/*/uevent; do
        [ -f "$entry" ] || continue
        part=''; name=''
        while IFS='=' read -r key value; do
            case "$key" in PARTNAME) part=$value ;; DEVNAME) name=$value ;; esac
        done < "$entry"
        [ "$part" = nvdata ] || continue
        case "$name" in ''|*[!a-zA-Z0-9._-]*) return 1 ;; esac
        candidates="$candidates $name"
    done
    set -- $candidates
    [ "$#" = 1 ] || { log 'CALIBRATION_PARTITION_NOT_UNIQUE_OR_ABSENT'; return 1; }
    device=/dev/$1
    [ -b "$device" ] || return 1
    $BB blockdev --setro "$device" || return 1
    readonly=$($BB blockdev --getro "$device") || return 1
    [ "$readonly" = 1 ] || return 1
    $BB mkdir -p /mnt/lynx-nvdata /run/lynx/calibration || return 1
    $BB mount -t ext4 -o ro,noload "$device" /mnt/lynx-nvdata || return 1
    # Check actual mount flags before reading a calibration file.
    mounted_ro=0
    while IFS=' ' read -r dev point type options rest; do
        [ "$point" = /mnt/lynx-nvdata ] || continue
        [ "$type" = ext4 ] || return 1
        case ",$options," in *,ro,*) mounted_ro=1 ;; esac
    done < /proc/mounts
    [ "$mounted_ro" = 1 ] || return 1
    source=/mnt/lynx-nvdata/APCFG/APRDEB/WIFI
    [ -f "$source" ] && [ ! -L "$source" ] || return 1
    size=$($BB stat -c %s "$source") || return 1
    case "$size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$size" -ge 128 ] && [ "$size" -le 32768 ] || return 1
    $BB cp "$source" /run/lynx/calibration/WIFI || return 1
    $BB chmod 600 /run/lynx/calibration/WIFI || return 1
    $BB umount /mnt/lynx-nvdata || return 1
    log "FACTORY_CALIBRATION_COPIED_TO_RAM bytes=$size storage_readonly=1"
}
