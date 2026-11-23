"""Guards for the release-train workflows: the freeze check's shell runs against a fixed clock, and
the orchestrator's schedules stay in step with the step selector that reads them."""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOW = ROOT / ".github" / "workflows" / "release-window.yml"
TRAIN = ROOT / ".github" / "workflows" / "release-train.yml"


def window_script():
    text = WINDOW.read_text(encoding="utf-8")
    m = re.search(r"- name: Check the release freeze\n(?:        .*\n)*?        run: \|\n((?:          .*\n|\n)+)", text)
    assert m, "release-window.yml has no run block"
    return "\n".join(line[10:] for line in m.group(1).splitlines())


def run_window(day, hm, labels=(), head="feat/x"):
    """Run the freeze check with `date` answering `day hm` (ISO weekday, HHMM)."""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "date"
        fake.write_text(f"#!/bin/sh\necho '{day} {hm}'\n", encoding="utf-8")
        fake.chmod(0o755)
        env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}", LABELS=json.dumps(list(labels)), HEAD_REF=head)
        return subprocess.run(["bash", "-c", window_script()], env=env, capture_output=True, text=True).returncode


class Window(unittest.TestCase):
    def test_open_outside_the_freeze(self):
        for day, hm in ((3, "1200"), (4, "0900"), (5, "1759"), (2, "1230"), (2, "1500")):
            self.assertEqual(run_window(day, hm), 0, f"{day} {hm}")

    def test_frozen_inside(self):
        for day, hm in ((5, "1800"), (6, "0000"), (7, "1200"), (1, "2359"), (2, "0800"), (2, "1229")):
            self.assertEqual(run_window(day, hm), 1, f"{day} {hm}")

    def test_allowed_through_the_freeze(self):
        self.assertEqual(run_window(6, "1000", labels=["release-fix"]), 0)
        self.assertEqual(run_window(6, "1000", head="release/train-1.2.3"), 0)
        self.assertEqual(run_window(6, "1000", labels=["release-fixes"]), 1)

    def test_leading_zero_times_are_decimal(self):
        # 0800 and 0900 are not octal: 10#$hm.
        self.assertEqual(run_window(2, "0900"), 1)


class Reopen(unittest.TestCase):
    def test_modes_are_separate_jobs(self):
        text = WINDOW.read_text(encoding="utf-8")
        self.assertIn("if: inputs.mode == 'check'", text)
        self.assertIn("if: inputs.mode == 'reopen'", text)
        # Only the reopen job may write; the per-PR check holds no permissions at all.
        check = text.split("\n  reopen:\n")[0]
        self.assertNotIn("actions: write", check.split("\njobs:\n")[1])
        self.assertIn("gh run rerun", text.split("\n  reopen:\n")[1])

    def test_reopen_runs_after_the_freeze_lifts(self):
        text = WINDOW.read_text(encoding="utf-8")
        cron = re.search(r'cron: "(\d+) (\d+) \* \* 2"', text)
        self.assertIsNotNone(cron, "the documented caller schedules reopen on a Tuesday")
        self.assertGreater(int(cron.group(2)) * 100 + int(cron.group(1)), 1230)


class DocumentedCaller(unittest.TestCase):
    """GitHub checks every job of a called workflow against the caller job's permissions before it
    starts, even a job that is skipped. The window caller job must therefore grant what the reopen job
    asks for, or the check never starts (startup_failure; laranail/package-tools#111, 2026-11-23)."""

    def callers(self):
        readme = (ROOT / "release-train" / "README.md").read_text(encoding="utf-8")
        header = "\n".join(l[1:] for l in WINDOW.read_text(encoding="utf-8").splitlines() if l.startswith("#"))
        found = []
        for name, text in (("README.md", readme), ("release-window.yml header", header)):
            blocks = re.findall(r"\n(\s*)window:\n(.*?)\n\1reopen:\n", text, re.S)
            found += [(name, body) for _, body in blocks]
        return found

    def test_window_caller_job_grants_the_reopen_permissions(self):
        callers = self.callers()
        self.assertEqual(len(callers), 2, "one documented caller in the README and one in the workflow header")
        for name, body in callers:
            with self.subTest(name):
                self.assertIn("actions: write", body)
                self.assertIn("pull-requests: read", body)


class Schedules(unittest.TestCase):
    def test_every_cron_has_a_step_and_a_timezone(self):
        text = TRAIN.read_text(encoding="utf-8")
        crons = re.findall(r'- cron: "([^"]+)"\n\s+timezone: America/New_York', text)
        self.assertEqual(len(crons), 3, "three schedules, each in New York time")
        for cron in crons:
            self.assertIn(f'"schedule:{cron}")', text, f"no step reads schedule {cron}")


if __name__ == "__main__":
    unittest.main()
