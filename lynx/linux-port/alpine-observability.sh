#!/bin/sh
# New read-only proc/sysfs mounts inside the existing RAM chroot only.
# Run outside the chroot, with the expected current boot ID as argument two.
set -eu
mode=${1:---status}
expected_boot=${2:-}
root=/run/lynx/alpine-3.24.2
case "$mode" in --apply|--status) ;; *) echo 'Expected --apply or --status' >&2; exit 2;; esac
[ -n "$expected_boot" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
[ ! -L "$root" ] && [ -d "$root" ]
[ "$(cat "$root/etc/alpine-release")" = 3.24.2 ]
for path in "$root/proc" "$root/sys"; do
    [ ! -L "$path" ] && [ -d "$path" ]
done
outer_before=$(awk '$2 == "/proc" || $2 == "/sys" {print}' /proc/mounts)
for fs in proc sysfs; do
    target=$root/proc
    [ "$fs" != sysfs ] || target=$root/sys
    existing=$(awk -v p="$target" '$2 == p {print}' /proc/mounts)
    if [ -z "$existing" ]; then
        [ "$mode" = --apply ] || { echo "Missing mount $target" >&2; exit 1; }
        mount -t "$fs" -o ro,nosuid,nodev,noexec "$fs" "$target"
    fi
    awk -v p="$target" -v f="$fs" '
        $2 == p {
            count++
            if ($3 != f) exit 1
            n=split($4, options, ",")
            for (i=1; i<=n; i++) seen[options[i]]=1
            if (!seen["ro"] || !seen["nosuid"] || !seen["nodev"] || !seen["noexec"] || seen["rw"]) exit 1
            good=1
        }
        END {if (count != 1 || !good) exit 1}
    ' /proc/mounts
done
[ "$outer_before" = "$(awk '$2 == "/proc" || $2 == "/sys" {print}' /proc/mounts)" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
echo LYNX_ALPINE_OBSERVABILITY_READY
awk -v p="$root/proc" -v s="$root/sys" '$2 == p || $2 == s {print}' /proc/mounts
