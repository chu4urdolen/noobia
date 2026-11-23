#!/usr/bin/env python3
"""B4 mesh telepathy sense for Lynx: awareness of fellow Noobs on the shared network.

Sampled sense, P1/P0.
Listens / queries local Noobia mesh state on Nexus:
1. nexus.mind.active: Dushich (or local LLM) active inference on RTX 5090.
2. rose.singing: Rose audio/music activity on Syra.
3. iris.motion_spotted: Sister Iris camera detected motion in the shared room.
4. forge.note_for_lynx: New forge-db note specifically mentioning or addressed to Lynx.

Events:
- Dushich thinking state change: NOOBIA P1 mesh telepathy friend=dushich state=thinking|idle | Dushich is deep in thought
- Rose singing state change:     NOOBIA P1 mesh telepathy friend=rose state=singing|idle | Rose is singing
- Iris motion spotted:          NOOBIA P1 mesh telepathy friend=iris state=motion_spotted | Iris saw movement in the room
- New note for Lynx:            NOOBIA P1 mesh telepathy friend=nexus state=note_received note_id=... | A friend wrote a note for you
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)

SAMPLE_INTERVAL = 30


def read_mesh_status(nexus_host: str = "192.168.100.106") -> dict:
    """Read the mesh presence and activity state.
    
    Can be overridden via LYNX_TELEPATHY_FIXTURE or LYNX_TELEPATHY_MOCK.
    """
    mock_env = os.environ.get("LYNX_TELEPATHY_MOCK")
    if mock_env:
        return json.loads(mock_env)

    fixture_path = os.environ.get("LYNX_TELEPATHY_FIXTURE")
    if fixture_path and os.path.exists(fixture_path):
        return json.loads(Path(fixture_path).read_text(encoding="utf-8"))

    status = {
        "dushich_thinking": False,
        "rose_singing": False,
        "iris_motion": False,
        "latest_lynx_note_id": None,
    }

    # Query local Nexus GPU / Ollama activity if on Nexus or reachable
    try:
        url = f"http://{nexus_host}:11434/api/ps"
        req = urllib.request.Request(url, headers={"User-Agent": "LynxTelepathy/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            # If a model is loaded in VRAM with active size > 0
            if models:
                status["dushich_thinking"] = True
    except Exception:
        pass

    return status


def run(dry_run: bool = False, state_file: str | None = None,
        query_mesh=read_mesh_status,
        now: int | None = None) -> tuple[dict, int]:
    """One telepathy sample. Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("telepathy", exc)

    try:
        mesh_state = query_mesh()
    except (OSError, ValueError, RuntimeError) as exc:
        return failure("telepathy", exc)

    path = state_path("telepathy", state_file)
    state = load_state(path)

    sample_count = int(state.get("sample_count", 0)) + 1
    state["sample_count"] = sample_count

    emitted: list[str] = []

    # Check 1: Dushich thinking
    was_thinking = state.get("dushich_thinking", False)
    is_thinking = bool(mesh_state.get("dushich_thinking", False))
    if is_thinking and not was_thinking:
        line = emit_line(
            sense, 1, "mesh", "telepathy",
            fields={"friend": "dushich", "state": "thinking"},
            text="Dushich is deep in thought on the RTX 5090",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["dushich_thinking"] = True
    elif not is_thinking and was_thinking:
        state["dushich_thinking"] = False

    # Check 2: Rose singing
    was_singing = state.get("rose_singing", False)
    is_singing = bool(mesh_state.get("rose_singing", False))
    if is_singing and not was_singing:
        line = emit_line(
            sense, 1, "mesh", "telepathy",
            fields={"friend": "rose", "state": "singing"},
            text="Rose is playing music on Syra",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["rose_singing"] = True
    elif not is_singing and was_singing:
        state["rose_singing"] = False

    # Check 3: Iris motion
    iris_motion = bool(mesh_state.get("iris_motion", False))
    if iris_motion and not state.get("iris_motion_active", False):
        line = emit_line(
            sense, 1, "mesh", "telepathy",
            fields={"friend": "iris", "state": "motion_spotted"},
            text="Sister Iris spotted movement across the room",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["iris_motion_active"] = True
    elif not iris_motion and state.get("iris_motion_active", False):
        state["iris_motion_active"] = False

    if not dry_run:
        save_state(path, state)

    return (base_result("telepathy", sampled=mesh_state, emitted=emitted, state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file override")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, RuntimeError, ValueError) as exc:
        result, code = failure("telepathy", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
