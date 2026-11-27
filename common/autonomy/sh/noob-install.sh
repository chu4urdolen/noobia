#!/bin/sh
# noob-install.sh: BusyBox and POSIX-safe install helper for Noob devices (NA-85).
# Gwyn & Banshee, 2026-11-27.
#
# Provides safe file installation, checksum verification, .pre-* backups,
# atomic updates, and conditional service restarts for OpenRC and systemd.
set -eu

noob_check_hash() {
    file="$1"
    expected="$2"
    if [ ! -f "$file" ]; then
        echo "ERROR: file $file does not exist" >&2
        return 1
    fi
    actual=$(sha256sum "$file" | cut -d" " -f1)
    if [ "$actual" != "$expected" ]; then
        echo "ERROR: sha256 mismatch for $file (got $actual, expected $expected)" >&2
        return 1
    fi
    return 0
}

noob_backup() {
    target="$1"
    suffix="$2"
    backup="${target}.${suffix}"
    if [ -e "$backup" ]; then
        echo "ERROR: backup destination $backup already exists; aborting" >&2
        return 1
    fi
    if [ -e "$target" ]; then
        cp -p "$target" "$backup"
        echo "Backed up $target -> $backup"
    fi
    return 0
}

noob_install_file() {
    src="$1"
    dst="$2"
    mode="${3:-0755}"
    owner="${4:-root:root}"
    backup_suffix="${5:-}"

    if [ ! -f "$src" ]; then
        echo "ERROR: source file $src not found" >&2
        return 1
    fi

    if [ -n "$backup_suffix" ] && [ -e "$dst" ]; then
        noob_backup "$dst" "$backup_suffix"
    fi

    # Install using install or cp + chmod/chown (safe across busybox implementations)
    tmp_dst="${dst}.tmp.$$"
    cp -p "$src" "$tmp_dst"
    chmod "$mode" "$tmp_dst"
    if [ "$(id -u)" = "0" ]; then
        chown "$owner" "$tmp_dst" 2>/dev/null || true
    fi
    mv -f "$tmp_dst" "$dst"
    echo "Installed $src -> $dst ($mode $owner)"
}

noob_rollback() {
    dst="$1"
    suffix="$2"
    backup="${dst}.${suffix}"
    if [ ! -e "$backup" ]; then
        echo "ERROR: backup $backup does not exist" >&2
        return 1
    fi
    mv -f "$backup" "$dst"
    echo "Rolled back $dst from $backup"
}

noob_restart_if_running() {
    svc="$1"
    if command -v rc-service >/dev/null 2>&1; then
        if rc-service "$svc" status 2>/dev/null | grep -q started; then
            echo "Restarting OpenRC service $svc..."
            rc-service "$svc" restart
        else
            echo "Service $svc is not running; leaving stopped"
        fi
    elif command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            echo "Restarting systemd service $svc..."
            systemctl restart "$svc"
        else
            echo "Service $svc is not running; leaving stopped"
        fi
    else
        echo "No supported init system detected (neither rc-service nor systemctl)"
    fi
}
