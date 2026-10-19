import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import resolve  # noqa: E402

POLICY = resolve.load_policy()
ORGS = ["simtabi", "laranail"]
WORKFLOWS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         ".github", "workflows")


def write_policy(policy):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(policy, fh)
    fh.close()
    return fh.name


class ResolveTest(unittest.TestCase):
    def test_merge_gets_exactly_its_permissions_on_every_repository(self):
        out = resolve.resolve(POLICY, ORGS, "dependabot-merge", "laranail")
        self.assertEqual(out["permission-workflows"], "write")
        self.assertEqual(out["permission-checks"], "read")
        self.assertEqual(out["permission-issues"], "")
        self.assertEqual(out["repositories"], "")

    def test_every_ceiling_permission_is_emitted_so_none_is_inherited(self):
        out = resolve.resolve(POLICY, ORGS, "dependabot-reconcile", "simtabi")
        self.assertEqual({k for k in out if k.startswith("permission-")},
                         {f"permission-{p}" for p in POLICY["ceiling"]})
        self.assertEqual(out["permission-workflows"], "")

    def test_a_job_limited_to_repositories_is_limited(self):
        out = resolve.resolve(POLICY, ORGS, "agent-kit-read", "simtabi")
        self.assertEqual(out["repositories"], "agent-kit")
        self.assertEqual(out["permission-contents"], "read")

    def test_unknown_job_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no job"):
            resolve.resolve(POLICY, ORGS, "deploy-everything", "simtabi")

    def test_owner_outside_the_job_is_refused(self):
        with self.assertRaisesRegex(ValueError, "may not act on laranail"):
            resolve.resolve(POLICY, ORGS, "agent-kit-read", "laranail")

    def test_star_means_managed_orgs_only(self):
        with self.assertRaisesRegex(ValueError, "may not act on"):
            resolve.resolve(POLICY, ORGS, "dependabot-merge", "someone-else")

    def test_client_accounts_are_refused_even_when_listed(self):
        for owner in ("adelsaiq", "dannielagumo", "joemanch"):
            with self.assertRaisesRegex(ValueError, "client account"):
                resolve.resolve(POLICY, ORGS + [owner], "dependabot-merge", owner)

    def test_policy_naming_a_client_account_does_not_load(self):
        p = copy.deepcopy(POLICY)
        p["jobs"]["agent-kit-read"]["owners"] = ["dannielagumo"]
        with self.assertRaisesRegex(ValueError, "client accounts"):
            resolve.load_policy(write_policy(p))

    def test_job_without_permissions_does_not_load(self):
        # The action would pass no permission input, and the token would carry the whole app.
        p = copy.deepcopy(POLICY)
        p["jobs"]["dependabot-reconcile"]["permissions"] = {}
        with self.assertRaisesRegex(ValueError, "no permissions"):
            resolve.load_policy(write_policy(p))

    def test_permission_above_the_ceiling_does_not_load(self):
        for perm, level in (("checks", "write"), ("administration", "write")):
            p = copy.deepcopy(POLICY)
            p["jobs"]["dependabot-reconcile"]["permissions"][perm] = level
            with self.assertRaisesRegex(ValueError, "ceiling"):
                resolve.load_policy(write_policy(p))

    def test_cli_prints_outputs_or_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(resolve.main(["--job", "dependabot-merge", "--owner", "simtabi"]), 0)
        self.assertIn("permission-contents=write\n", out.getvalue())
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(resolve.main(["--job", "nope", "--owner", "simtabi"]), 1)
        self.assertEqual(out.getvalue(), "")

    def test_the_action_passes_exactly_the_ceiling(self):
        # A ceiling permission the action does not pass would be silently dropped; one it passes that the
        # ceiling lacks would always be empty.
        action = os.path.join(os.path.dirname(WORKFLOWS), "actions", "bot-token", "action.yml")
        with open(action, encoding="utf-8") as fh:
            passed = {line.strip().split(":", 1)[0][len("permission-"):]
                      for line in fh if line.strip().startswith("permission-")}
        self.assertEqual(passed, set(POLICY["ceiling"]))

    def test_every_job_a_workflow_asks_for_exists(self):
        # A renamed job would otherwise fail only when its schedule next fires.
        asked = set()
        files = [f for f in os.listdir(WORKFLOWS) if f.endswith((".yml", ".yaml"))]
        self.assertGreaterEqual(len(files), 3)
        for name in files:
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("job:") and "bot-token" not in line:
                        asked.add(line.split(":", 1)[1].strip().strip("'\""))
        self.assertGreaterEqual(len(asked), 3)
        self.assertEqual(asked - set(POLICY["jobs"]), set())


if __name__ == "__main__":
    unittest.main()
