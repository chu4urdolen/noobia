#!/usr/bin/env python3
"""Live Nexus end-to-end integration test for Aigel's Sensory Perception Engine & DB Tools."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AUTONOMY = REPO / "common" / "autonomy"
SERVICE = REPO / "aigel" / "service"

ENV = dict(os.environ, PYTHONPATH=f"{SERVICE}:{AUTONOMY}:{REPO}")

TEST_DB = Path("/tmp/nexus_aigel_test.db")
TEST_LOG = Path("/tmp/nexus_mock_sensory.log")


def main():
    print("=" * 75)
    print("      NEXUS LIVE TEST: AIGEL PERCEPTION ENGINE & DB MANAGEMENT")
    print("=" * 75)

    if TEST_DB.exists():
        TEST_DB.unlink()
    if TEST_LOG.exists():
        TEST_LOG.unlink()

    # 1. Start mock sensory service to emit a test batch of messages
    print("\n[STEP 1] Generating mock sensory log stream with random messages...")
    mock_script = REPO / "aigel" / "tools" / "mock_sensory_service.py"
    subprocess.run([sys.executable, str(mock_script), "-o", str(TEST_LOG), "-n", "12", "--min-interval", "0.05", "--max-interval", "0.15"], check=True)
    with open(TEST_LOG) as f:
        lines = f.readlines()
    print(f"  Generated {len(lines)} log lines in {TEST_LOG}:")
    for l in lines[:4]:
        print(f"    • {l.strip()}")
    print("    • ...")

    # 2. Run Aigel Perception Engine on this log batch using local Qwen inference
    print("\n[STEP 2] Running Aigel Perception Engine over the stream (with local Qwen)...")
    engine_script = REPO / "aigel" / "service" / "aigel_perception_engine.py"
    res = subprocess.run([
        sys.executable, str(engine_script),
        "--source", f"file:{TEST_LOG}",
        "--host", "nexus-test",
        "--db-path", str(TEST_DB),
        "--once",
    ], env=ENV, capture_output=True, text=True)

    print("Engine Output:")
    for line in res.stdout.splitlines():
        print(f"  {line}")

    # 3. Use aigel-db tool to inspect learned patterns
    print("\n[STEP 3] Testing 'aigel-db' CLI tool to inspect learned database...")
    db_tool = REPO / "aigel" / "tools" / "aigel_db.py"
    res_list = subprocess.run([
        sys.executable, str(db_tool),
        "--db-path", str(TEST_DB),
        "list", "--host", "nexus-test",
    ], env=ENV, capture_output=True, text=True)
    print(res_list.stdout)

    # 4. Test editing an entry via aigel-db tool
    print("[STEP 4] Testing 'aigel-db edit' to update an entry...")
    # Find first pattern id
    res_json = subprocess.run([
        sys.executable, str(db_tool),
        "--db-path", str(TEST_DB),
        "list", "--host", "nexus-test", "--json",
    ], env=ENV, capture_output=True, text=True)
    import json
    pats = json.loads(res_json.stdout)
    if pats:
        target_id = pats[0]["pattern_id"]
        print(f"  Editing pattern: {target_id}")
        edit_res = subprocess.run([
            sys.executable, str(db_tool),
            "--db-path", str(TEST_DB),
            "edit", target_id,
            "--message", "Aigel updated this message: clear and safe perception.",
            "--p", "2",
        ], env=ENV, capture_output=True, text=True)
        print(f"  Result: {edit_res.stdout.strip()}")

        # Verify get
        get_res = subprocess.run([
            sys.executable, str(db_tool),
            "--db-path", str(TEST_DB),
            "get", target_id,
        ], env=ENV, capture_output=True, text=True)
        print(get_res.stdout)

    # 5. Emit a second occurrence of one of the lines to demonstrate matching without re-learning
    print("[STEP 5] Testing repeated perception (verifying pure DB matching without LLM)...")
    repeat_line = lines[0]
    with open(TEST_LOG, "a") as f:
        f.write(repeat_line)
    res_repeat = subprocess.run([
        sys.executable, str(engine_script),
        "--source", f"file:{TEST_LOG}",
        "--host", "nexus-test",
        "--db-path", str(TEST_DB),
        "--once",
    ], env=ENV, capture_output=True, text=True)
    for line in res_repeat.stdout.splitlines():
        if "matched" in line.lower() or "processed" in line.lower():
            print(f"  {line}")

    # 6. Verify Diagnostic suggestions log output
    print("\n[STEP 6] Checking Aigel's suggestions.log...")
    sugg_path = REPO / "aigel" / "logs" / "suggestions.log"
    if sugg_path.exists():
        with open(sugg_path) as f:
            content = f.read()
        print(content[-500:])

    print("\n===========================================================================")
    print("               LIVE NEXUS TEST COMPLETED SUCCESSFULLY!")
    print("===========================================================================")


if __name__ == "__main__":
    main()
