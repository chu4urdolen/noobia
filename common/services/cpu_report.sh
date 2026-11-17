#!/usr/bin/env bash
set -euo pipefail

LOGDIR="/var/log/noobia/aigel"
mkdir -p "$LOGDIR"
LOGFILE="$LOGDIR/cpu_report.log"
LAST_MIN_FILE="$LOGDIR/cpu_report.last_minute"
LAST_HOUR_FILE="$LOGDIR/cpu_report.last_hour"

# Snapshot two times 1s apart to compute per‑core usage
snap1=$(grep '^cpu[0-9]' /proc/stat)
sleep 1
snap2=$(grep '^cpu[0-9]' /proc/stat)

# Compute usage per core
usage_lines=""
while read -r line1; do
  cpu_name=${line1%% *}
  line2=$(grep "^$cpu_name " <<< "$snap2")
  read -ra f1 <<< "$line1"
  read -ra f2 <<< "$line2"
  idle1=${f1[4]}
  idle2=${f2[4]}
  total1=$(( ${f1[1]} + ${f1[2]} + ${f1[3]} + ${f1[4]} + ${f1[5]} + ${f1[6]} + ${f1[7]} + ${f1[8]} ))
  total2=$(( ${f2[1]} + ${f2[2]} + ${f2[3]} + ${f2[4]} + ${f2[5]} + ${f2[6]} + ${f2[7]} + ${f2[8]} ))
  diff_total=$((total2 - total1))
  diff_idle=$((idle2 - idle1))
  if ((diff_total==0)); then
    usage=0
  else
    usage=$(( (1000*(diff_total - diff_idle)/diff_total +5)/10 ))
  fi
  usage_lines+="$cpu_name: $usage%\n"
done <<< "$snap1"

# Top snapshot for context
context=$(top -bn1 | head -n 6 | tr -d '\r')

# Full output string
output="$usage_lines\nTop snapshot (summary):\n$context"

# Determine logging frequency
boot=$(date -d "$(uptime -s)" +%s)
now=$(date +%s)
elapsed=$((now - boot))

should_log=true
if (( elapsed > 300 )); then
  minute=$(date +%M)
  last_min=$(cat "$LAST_MIN_FILE" 2>/dev/null || echo "")
  if [[ "$last_min" == "$minute" ]]; then
    should_log=false
  else
    echo "$minute" > "$LAST_MIN_FILE"
  fi
fi
if (( elapsed > 3600 )); then
  hour=$(date +%H)
  last_hour=$(cat "$LAST_HOUR_FILE" 2>/dev/null || echo "")
  if [[ "$last_hour" == "$hour" ]]; then
    should_log=false
  else
    echo "$hour" > "$LAST_HOUR_FILE"
  fi
fi

if $should_log; then
  timestamp=$(date +%s)
  echo "$timestamp $output" >> "$LOGFILE"
  logger -t cpu_report "$(date +%Y-%m-%dT%H:%M:%S%z) $output"
fi

# Print to stdout
printf "%s\n" "$output"
