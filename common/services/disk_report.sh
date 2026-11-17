#!/usr/bin/env bash
set -euo pipefail

# Report each mount point with its usage
# Skip pseudo filesystems (tmpfs, devtmpfs, etc.)

while read -r mount; do
  if [[ "$mount" =~ ^/(proc|sys|devtmpfs|tmpfs|dev|run|sysfs|cgroup|pstore|debugfs|tracefs|securityfs|configfs|hugetlbfs|fusectl|mqueue|rpc_pipefs|rpc_pipefs|overlay|overlayfs|fuse.sshfs|fuseblk) ]]; then
    continue
  fi
  df -h "$mount" | awk 'NR==2{printf "%s: %s used (%s free) on %s\n", $1, $5, $4, $6}'
done < <(mount | awk '{print $3}')
