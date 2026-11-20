#!/usr/bin/env python3
import time, subprocess, os, signal

MAX_TEMP = 65.0   # °C, raise/lower as you wish
CHECK_EVERY = 5   # seconds between checks
COOLDOWN_CMD = ["sudo", "cpupower", "frequency-set", "-g", "powersave"]
NORMAL_CMD   = ["sudo", "cpupower", "frequency-set", "-g", "performance"]
LOGFILE = "/mnt/nvme/argus/temp_guard.log"

def get_temp():
    out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
    return float(out.split("=")[1].split("'")[0])

def set_mode(cmd):
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        log("Error running", cmd, e)

def main():
    cooled = False
    while True:
        t = get_temp()
        if t > MAX_TEMP and not cooled:
            log(f"{t}°C too hot, throttling…")
            set_mode(COOLDOWN_CMD)
            cooled = True
        elif t <= MAX_TEMP - 5 and cooled:
            log(f"{t}°C safe, restoring performance…")
            set_mode(NORMAL_CMD)
            cooled = False
        time.sleep(CHECK_EVERY)

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOGFILE, "a") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
