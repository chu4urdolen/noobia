#!/usr/bin/env python3
"""Lynx Autonomous Sight Service.

Continuously captures frames from Lynx's camera, lifts and runs object
detection, and emits sense lines to Lynx's syslog (noobia-sense) so the
autonomy harness, ranker, and Aigel perceive her world continuously.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LYNX_TOOLS = REPO / "lynx" / "tools"
CAMERA_DIR = HERE

PID_FILE = REPO / "lynx" / "logs" / "lynx_sight_service.pid"
LOG_FILE = REPO / "lynx" / "logs" / "lynx_sight_service.log"


class SightService:
    def __init__(
        self,
        interval_s: float = 5.0,
        max_iterations: int = 0,
        detect_url: str = "http://127.0.0.1:5050/detect",
        mode: str = "alternate",
    ):
        self.interval_s = max(1.0, float(interval_s))
        self.max_iterations = int(max_iterations)
        self.detect_url = detect_url
        self.mode = mode
        self.running = True

    def stop(self, signum=None, frame=None):
        self.running = False
        print(f"\n[sight] Stopping sight service (signal {signum})...", flush=True)

    def log(self, msg: str):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def get_lynx_status(self) -> dict | None:
        try:
            cmd = ["python3", str(LYNX_TOOLS / "lynx_remote.py"), "run", "/usr/local/bin/lynx-status"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout:
                out = res.stdout
                if "{" in out:
                    raw = out[out.find("{"):out.rfind("}") + 1]
                    return json.loads(raw)
        except Exception as e:
            self.log(f"warning: status read failed: {e}")
        return None

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        self.log(f"Starting autonomous sight service (interval: {self.interval_s}s, max: {self.max_iterations or 'inf'})")

        iteration = 0
        try:
            while self.running:
                iteration += 1
                if self.max_iterations and iteration > self.max_iterations:
                    self.log(f"Reached max iterations ({self.max_iterations}). Exiting.")
                    break

                # 1. Health & boot check
                status = self.get_lynx_status()
                if not status:
                    self.log("warning: Lynx unreachable, waiting 5s...")
                    time.sleep(5)
                    continue

                boot_id = status.get("boot_id")
                battery = status.get("battery", {})
                battery_pct = battery.get("capacity_percent", 0)
                current_mA = battery.get("current_mA_signed", 0)
                temp_c = status.get("thermal", {}).get("max_mC", 0) / 1000.0

                if battery_pct < 20:
                    self.log(f"SAFETY: battery low ({battery_pct}%), pausing sight service.")
                    time.sleep(30)
                    continue

                if temp_c > 41.0:
                    self.log(f"SAFETY: temperature warm ({temp_c:.1f}°C), cooling down 25s.")
                    time.sleep(25)
                    continue

                # 2. Select camera and capture frame
                if self.mode == "alternate":
                    active_lens = "macro" if iteration % 2 == 1 else "wide"
                elif self.mode == "wide":
                    active_lens = "wide"
                else:
                    active_lens = "macro"

                script_name = "trial_camera_camsv_frame.py" if active_lens == "macro" else "trial_camera_wide_frame.py"
                t0 = time.time()
                capture_cmd = [
                    sys.executable,
                    str(LYNX_TOOLS / script_name),
                    "--attended",
                    "--boot-id",
                    boot_id,
                ]
                cap_res = subprocess.run(capture_cmd, capture_output=True, text=True, timeout=45)
                dt_cap = time.time() - t0

                if cap_res.returncode != 0:
                    err_msg = cap_res.stderr.strip() or cap_res.stdout.strip()
                    self.log(f"frame #{iteration} [{active_lens}] capture failed ({dt_cap:.1f}s): {err_msg[:120]}")
                    time.sleep(5)
                    continue

                # 3. Detect & Emit
                c1_cmd = [
                    sys.executable,
                    str(CAMERA_DIR / "lynx_camera_c1_wrapper.py"),
                    "--latest-trial",
                    "--boot-id",
                    boot_id,
                    "--lens",
                    active_lens,
                    "--emit",
                    "--detect-url",
                    self.detect_url,
                ]
                det_res = subprocess.run(c1_cmd, capture_output=True, text=True, timeout=20)
                if det_res.returncode == 0:
                    try:
                        c1_out = json.loads(det_res.stdout)
                        objs = c1_out.get("objects", [])
                        labels = [f"{o.get('label')}:{o.get('confidence'):.2f}" for o in objs]
                        self.log(
                            f"frame #{iteration} [{active_lens}] ok ({dt_cap:.1f}s) | "
                            f"detected: {labels or 'none'} | "
                            f"batt: {battery_pct}% | temp: {temp_c:.1f}°C"
                        )
                    except Exception:
                        self.log(f"frame #{iteration} [{active_lens}] ok ({dt_cap:.1f}s) | parsed stdout: {det_res.stdout.strip()[:80]}")
                else:
                    self.log(f"frame #{iteration} [{active_lens}] detect error: {det_res.stderr.strip()[:100]}")

                # 4. Settle interval
                effective_interval = max(self.interval_s, 25.0) if current_mA < 0 else self.interval_s
                for _ in range(int(effective_interval * 2)):
                    if not self.running:
                        break
                    time.sleep(0.5)

        finally:
            if PID_FILE.exists():
                try:
                    PID_FILE.unlink()
                except OSError:
                    pass
            self.log("Autonomous sight service stopped.")


def stop_existing():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to sight service PID {pid}")
            time.sleep(1)
            return True
        except (ValueError, OSError) as e:
            print(f"Could not kill PID: {e}")
            try:
                PID_FILE.unlink()
            except OSError:
                pass
    return False


def main():
    ap = argparse.ArgumentParser(description="Autonomous sight daemon for Lynx")
    ap.add_argument("--interval", type=float, default=5.0, help="Settle interval in seconds between captures")
    ap.add_argument("--max-iterations", type=int, default=0, help="Max iterations (0 = run forever)")
    ap.add_argument("--mode", choices=["alternate", "macro", "wide"], default="alternate", help="Camera mode: alternate, macro, or wide")
    ap.add_argument("--stop", action="store_true", help="Stop running sight service")
    args = ap.parse_args()

    if args.stop:
        stop_existing()
        return 0

    stop_existing()
    svc = SightService(interval_s=args.interval, max_iterations=args.max_iterations, mode=args.mode)
    svc.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
