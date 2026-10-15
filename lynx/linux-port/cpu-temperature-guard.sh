# Read-only prerequisite for the supervised CPU-frequency stage.
# 50C is a conservative test cutoff, not a validated battery safety threshold.
lynx_cpu_temperature_guard() {
    cpu_samples=0
    soc_samples=0
    cpu_highest=0
    for p in /sys/class/thermal/thermal_zone*; do
        [ -r "$p/type" ] || continue
        IFS= read -r kind < "$p/type" || continue
        case "$kind" in soc_max|cpu_*) ;; *) continue ;; esac
        IFS= read -r value < "$p/temp" || return 1
        case "$value" in ''|*[!0-9]*) return 1 ;; esac
        [ "$value" -gt 0 ] && [ "$value" -lt 50000 ] || return 1
        [ "$value" -le "$cpu_highest" ] || cpu_highest=$value
        case "$kind" in soc_max) soc_samples=$((soc_samples+1)) ;; cpu_*) cpu_samples=$((cpu_samples+1)) ;; esac
    done
    [ "$soc_samples" = 1 ] && [ "$cpu_samples" -ge 2 ] || return 1
    printf 'CPU_TEMPERATURE_GUARD_OK max_millidegrees=%s cpu_samples=%s\n' "$cpu_highest" "$cpu_samples"
}
