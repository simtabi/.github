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
        self.assertEqual(out["permission-contents"], "write")
        self.assertEqual(out["permission-pull-requests"], "write")
        self.assertEqual(out["repositories"], "")
        # It cannot reach .github/workflows/, by design: see the job's `why`.
        self.assertNotIn("permission-workflows", out)

    def test_every_ceiling_permission_is_emitted_so_none_is_inherited(self):
        out = resolve.resolve(POLICY, ORGS, "dependabot-reconcile", "simtabi")
        self.assertEqual({k for k in out if k.startswith("permission-")},
                         {f"permission-{p}" for p in POLICY["ceiling"]})
        read_only = resolve.resolve(POLICY, ORGS, "estate-read", "simtabi")
        self.assertEqual(read_only["permission-contents"], "read")

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

    def test_an_empty_repositories_list_does_not_load(self):
        # It reads as "narrowed" and resolves to "", which the action treats as every repository of the
        # owner. The opposite of what whoever wrote it meant, and silent.
        p = copy.deepcopy(POLICY)
        p["jobs"]["agent-kit-read"]["repositories"] = []
        with self.assertRaisesRegex(ValueError, "non-empty list of names"):
            resolve.load_policy(write_policy(p))

    def test_repositories_written_as_owner_slash_name_do_not_load(self):
        # create-github-app-token takes bare names; "simtabi/agent-kit" matches no repository and the
        # token comes back scoped to nothing.
        p = copy.deepcopy(POLICY)
        p["jobs"]["agent-kit-read"]["repositories"] = ["simtabi/agent-kit"]
        with self.assertRaisesRegex(ValueError, "not owner/name"):
            resolve.load_policy(write_policy(p))

    def test_narrowed_repositories_with_star_owners_do_not_load(self):
        # The same names would go to every managed org, handing a token to a same-named repository
        # somewhere it was never meant to reach.
        p = copy.deepcopy(POLICY)
        p["jobs"]["dependabot-reconcile"]["repositories"] = ["agent-kit"]
        with self.assertRaisesRegex(ValueError, "explicit owners list"):
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

    def test_every_workflow_that_mints_a_token_skips_when_the_credentials_are_not_ready(self):
        # A half-configured app is one notice, not one create-github-app-token failure per org. The
        # merge gate had this from the start; the reconciler did not, and would have failed twelve
        # times over once Refresh Bot's fallback is retired.
        minting = []
        for name in sorted(os.listdir(WORKFLOWS)):
            if not name.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
                text = fh.read()
            if "actions/bot-token" in text:
                minting.append((name, text))
        self.assertGreaterEqual(len(minting), 2, "no workflow mints a token; this sweep proves nothing")
        for name, text in minting:
            with self.subTest(workflow=name):
                self.assertIn("outputs.ready", text,
                              f"{name} mints a token without gating on a readiness check")


class CeilingMatchesTheAppTest(unittest.TestCase):
    """The ceiling is refresh-bot's own permission set, and that is the whole safety property.

    simtabi-bot was retired on 2026-11-03 to keep the estate to two apps, and refresh-bot became the
    single CI app. The two differ in a way that decides this file:

        refresh-bot   checks=read contents=write metadata=read
                      pull_requests=write statuses=read                      (5)

    checks and statuses were granted on 2026-11-03, after simtabi-bot was retired, so the
    Dependabot merge gate can read whether a head is green; all 10 orgs approved them. The app
    still has no workflows:write and must never gain it.

    refresh-bot is the narrower app, and its key is organisation-level on every owned org -- so a
    ceiling wider than it holds would put that extra reach within range of every workflow in the
    estate. `workflows: write` is the one that matters: with it, a release job could rewrite the CI
    that gates it. Measured with `gh api apps/refresh-bot --jq .permissions`.
    """

    REFRESH_BOT_HELD = {"contents": "write", "pull-requests": "write",
                        "checks": "read", "statuses": "read"}
    NEVER = ("workflows", "issues", "administration", "members", "secrets")
    # workflows is the one that matters: this app's key is organisation-level.

    def test_the_ceiling_is_exactly_what_the_app_holds(self):
        self.assertEqual(POLICY["ceiling"], self.REFRESH_BOT_HELD)

    def test_no_job_can_ask_for_a_permission_the_app_does_not_hold(self):
        jobs = POLICY["jobs"]
        self.assertGreaterEqual(len(jobs), 8, "too few jobs; this sweep would prove little")
        for name, job in jobs.items():
            with self.subTest(job=name):
                for perm, level in job["permissions"].items():
                    self.assertIn(perm, self.REFRESH_BOT_HELD,
                                  f"{name} wants {perm}, which refresh-bot does not hold")
                    self.assertLessEqual(resolve.RANK[level],
                                         resolve.RANK[self.REFRESH_BOT_HELD[perm]])

    def test_the_ceiling_refuses_each_dangerous_permission(self):
        # Proven red rather than assumed: each of these loads fine under a widened ceiling, so the
        # ceiling is the only thing refusing them.
        for perm in self.NEVER:
            with self.subTest(permission=perm):
                p = copy.deepcopy(POLICY)
                p["jobs"]["release-pr"]["permissions"][perm] = "write"
                with self.assertRaisesRegex(ValueError, "ceiling"):
                    resolve.load_policy(write_policy(p))

    def test_release_pr_cannot_touch_workflows(self):
        # release-pr is owners "*", so it is reachable for every managed org.
        out = resolve.resolve(POLICY, ORGS, "release-pr", "laranail")
        self.assertNotIn("permission-workflows", out)
        self.assertEqual(out["permission-contents"], "write")
        self.assertEqual(out["permission-pull-requests"], "write")

    def test_the_jobs_that_replaced_refresh_bot_s_own_work_are_present(self):
        # A sweep over a name that no longer exists asserts nothing at all.
        expected = ("release-pr", "estate-read", "private-dep-read", "consumer-read",
                    "package-repo-push")
        missing = [j for j in expected if j not in POLICY["jobs"]]
        self.assertEqual(missing, [], f"policy is missing {missing}")

    def test_the_narrowed_jobs_refuse_an_owner_they_do_not_name(self):
        for job, allowed in (("private-dep-read", "simtabi"), ("consumer-read", "ichava"),
                             ("package-repo-push", "simtabi")):
            with self.subTest(job=job):
                resolve.resolve(POLICY, ORGS + ["ichava"], job, allowed)  # the positive control
                with self.assertRaisesRegex(ValueError, "may not act on"):
                    resolve.resolve(POLICY, ORGS + ["ichava", "tusente"], job, "tusente")

    def test_the_read_only_jobs_cannot_write(self):
        for job, owner in (("estate-read", "laranail"), ("private-dep-read", "simtabi"),
                           ("consumer-read", "ichava")):
            with self.subTest(job=job):
                out = resolve.resolve(POLICY, ORGS + ["ichava"], job, owner)
                for key, value in out.items():
                    if key.startswith("permission-"):
                        self.assertNotEqual(value, "write", f"{job} writes via {key}")


if __name__ == "__main__":
    unittest.main()
