#!/usr/bin/env python3
import os, time, glob, csv, datetime

SCAN_DIR   = "/mnt/nvme/argus/scans"
ALERT_LOG  = "/mnt/nvme/argus/alerts.log"
RETENTION_DAYS = 7

def log_alert(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(ALERT_LOG, "a") as f:
        f.write(line + "\n")

def parse_scan(csv_file):
    seen_ssids = {}
    with open(csv_file, newline='', encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 14:  # skip malformed
                continue
            bssid = row[0].strip()
            ssid  = row[13].strip() or "<hidden>"
            if ssid not in seen_ssids:
                seen_ssids[ssid] = set()
            seen_ssids[ssid].add(bssid)

    for ssid, bssids in seen_ssids.items():
        if ssid == "<hidden>":
            log_alert(f"Hidden SSID spotted in {os.path.basename(csv_file)}")
        if len(bssids) > 3:  # arbitrary threshold for duplicates
            log_alert(f"Possible Evil Twin: SSID '{ssid}' with {len(bssids)} BSSIDs")

def cleanup_old_logs():
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    for f in glob.glob(os.path.join(SCAN_DIR, "*.csv")):
        if os.path.getmtime(f) < cutoff:
            os.remove(f)
            log_alert(f"Deleted old log {os.path.basename(f)}")

def main():
    while True:
        csv_files = sorted(glob.glob(os.path.join(SCAN_DIR, "*.csv")))
        for f in csv_files:
            done_marker = f + ".done"
            if not os.path.exists(done_marker):
                parse_scan(f)
                open(done_marker, "w").close()
        cleanup_old_logs()
        time.sleep(60)  # check every minute

if __name__ == "__main__":
    main()
