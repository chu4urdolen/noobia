#!/bin/bash
OUTDIR="/mnt/nvme/argus/scans"
mkdir -p "$OUTDIR"

check_eth0_ip() {
    ip addr show dev eth0 | grep -q "inet "
}

while true; do
    if check_eth0_ip; then
        TS=$(date +"%Y%m%d-%H%M%S")
        echo "[$(date)] eth0 up -> scanning with wlan0" >> "$OUTDIR/scan_history.log"

        # flip wlan0 into monitor and scan
        sudo ip link set wlan0 down
        sudo iw dev wlan0 set type monitor
        sudo ip link set wlan0 up

        timeout 60 sudo airodump-ng --write-interval 30 --output-format csv -w "$OUTDIR/scan_$TS" wlan0
        echo "[$(date)] Completed scan cycle -> scan_$TS.csv" >> "$OUTDIR/scan_history.log"

        # put wlan0 back to managed after scan
        ip link set wlan0 down
        iw dev wlan0 set type managed
        ip link set wlan0 up
    else
        echo "[$(date)] eth0 has no IP -> wlan0 reserved for internet, skipping scan" >> "$OUTDIR/scan_history.log"
        sleep 60
    fi

    sleep 5
done
