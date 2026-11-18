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
    m = re.search(r"        run: \|\n((?:          .*\n|\n)+)", text)
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


class Schedules(unittest.TestCase):
    def test_every_cron_has_a_step_and_a_timezone(self):
        text = TRAIN.read_text(encoding="utf-8")
        crons = re.findall(r'- cron: "([^"]+)"\n\s+timezone: America/New_York', text)
        self.assertEqual(len(crons), 3, "three schedules, each in New York time")
        for cron in crons:
            self.assertIn(f'"schedule:{cron}")', text, f"no step reads schedule {cron}")


if __name__ == "__main__":
    unittest.main()
