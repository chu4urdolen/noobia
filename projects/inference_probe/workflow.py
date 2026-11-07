#!/usr/bin/env python3
"""Inference and coding stress test utility.

This module implements a lightweight deterministic scheduler for a task
directed acyclic graph (DAG).  The input is a JSON file that describes a set
of tasks, their durations, required resources, and dependencies.  The
scheduler respects a global worker limit and per‑resource capacities.  It
produces a JSON report containing the makespan, the critical path, and a
per‑task start/end schedule.

The program is intentionally simple – it is meant to run in the isolated
``/noobia/dushich/workspace`` environment as part of the local inference
stress test.  It uses only the Python standard library.

Example invocation::

    python3 projects/inference_probe/workflow.py tasks.json --workers 2 --resource cpu=2,mem=1

The output is written to ``stdout`` as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple


class SchedulerError(Exception):
    """Raised for any validation or scheduling error."""


@dataclass
class Task:
    id: str
    duration: int
    resources: Dict[str, int]
    deps: List[str]


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Schedule a task DAG with resources.")
    parser.add_argument("dag", help="Path to JSON file describing the DAG.")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers.")
    parser.add_argument(
        "--resource",
        action="append",
        default=[],
        help="Resource capacity in the form name=value. Can be repeated.",
    )
    return parser.parse_args(argv)


def load_dag(path: str) -> Tuple[List[Task], int, Dict[str, int]]:
    try:
        data = json.loads(open(path).read())
    except Exception as exc:  # pragma: no cover - defensive
        raise SchedulerError(f"Failed to load JSON: {exc}")

    if not isinstance(data, dict):
        raise SchedulerError("Top level JSON must be an object")
    tasks_data = data.get("tasks")
    if tasks_data is None or not isinstance(tasks_data, list):
        raise SchedulerError("'tasks' key must be a list")

    tasks: List[Task] = []
    ids: Set[str] = set()
    for t in tasks_data:
        if not isinstance(t, dict):
            raise SchedulerError("Each task must be an object")
        try:
            tid = t["id"]
            dur = int(t["duration"])
            res = dict(t.get("resources", {}))
            deps = list(t.get("deps", []))
        except KeyError as exc:
            raise SchedulerError(f"Missing key in task: {exc}")
        if tid in ids:
            raise SchedulerError(f"Duplicate task id: {tid}")
        ids.add(tid)
        tasks.append(Task(tid, dur, res, deps))

    workers = int(data.get("workers", 1))
    if workers <= 0:
        raise SchedulerError("workers must be positive")

    # Resources from command line override JSON if provided
    json_res = data.get("resources", {})
    resources = dict(json_res)
    return tasks, workers, resources


def validate(tasks: List[Task], resources: Dict[str, int]) -> None:
    # Check all deps exist
    ids = {t.id for t in tasks}
    for t in tasks:
        for d in t.deps:
            if d not in ids:
                raise SchedulerError(f"Task {t.id} has unknown dependency {d}")
    # Detect cycles using Kahn's algorithm
    indeg: Dict[str, int] = {t.id: 0 for t in tasks}
    for t in tasks:
        for d in t.deps:
            indeg[t.id] += 1
    queue = deque([tid for tid, d in indeg.items() if d == 0])
    seen = 0
    while queue:
        cur = queue.popleft()
        seen += 1
        for t in tasks:
            if cur in t.deps:
                indeg[t.id] -= 1
                if indeg[t.id] == 0:
                    queue.append(t.id)
    if seen != len(tasks):
        raise SchedulerError("Cycle detected in DAG")

    # Ensure each task's resources are <= global capacity
    for t in tasks:
        for r, amt in t.resources.items():
            cap = resources.get(r)
            if cap is None:
                raise SchedulerError(f"Task {t.id} requests unknown resource {r}")
            if amt > cap:
                raise SchedulerError(
                    f"Task {t.id} requests {amt} of {r}, exceeding capacity {cap}"
                )


def schedule(tasks: List[Task], workers: int, resources: Dict[str, int]) -> Dict:
    # Build adjacency lists
    dep_map: Dict[str, Set[str]] = {t.id: set(t.deps) for t in tasks}
    rev_map: Dict[str, Set[str]] = defaultdict(set)
    for t in tasks:
        for d in t.deps:
            rev_map[d].add(t.id)
    # Topological order for deterministic tie‑breaking
    sorted_tasks = sorted(tasks, key=lambda t: t.id)
    # State tracking
    remaining = set(t.id for t in tasks)
    ready: List[str] = []  # tasks whose deps satisfied
    for t in sorted_tasks:
        if not t.deps:
            ready.append(t.id)
    ready.sort()
    schedule: Dict[str, Dict[str, int]] = {}
    # Resource availability per tick
    avail = resources.copy()
    busy: List[Tuple[int, str]] = []  # (end_time, task_id)
    current_time = 0
    # Helper: pop next completed task
    def advance_time(to_time: int):
        nonlocal current_time, avail
        # Move time forward and free resources
        while busy and busy[0][0] <= to_time:
            end, tid = busy.pop(0)
            task = next(t for t in tasks if t.id == tid)
            # release resources
            for r, amt in task.resources.items():
                avail[r] += amt
            current_time = end
        # If no tasks finished, set current_time to to_time
        if current_time < to_time:
            current_time = to_time
    # Main loop
    while remaining:
        # Try to start as many ready tasks as possible
        started = False
        for tid in list(ready):
            task = next(t for t in tasks if t.id == tid)
            # Check worker slot and resources
            if len(busy) >= workers:
                break
            if all(avail.get(r, 0) >= amt for r, amt in task.resources.items()):
                # start task
                start = current_time
                end = start + task.duration
                schedule[tid] = {"start": start, "end": end}
                # allocate resources
                for r, amt in task.resources.items():
                    avail[r] -= amt
                busy.append((end, tid))
                busy.sort()  # keep by end time
                ready.remove(tid)
                remaining.remove(tid)
                started = True
        if not started:
            if busy:
                next_end = busy[0][0]
                advance_time(next_end)
                for t in sorted_tasks:
                    if t.id in remaining and set(t.deps).issubset(schedule.keys()):
                        if t.id not in ready:
                            ready.append(t.id)
                ready.sort()
            else:
                raise SchedulerError("Deadlock: no tasks can be scheduled")
    makespan = max(v["end"] for v in schedule.values()) if schedule else 0
    # Compute critical path: longest path in DAG using DP
    longest: Dict[str, int] = {t.id: 0 for t in tasks}
    prev: Dict[str, str | None] = {t.id: None for t in tasks}
    for t in sorted_tasks:
        max_dep = 0
        best_prev = None
        for d in t.deps:
            if longest[d] > max_dep:
                max_dep = longest[d]
                best_prev = d
        longest[t.id] = max_dep + t.duration
        prev[t.id] = best_prev
    max_end = max(longest.values()) if longest else 0
    # backtrack one longest path
    # pick a task with longest == max_end
    end_task = max(longest, key=lambda k: longest[k])
    crit_path_rev = []
    cur = end_task
    while cur is not None:
        crit_path_rev.append(cur)
        cur = prev[cur]
    crit_path = list(reversed(crit_path_rev))
    return {
        "makespan": makespan,
        "critical_path": crit_path,
        "schedule": schedule,
    }


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        tasks, workers, res_cap = load_dag(args.dag)
    except SchedulerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        validate(tasks, res_cap)
    except SchedulerError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        sys.exit(1)
    report = schedule(tasks, workers, res_cap)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()

