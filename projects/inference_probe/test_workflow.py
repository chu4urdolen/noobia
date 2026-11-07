import json
import os
import subprocess
import sys
import tempfile
import unittest


SCRIPT = os.path.join("projects", "inference_probe", "workflow.py")


class TestWorkflow(unittest.TestCase):
    def run_dag(self, dag: dict, workers: int = 1) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump(dag, f)
            f_path = f.name
        args = [sys.executable, SCRIPT, f_path, "--workers", str(workers)]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.unlink(f_path)
        return result

    def test_cycle(self):
        dag = {
            "tasks": [
                {"id": "A", "duration": 1, "deps": ["B"]},
                {"id": "B", "duration": 1, "deps": ["A"]},
            ],
            "workers": 1,
            "resources": {"cpu": 1},
        }
        res = self.run_dag(dag)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Cycle detected", res.stderr)

    def test_resource_conflict(self):
        dag = {
            "tasks": [
                {"id": "A", "duration": 2, "resources": {"cpu": 2}, "deps": []},
                {"id": "B", "duration": 1, "resources": {"cpu": 2}, "deps": []},
            ],
            "workers": 2,
            "resources": {"cpu": 2},
        }
        res = self.run_dag(dag, workers=2)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["makespan"], 3)
        # A must finish before B starts (or vice versa)
        a_end = out["schedule"]["A"]["end"]
        b_start = out["schedule"]["B"]["start"]
        b_end = out["schedule"]["B"]["end"]
        a_start = out["schedule"]["A"]["start"]
        self.assertTrue(a_end <= b_start or b_end <= a_start)

    def test_tie_breaking(self):
        dag = {
            "tasks": [
                {"id": "A", "duration": 1, "resources": {"cpu": 1}, "deps": []},
                {"id": "B", "duration": 1, "resources": {"cpu": 1}, "deps": []},
            ],
            "workers": 2,
            "resources": {"cpu": 2},
        }
        res = self.run_dag(dag, workers=2)
        out = json.loads(res.stdout)
        # both start at 0 because workers allow
        self.assertEqual(out["schedule"]["A"]["start"], 0)
        self.assertEqual(out["schedule"]["B"]["start"], 0)

    def test_critical_path(self):
        dag = {
            "tasks": [
                {"id": "A", "duration": 1, "resources": {"cpu": 1}, "deps": []},
                {"id": "B", "duration": 1, "resources": {"cpu": 1}, "deps": ["A"]},
                {"id": "C", "duration": 1, "resources": {"cpu": 1}, "deps": ["B"]},
            ],
            "workers": 2,
            "resources": {"cpu": 2},
        }
        res = self.run_dag(dag, workers=2)
        out = json.loads(res.stdout)
        self.assertEqual(out["makespan"], 3)
        self.assertEqual(out["critical_path"], ["A", "B", "C"])

    def test_topological_critical_path_order(self):
        # A depends on Z; Z should come first in critical path
        dag = {
            "tasks": [
                {"id": "A", "duration": 2, "resources": {"cpu": 1}, "deps": ["Z"]},
                {"id": "Z", "duration": 3, "resources": {"cpu": 1}, "deps": []},
            ],
            "workers": 1,
            "resources": {"cpu": 1},
        }
        res = self.run_dag(dag, workers=1)
        out = json.loads(res.stdout)
        self.assertEqual(out["makespan"], 5)
        self.assertEqual(out["critical_path"], ["Z", "A"])

    def test_dependency_completion(self):
        # C depends on A; C cannot start until A finishes
        dag = {
            "tasks": [
                {"id": "A", "duration": 10, "resources": {"cpu": 1}, "deps": []},
                {"id": "B", "duration": 1, "resources": {"cpu": 1}, "deps": []},
                {"id": "C", "duration": 1, "resources": {"cpu": 1}, "deps": ["A"]},
            ],
            "workers": 2,
            "resources": {"cpu": 2},
        }
        res = self.run_dag(dag, workers=2)
        out = json.loads(res.stdout)
        self.assertEqual(out["makespan"], 11)
        # C starts after A finishes at 10
        self.assertEqual(out["schedule"]["C"]["start"], 10)

    def test_worker_capacity(self):
        # three independent tasks with 1 worker
        dag = {
            "tasks": [
                {"id": "T1", "duration": 1, "resources": {"cpu": 1}, "deps": []},
                {"id": "T2", "duration": 1, "resources": {"cpu": 1}, "deps": []},
                {"id": "T3", "duration": 1, "resources": {"cpu": 1}, "deps": []},
            ],
            "workers": 1,
            "resources": {"cpu": 1},
        }
        res = self.run_dag(dag, workers=1)
        out = json.loads(res.stdout)
        self.assertEqual(out["makespan"], 3)
        starts = [out["schedule"][t]["start"] for t in ["T1","T2","T3"]]
        self.assertEqual(sorted(starts), [0,1,2])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

